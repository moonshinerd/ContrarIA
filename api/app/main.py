"""Entry point do serviço HTTP do ContrarIA.

O processamento contínuo (coleta, triagem, verificação, intervenção) roda no
worker (`app/worker.py`), na mesma imagem. A API expõe saúde, consulta de
decisões e a verificação sob demanda.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import create_engine

from app.core.config import get_settings
from app.core.logging import configure_logging, enable_database_logging
from app.repositories.crc_calibration import CRCCalibrationRepository
from app.routers.v1 import admin, decisions
from app.services.crc_seed import ensure_calibration_seeded

settings = get_settings()
configure_logging(settings)


@asynccontextmanager
async def lifespan(app: FastAPI):
    enable_database_logging(settings, service_name="api")
    engine = create_engine(settings.database_url)
    try:
        ensure_calibration_seeded(CRCCalibrationRepository(engine), settings)
    finally:
        engine.dispose()
    yield


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)

app.include_router(decisions.router)
app.include_router(admin.router, prefix="/v1")
app.include_router(admin.router)


@app.get("/health", tags=["infra"])
def health() -> dict[str, str]:
    """Liveness: não toca banco, LLM nem Bluesky."""
    return {"status": "ok"}
