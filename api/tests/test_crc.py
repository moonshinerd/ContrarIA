"""Testes da calibração e persistência de Conformal Risk Control."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine

from app.core.config import Settings
from app.db.base import Base
from app.repositories.crc_calibration import CRCCalibrationRepository
from app.services.crc import CalibrationExample, CRCCalibration, calibrate_threshold
from app.services.crc_seed import ensure_calibration_seeded


def test_calibration_respects_finite_sample_bound_and_false_positive_rate():
    examples = [
        CalibrationExample("true", "false", 0.72, "true-fp"),
        *[
            CalibrationExample("true", "true", 0.60 + index / 100, f"true-{index}")
            for index in range(12)
        ],
        *[
            CalibrationExample("false", "false", 0.75 + index / 100, f"false-{index}")
            for index in range(12)
        ],
    ]

    result = calibrate_threshold(examples, alpha=0.05)

    assert result.lambda_hat > 0.72
    assert result.false_positives == 0
    assert result.empirical_risk <= result.alpha
    assert result.conditional_false_positive_rate <= result.alpha
    assert result.risk_bound <= result.alpha


def test_calibration_rejects_sample_too_small_for_alpha():
    examples = [CalibrationExample("true", "true", 0.9, str(index)) for index in range(18)]

    with pytest.raises(ValueError, match="Use mais amostras"):
        calibrate_threshold(examples, alpha=0.05)


def test_repository_returns_latest_calibration_for_requested_model():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    repository = CRCCalibrationRepository(engine)
    now = datetime.now(UTC)
    repository.save(CRCCalibration(0.75, 0.05, 100, "model-a", now - timedelta(days=1)))
    repository.save(CRCCalibration(0.82, 0.05, 120, "model-a", now))
    repository.save(CRCCalibration(0.91, 0.05, 120, "model-b", now))

    latest = repository.get_latest("model-a")

    assert latest is not None
    assert latest.lambda_hat == 0.82
    assert repository.get_latest("unknown") is None


def test_ensure_calibration_seeded_persists_seed_for_configured_model():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    repository = CRCCalibrationRepository(engine)
    settings = Settings(_env_file=None)

    ensure_calibration_seeded(repository, settings)

    model = settings.crc_model_name or settings.llm_model_name
    seeded = repository.get_latest(model)
    assert seeded is not None
    assert seeded.lambda_hat == 0.0
    assert seeded.n == 52


def test_ensure_calibration_seeded_does_not_override_existing_calibration():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    repository = CRCCalibrationRepository(engine)
    settings = Settings(_env_file=None)
    model = settings.crc_model_name or settings.llm_model_name
    repository.save(CRCCalibration(0.42, 0.05, 100, model, datetime.now(UTC)))

    ensure_calibration_seeded(repository, settings)

    latest = repository.get_latest(model)
    assert latest is not None
    assert latest.lambda_hat == 0.42
    assert latest.n == 100
