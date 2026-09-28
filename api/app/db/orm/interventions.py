from sqlalchemy import Column, DateTime, String, func

from app.db.base import Base


class InterventionLog(Base):
    __tablename__ = "intervention_logs"

    id = Column(String, primary_key=True)  # Maybe just use post_uri + action as PK
    post_uri = Column(String, nullable=False, index=True)
    author_did = Column(String, nullable=False, index=True)
    action = Column(String, nullable=False)  # 'quote_post'
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
