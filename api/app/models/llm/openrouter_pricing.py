"""Preço dos modelos segundo o próprio OpenRouter.

O catálogo do litellm não conhece os preços via OpenRouter (devolve custo 0 ou erro), e isso
desligava na prática a trava de orçamento diário. O OpenRouter informa o custo de cada chamada
em ``usage.cost`` quando a requisição pede ``usage: {include: true}``; esta tabela é a reserva,
com o preço publicado em ``/api/v1/models`` vezes os tokens da resposta.
"""

import logging
import time

import httpx

logger = logging.getLogger(__name__)

MODELS_URL = "https://openrouter.ai/api/v1/models"
_TTL_SECONDS = 24 * 3600
_cache: dict = {"at": float("-inf"), "prices": {}}


def _fetch() -> dict[str, tuple[float, float]]:
    response = httpx.get(MODELS_URL, timeout=15)
    response.raise_for_status()
    prices: dict[str, tuple[float, float]] = {}
    for item in response.json().get("data", []):
        pricing = item.get("pricing") or {}
        try:
            prices[item["id"]] = (float(pricing["prompt"]), float(pricing["completion"]))
        except (KeyError, TypeError, ValueError):
            continue
    return prices


def openrouter_prices(fetch=_fetch) -> dict[str, tuple[float, float]]:
    """Preço em USD por token (entrada, saída), por id do OpenRouter. Cache de 24 h."""
    if time.monotonic() - _cache["at"] < _TTL_SECONDS and _cache["prices"]:
        return _cache["prices"]
    try:
        _cache["prices"] = fetch()
    except Exception as exc:
        # Sem rede, mantém a tabela anterior (se houver) e tenta de novo na próxima vez.
        logger.warning("Não foi possível obter preços do OpenRouter: %s", type(exc).__name__)
        return _cache["prices"]
    _cache["at"] = time.monotonic()
    return _cache["prices"]


def estimate_cost(
    model: str, tokens_in: int, tokens_out: int, prices: dict[str, tuple[float, float]]
) -> float | None:
    """Custo pela tabela do OpenRouter; None se o modelo não estiver nela."""
    model_id = model.removeprefix("openrouter/")
    if model_id not in prices:
        return None
    price_in, price_out = prices[model_id]
    return tokens_in * price_in + tokens_out * price_out
