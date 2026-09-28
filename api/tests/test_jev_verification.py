from datetime import UTC, datetime

import pytest

from app.core.config import Settings
from app.domain.entities import VerdictLabel
from app.services.crc import CRCCalibration
from app.services.jev_verification import JevVerificationService


class StaticCalibrations:
    def __init__(self, calibration: CRCCalibration | None) -> None:
        self.calibration = calibration

    def get_latest(self, model: str) -> CRCCalibration | None:
        return self.calibration


def build_service(calibration: CRCCalibration | None, **settings) -> JevVerificationService:
    return JevVerificationService(
        classifier=None,
        sources=[],
        calibration_repo=StaticCalibrations(calibration),
        settings=Settings(_env_file=None, **settings),
    )


def calibration(lambda_hat: float) -> CRCCalibration:
    return CRCCalibration(
        lambda_hat=lambda_hat, alpha=0.05, n=40, model="jev", created_at=datetime.now(UTC)
    )


def test_abstains_without_calibration_by_default():
    label, confidence, rationale = build_service(None)._apply_calibration(
        VerdictLabel.FALSE, 0.95, 2
    )
    assert label == VerdictLabel.INSUFFICIENT_EVIDENCE
    assert confidence == 0.0
    assert "não há calibração" in rationale


def test_allow_uncalibrated_keeps_raw_verdict_and_says_so():
    service = build_service(None, jev_allow_uncalibrated=True)
    label, confidence, rationale = service._apply_calibration(VerdictLabel.FALSE, 0.95, 2)
    assert label == VerdictLabel.FALSE
    assert confidence == 0.95
    assert "JEV_ALLOW_UNCALIBRATED" in rationale


@pytest.mark.parametrize("allow_uncalibrated", [False, True])
def test_existing_calibration_still_gates_low_confidence(allow_uncalibrated):
    service = build_service(calibration(0.9), jev_allow_uncalibrated=allow_uncalibrated)
    label, _, rationale = service._apply_calibration(VerdictLabel.MISLEADING, 0.85, 1)
    assert label == VerdictLabel.INSUFFICIENT_EVIDENCE
    assert "lambda_hat" in rationale
