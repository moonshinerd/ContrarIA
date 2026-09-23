"""Entry point do serviço HTTP do ContrarIA.

O processamento contínuo (coleta, triagem, verificação, intervenção) roda no
worker (`app/worker.py`), na mesma imagem. A API expõe saúde, consulta de
decisões e a verificação sob demanda.
"""

from fastapi import FastAPI

from app.core.config import get_settings
from app.core.logging import configure_logging

from app.routers.v1 import decisions

settings = get_settings()
configure_logging(settings)

app = FastAPI(title=settings.app_name, version="0.1.0")

app.include_router(decisions.router)


@app.get("/health", tags=["infra"])
def health() -> dict[str, str]:
    """Liveness: não toca banco, LLM nem Bluesky."""
    return {"status": "ok"}
