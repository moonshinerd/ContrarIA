import hashlib
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db.orm.interventions import InterventionLog


class InterventionRepository:
    def __init__(self, engine):
        self.engine = engine

    def _generate_id(self, post_uri: str, action: str) -> str:
        s = f"{post_uri}|{action}"
        return hashlib.sha256(s.encode()).hexdigest()

    def has_intervened_on_post(self, post_uri: str, action: str) -> bool:
        doc_id = self._generate_id(post_uri, action)
        with Session(self.engine) as session:
            row = session.scalar(select(InterventionLog).where(InterventionLog.id == doc_id))
            return row is not None

    def count_interventions_by_author_in_last_24h(self, author_did: str, action: str) -> int:
        since = datetime.now(UTC) - timedelta(hours=24)
        with Session(self.engine) as session:
            stmt = select(InterventionLog).where(
                InterventionLog.author_did == author_did,
                InterventionLog.action == action,
                InterventionLog.created_at >= since,
            )
            return len(list(session.scalars(stmt)))

    def count_interventions_in_last_24h(self, action: str) -> int:
        since = datetime.now(UTC) - timedelta(hours=24)
        with Session(self.engine) as session:
            stmt = select(InterventionLog).where(
                InterventionLog.action == action, InterventionLog.created_at >= since
            )
            return len(list(session.scalars(stmt)))

    def record_intervention(self, post_uri: str, author_did: str, action: str) -> None:
        doc_id = self._generate_id(post_uri, action)
        with Session(self.engine) as session, session.begin():
            stmt = insert(InterventionLog).values(
                id=doc_id,
                post_uri=post_uri,
                author_did=author_did,
                action=action,
                created_at=datetime.now(UTC),
            )
            session.execute(stmt.on_conflict_do_nothing(index_elements=["id"]))
