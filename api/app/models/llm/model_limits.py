"""Limites de contexto resolvidos pelo catálogo instalado do LiteLLM."""

import logging

import litellm

logger = logging.getLogger(__name__)


def get_max_input_tokens(model: str, fallback: int) -> int:
    """Retorna o limite de entrada do modelo; usa fallback se o catálogo não o conhecer."""
    try:
        info = litellm.get_model_info(model=model)
        limit = info.get("max_input_tokens")
        if isinstance(limit, int) and limit > 0:
            return limit
    except Exception as exc:
        logger.info("LiteLLM não informou limite para %s: %s", model, type(exc).__name__)
    return fallback
