"""Persistência idempotente e ranking semântico com bônus limitado de recência."""

from datetime import UTC, datetime

from sqlalchemy import case, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db.orm.fact_article import FactArticle
from app.domain.entities import Evidence


class FactArticleRepository:
    def __init__(self, engine):
        self.engine = engine

    def unchanged(self, article: dict) -> bool:
        with Session(self.engine) as session:
            old = session.get(FactArticle, article["url"])
            return old is not None and all(
                getattr(old, key) == article[key]
                for key in ("source", "title", "summary", "published_at")
            )

    def upsert(self, articles: list[dict]) -> int:
        if not articles:
            return 0
        with Session(self.engine) as session, session.begin():
            statement = insert(FactArticle).values(articles)
            session.execute(
                statement.on_conflict_do_update(
                    index_elements=[FactArticle.url],
                    set_={
                        key: getattr(statement.excluded, key) for key in articles[0] if key != "url"
                    },
                )
            )
        return len(articles)

    def count(self) -> int:
        with Session(self.engine) as session:
            return session.scalar(select(func.count()).select_from(FactArticle))

    def search(self, vector, *, sources, limit, weight, half_life, min_similarity):
        similarity = 1 - FactArticle.embedding.cosine_distance(vector)
        age_days = func.greatest(
            func.extract("epoch", datetime.now(UTC) - FactArticle.published_at) / 86400, 0
        )
        recency = case(
            (FactArticle.published_at.is_(None), 0.0),
            else_=func.power(0.5, age_days / half_life),
        )
        score = (1 - weight) * similarity + weight * recency
        statement = (
            select(FactArticle)
            .where(FactArticle.source.in_(sources), similarity >= min_similarity)
            .order_by(score.desc(), FactArticle.url)
            .limit(limit)
        )
        with Session(self.engine) as session:
            return [
                Evidence(
                    source="rss_checkers",
                    url=row.url,
                    title=row.title,
                    snippet=row.summary,
                    published_at=row.published_at,
                )
                for row in session.scalars(statement)
            ]
