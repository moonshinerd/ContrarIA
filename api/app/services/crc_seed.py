"""Seed automático da calibração CRC quando o banco ainda não tem nenhuma.

Sem uma calibração persistida para o modelo em uso, `_apply_runtime_guards`
(`app/services/verification.py`) força todo veredito para
`insufficient_evidence`, mesmo com evidência forte e consenso do debate --
isso já aconteceu num banco novo (deploy limpo, volume recriado, ambiente de
dev). Este módulo garante que sempre exista ao menos a calibração conhecida
mais recente, sem exigir que alguém lembre de rodar
`research/experiments/calibrate_crc.py` manualmente antes do primeiro uso.
Uma recalibração feita depois (mesmo script, dataset maior) sempre passa a
valer, já que `get_latest` usa a mais recente por `created_at`.
"""

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from app.core.config import Settings
from app.repositories.crc_calibration import CRCCalibrationRepository
from app.services.crc import CRCCalibration

logger = logging.getLogger("contraria.services.crc_seed")

SEED_PATH = Path(__file__).resolve().parent.parent / "domain" / "crc_calibration_seed.json"


def ensure_calibration_seeded(repo: CRCCalibrationRepository, settings: Settings) -> None:
    model = settings.crc_model_name or settings.llm_model_name
    if repo.get_latest(model) is not None:
        return

    if not SEED_PATH.exists():
        logger.warning("Seed de calibração CRC não encontrado em %s", SEED_PATH)
        return

    data = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    if data.get("model") != model:
        logger.warning(
            "Seed de calibração é para o modelo %s, mas o configurado é %s; nada foi gravado",
            data.get("model"),
            model,
        )
        return

    calibration = CRCCalibration(
        lambda_hat=data["lambda_hat"],
        alpha=data["alpha"],
        n=data["n"],
        model=model,
        created_at=datetime.now(UTC),
    )
    repo.save(calibration)
    logger.info(
        "Calibração CRC semeada automaticamente para %s (lambda_hat=%s, n=%s)",
        model,
        calibration.lambda_hat,
        calibration.n,
    )
