"""Serviço dedicado do classificador Jev: uma única cópia do modelo mDeBERTa NLI em
memória, compartilhada por api/worker/scripts via HTTP.

Mantém o consumo de RAM baixo (~500MB) e atende requisições de classificação,
contagem de tokens e inferência NLI direta (premissa vs hipótese).

Rode com: uvicorn app.jev_server:app --host 0.0.0.0 --port 8100
"""

from fastapi import FastAPI
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.models.classifiers.jev import JevClassifier

settings = get_settings()
_classifier = JevClassifier(settings)

app = FastAPI(title="ContrarIA Jev Server", version="0.2.0")


class ClassifyRequest(BaseModel):
    question: str = Field(min_length=1)
    options: list[str] = Field(min_length=2, max_length=26)


class ClassifyResponse(BaseModel):
    probabilities: dict[str, float]


@app.post("/classify", response_model=ClassifyResponse)
async def classify(req: ClassifyRequest) -> ClassifyResponse:
    probabilities = await _classifier.classify(req.question, req.options)
    return ClassifyResponse(probabilities=probabilities)


class CountTokensRequest(BaseModel):
    texts: list[str] = Field(min_length=1)


class CountTokensResponse(BaseModel):
    counts: list[int]


@app.post("/count_tokens", response_model=CountTokensResponse)
async def count_tokens(req: CountTokensRequest) -> CountTokensResponse:
    return CountTokensResponse(counts=await _classifier.count_tokens(req.texts))


class NLIRequest(BaseModel):
    premise: str = Field(min_length=1)
    hypothesis: str = Field(min_length=1)


class NLIResponse(BaseModel):
    probabilities: dict[str, float]


@app.post("/nli", response_model=NLIResponse)
async def predict_nli(req: NLIRequest) -> NLIResponse:
    probabilities = await _classifier.predict_nli(req.premise, req.hypothesis)
    return NLIResponse(probabilities=probabilities)


class NLIPair(BaseModel):
    premise: str = Field(min_length=1)
    hypothesis: str = Field(min_length=1)


class NLIBatchRequest(BaseModel):
    pairs: list[NLIPair] = Field(min_length=1)


class NLIBatchResponse(BaseModel):
    results: list[dict[str, float]]


@app.post("/nli_batch", response_model=NLIBatchResponse)
async def predict_nli_batch(req: NLIBatchRequest) -> NLIBatchResponse:
    pairs = [(p.premise, p.hypothesis) for p in req.pairs]
    results = await _classifier.predict_nli_batch(pairs)
    return NLIBatchResponse(results=results)


@app.get("/health", tags=["infra"])
def health() -> dict[str, str]:
    """Liveness: não carrega o modelo (isso só acontece na 1ª classificação)."""
    return {"status": "ok"}
