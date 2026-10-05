from sqlalchemy import func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db.orm.posts import IngestCursor, Post
from app.domain.entities import Post as DomainPost

PENDING_STATUSES = ("monitor", "queued")


def _is_pending():
    # Posts recém-coletados ainda não têm triagem (NULL) e já contam como fila.
    return or_(Post.triage_status.in_(PENDING_STATUSES), Post.triage_status.is_(None))


class PostRepository:
    def __init__(self, engine):
        self.engine = engine

    def upsert_posts(self, posts_data: list[dict]) -> int:
        if not posts_data:
            return 0
        with Session(self.engine) as session, session.begin():
            statement = insert(Post).values(posts_data)
            session.execute(statement.on_conflict_do_nothing(index_elements=[Post.uri]))
        return len(posts_data)

    def get_cursor(self, stream: str) -> int:
        with Session(self.engine) as session:
            cursor = session.scalar(
                select(IngestCursor.cursor).where(IngestCursor.stream == stream)
            )
            return cursor or 0

    def set_cursor(self, stream: str, cursor: int):
        with Session(self.engine) as session, session.begin():
            statement = insert(IngestCursor).values({"stream": stream, "cursor": cursor})
            session.execute(
                statement.on_conflict_do_update(
                    index_elements=[IngestCursor.stream], set_={"cursor": statement.excluded.cursor}
                )
            )

    def count_posts(self) -> int:
        from sqlalchemy import func

        with Session(self.engine) as session:
            return session.scalar(select(func.count()).select_from(Post))

    def pending_count(self) -> int:
        """Posts aguardando análise (inclui os ainda sem triagem)."""
        with Session(self.engine) as session:
            return session.scalar(select(func.count()).select_from(Post).where(_is_pending())) or 0

    def trim_pending(self, keep: int) -> int:
        """Mantém só os `keep` pendentes de maior prioridade; os demais viram 'expired'.

        O post continua no banco, só sai da fila ('expired' é status final: o refresher não o
        reativa). Devolve quantos foram expirados.
        """
        top = (
            select(Post.uri)
            .where(_is_pending())
            .order_by(Post.priority.desc().nullslast(), Post.first_seen_at.desc())
            .limit(keep)
        )
        with Session(self.engine) as session, session.begin():
            result = session.execute(
                update(Post)
                .where(_is_pending(), Post.uri.not_in(top))
                .values(triage_status="expired")
            )
        return result.rowcount

    def get_triage_candidates(
        self, limit: int, *, exclude_uris: set[str] | frozenset[str] = frozenset()
    ) -> list[tuple[DomainPost, float]]:
        """Retorna candidatos recentes em ordem de prioridade para o pipeline caro."""
        with Session(self.engine) as session:
            rows = session.scalars(
                select(Post)
                .where(Post.triage_status.in_(PENDING_STATUSES), Post.uri.not_in(exclude_uris))
                .order_by(Post.priority.desc().nullslast(), Post.first_seen_at.desc())
                .limit(limit)
            )
            return [
                (
                    DomainPost(
                        uri=row.uri,
                        cid=row.cid,
                        author_did=row.author_did,
                        text=row.text,
                        created_at=row.created_at,
                        langs=row.langs or [],
                    ),
                    row.priority or 0.0,
                )
                for row in rows
            ]

    def update_triage(self, uri: str, *, status: str, priority: float) -> None:
        from sqlalchemy import update

        with Session(self.engine) as session, session.begin():
            session.execute(
                update(Post).where(Post.uri == uri).values(triage_status=status, priority=priority)
            )
