"""Serviço dedicado do classificador Jev: uma única cópia do modelo em
memória, compartilhada por api/worker/scripts via HTTP.

Por que um serviço separado em vez de cada processo carregar o próprio
JevClassifier: medido ao vivo (28/09/2026), rodar api + worker + um script
de calibração ao mesmo tempo (3 cópias do modelo, ~3-4GB cada) estourou os
16GB de RAM do Docker Desktop e os três processos morreram por OOM. Com
este serviço, existe só uma cópia do modelo não importa quantos clientes
usem o classificador -- o próprio JevClassifier já serializa o acesso à
instância do llama.cpp internamente (não é thread-safe pra chamadas
concorrentes).

Rode com: uvicorn app.jev_server:app --host 0.0.0.0 --port 8100
"""

from fastapi import FastAPI
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.models.classifiers.jev import JevClassifier

settings = get_settings()
_classifier = JevClassifier(settings)

app = FastAPI(title="ContrarIA Jev Server", version="0.1.0")


class ClassifyRequest(BaseModel):
    question: str = Field(min_length=1)
    options: list[str] = Field(min_length=2, max_length=26)


class ClassifyResponse(BaseModel):
    probabilities: dict[str, float]


@app.post("/classify", response_model=ClassifyResponse)
async def classify(req: ClassifyRequest) -> ClassifyResponse:
    probabilities = await _classifier.classify(req.question, req.options)
    return ClassifyResponse(probabilities=probabilities)


@app.get("/health", tags=["infra"])
def health() -> dict[str, str]:
    """Liveness: não carrega o modelo (isso só acontece na 1ª classificação)."""
    return {"status": "ok"}
