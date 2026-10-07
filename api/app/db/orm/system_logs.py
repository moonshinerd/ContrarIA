"""Mapeamento ORM da tabela de logs estruturados do sistema."""

from datetime import UTC, datetime

from sqlalchemy import BigInteger, Column, DateTime, Index, Integer, String, Text
from sqlalchemy.types import JSON

from app.db.base import Base


class SystemLog(Base):
    """Log estruturado de evento do sistema (worker, api, etc.)."""

    __tablename__ = "system_logs"

    id = Column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        index=True,
    )
    level = Column(String(20), nullable=False, index=True)
    logger = Column(String(100), nullable=False, index=True)
    service = Column(String(50), nullable=False, index=True, default="unknown")
    message = Column(Text, nullable=False)
    context = Column(JSON, nullable=True)

    __table_args__ = (
        Index("ix_system_logs_service_created", "service", "created_at"),
        Index("ix_system_logs_level_created", "level", "created_at"),
    )
