from sqlalchemy import JSON, Column, DateTime, Float, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB

from app.db.base import Base


class DecisionLog(Base):
    """
    Log imutável de decisões (Issue #17).
    """

    __tablename__ = "decisions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    post_uri = Column(String, index=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Snapshot do post e conta
    post_snapshot = Column(JSON().with_variant(JSONB, "postgresql"), nullable=False)

    # Detalhes da avaliação
    bot_score = Column(Float, nullable=True)
    bot_features = Column(JSON().with_variant(JSONB, "postgresql"), nullable=True)

    # Verificação
    sources = Column(JSON().with_variant(JSONB, "postgresql"), nullable=True)
    agent_outputs = Column(JSON().with_variant(JSONB, "postgresql"), nullable=True)
    verdict = Column(String, nullable=True)  # INSUFFICIENT_EVIDENCE, FAKE, TRUE, etc
    confidence = Column(Float, nullable=True)
    crc_threshold_used = Column(Float, nullable=True)

    # Ação tomada
    action = Column(String, nullable=False)  # "IGNORE", "MONITOR", "INTERVENE"
    justification = Column(String, nullable=False)


class DecisionReview(Base):
    """Evento de revisão de uma decisão, sem alterar o log original."""

    __tablename__ = "decision_reviews"

    id = Column(Integer, primary_key=True, autoincrement=True)
    decision_id = Column(Integer, nullable=False, index=True)
    action = Column(String, nullable=False)
    justification = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
