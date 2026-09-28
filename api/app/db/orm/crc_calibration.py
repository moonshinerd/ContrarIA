"""Modelo ORM das calibrações de Conformal Risk Control."""

from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CRCCalibrationRecord(Base):
    __tablename__ = "crc_calibration"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lambda_hat: Mapped[float] = mapped_column("lambda", Float, nullable=False)
    alpha: Mapped[float] = mapped_column(Float, nullable=False)
    n: Mapped[int] = mapped_column(Integer, nullable=False)
    model: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
