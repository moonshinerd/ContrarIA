"""Persistência e consulta das calibrações CRC."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.orm.crc_calibration import CRCCalibrationRecord
from app.services.crc import CRCCalibration


class CRCCalibrationRepository:
    def __init__(self, engine) -> None:
        self.engine = engine

    def save(self, calibration: CRCCalibration) -> CRCCalibration:
        with Session(self.engine) as session, session.begin():
            session.add(
                CRCCalibrationRecord(
                    lambda_hat=calibration.lambda_hat,
                    alpha=calibration.alpha,
                    n=calibration.n,
                    model=calibration.model,
                    created_at=calibration.created_at,
                )
            )
        return calibration

    def get_latest(self, model: str) -> CRCCalibration | None:
        statement = (
            select(CRCCalibrationRecord)
            .where(CRCCalibrationRecord.model == model)
            .order_by(CRCCalibrationRecord.created_at.desc(), CRCCalibrationRecord.id.desc())
            .limit(1)
        )
        with Session(self.engine) as session:
            row = session.scalar(statement)
            if row is None:
                return None
            return CRCCalibration(
                lambda_hat=row.lambda_hat,
                alpha=row.alpha,
                n=row.n,
                model=row.model,
                created_at=row.created_at,
            )
