import asyncio
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.clients.bluesky_client import BlueskyClient
from app.db.orm.posts import Post, PostEngagementSnapshot
from app.domain.prioritization import calculate_relevance

logger = logging.getLogger("contraria.jobs.refresh_engagement")


class EngagementRefresher:
    def __init__(self, engine, bsky_client: BlueskyClient, tick_seconds: int = 300):
        self.engine = engine
        self.bsky_client = bsky_client
        self.tick_seconds = tick_seconds

    def _get_candidate_uris(self) -> list[str]:
        # Posts das últimas 48 horas
        limit_time = datetime.now(UTC) - timedelta(hours=48)
        with Session(self.engine) as session:
            # Pegar URIs que precisam de refresh
            # Filtrar por data e ordenar por prioridade ou first_seen_at
            statement = (
                select(Post.uri)
                .where(Post.created_at >= limit_time)
                .order_by(Post.first_seen_at.desc())
                # Limitamos o batch total para não estourar a API caso o firehose pegue muito
                .limit(1000)
            )
            return list(session.scalars(statement))

    def _save_snapshots_and_update_priority(self, hydrated_posts):
        if not hydrated_posts:
            return

        now = datetime.now(UTC)
        snapshots = []
        uris = [p.uri for p in hydrated_posts]

        with Session(self.engine) as session:
            # Pegar o último snapshot para cada URI
            # Para isso usaremos uma query agregada ou apenas faremos distinct on
            # Postgres: SELECT DISTINCT ON (uri) ... ORDER BY uri, ts DESC
            stmt = (
                select(PostEngagementSnapshot)
                .where(PostEngagementSnapshot.uri.in_(uris))
                .order_by(PostEngagementSnapshot.uri, PostEngagementSnapshot.ts.desc())
            )

            # Pegaremos manualmente apenas o mais recente
            last_snapshots = {}
            for row in session.scalars(stmt):
                if row.uri not in last_snapshots:
                    last_snapshots[row.uri] = row

            # Precisamos atualizar a tabela posts também
            from sqlalchemy import update

            from app.db.orm.posts import Post

            with session.begin():
                for p in hydrated_posts:
                    snapshots.append(
                        {
                            "uri": p.uri,
                            "ts": now,
                            "likes": p.like_count,
                            "reposts": p.repost_count,
                            "replies": p.reply_count,
                            "quotes": p.quote_count,
                        }
                    )

                    last_snap = last_snapshots.get(p.uri)
                    velocity = 0.0

                    if last_snap:
                        delta_hours = (now - last_snap.ts).total_seconds() / 3600.0
                        if delta_hours > 0:
                            current_interactions = (
                                p.like_count + p.repost_count + p.reply_count + p.quote_count
                            )
                            old_interactions = (
                                last_snap.likes
                                + last_snap.reposts
                                + last_snap.replies
                                + last_snap.quotes
                            )
                            velocity = max(
                                0.0, (current_interactions - old_interactions) / delta_hours
                            )

                    # Followers count? The getPosts API doesn't return author followers count.
                    # getPosts doesn't have followers count.
                    # The entity Post does not have followers_count. The Account entity does.
                    # If we don't have followers count, we default to 0 for now.
                    relevance = calculate_relevance(
                        likes=p.like_count,
                        reposts=p.repost_count,
                        replies=p.reply_count,
                        quotes=p.quote_count,
                        velocity=velocity,
                        followers=0,  # TODO: fetch author profile or adjust relevance calculation
                    )

                    # Atualiza o post (apenas prioridade por enquanto)
                    # Por enquanto, apenas priority:
                    up_stmt = update(Post).where(Post.uri == p.uri).values(priority=relevance)
                    session.execute(up_stmt)

                if snapshots:
                    ins_stmt = insert(PostEngagementSnapshot).values(snapshots)
                    session.execute(ins_stmt.on_conflict_do_nothing(index_elements=["uri", "ts"]))

    async def run(self):
        while True:
            try:
                logger.info("Iniciando refresh de engajamento...")
                uris = self._get_candidate_uris()
                if uris:
                    hydrated = await self.bsky_client.get_posts(uris)
                    self._save_snapshots_and_update_priority(hydrated)
                    logger.info("Engajamento atualizado para %d posts.", len(hydrated))
            except Exception as e:
                logger.error("Erro no RefreshEngagement: %s", e)

            await asyncio.sleep(self.tick_seconds)
