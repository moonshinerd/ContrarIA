import logging
import time
from datetime import datetime

import httpx

from app.clients.evidence.base import EvidenceSource
from app.clients.evidence.cache import TTLCache
from app.clients.evidence.ratelimit import RateLimiter
from app.core.config import get_settings
from app.domain.entities import Evidence

logger = logging.getLogger(__name__)

DEFAULT_COOLDOWN_SECONDS = 60.0


class GoogleFactCheckClient(EvidenceSource):
    """Cliente para a Google Fact Check Tools API (claims:search) com cache.

    Falhas (chave ausente ou inválida, cota, rede) são logadas e devolvem lista
    vazia: quem chama trata "sem evidência" como incerteza, nunca como erro fatal.

    Cota do Google: 300 req/min (sem limite diário). O `RateLimiter` mantém o
    cliente abaixo disso, e um HTTP 429 abre uma pausa (respeita `Retry-After`)
    em que nenhuma requisição é feita.
    """

    name: str = "google_factcheck"

    def __init__(
        self,
        api_key: str | None = None,
        timeout: float = 10.0,
        ttl_seconds: int = 3600,
        max_age_days: int | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        rate_limiter: RateLimiter | None = None,
    ):
        settings = get_settings()
        self.api_key = api_key if api_key is not None else settings.google_factcheck_api_key
        self.rate_limiter = rate_limiter or RateLimiter(settings.google_factcheck_rate_per_minute)
        self._blocked_until = 0.0
        self.timeout = timeout
        self.max_age_days = max_age_days
        self.transport = transport
        self.base_url = "https://factchecktools.googleapis.com/v1alpha1/claims:search"
        self.cache = TTLCache(ttl_seconds=ttl_seconds)

    async def search(self, query: str, *, limit: int = 5) -> list[Evidence]:
        if not self.api_key:
            logger.warning("GOOGLE_FACTCHECK_API_KEY ausente: fonte google_factcheck desativada")
            return []

        cache_key = f"{' '.join(query.split()).casefold()}:{limit}:{self.max_age_days}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return list(cached)

        if time.monotonic() < self._blocked_until:
            logger.warning("Google Fact Check em pausa após HTTP 429: consulta ignorada")
            return []

        params: dict[str, str | int] = {
            "query": query,
            "languageCode": "pt",
            "pageSize": limit,
            "key": self.api_key,
        }
        if self.max_age_days is not None:
            params["maxAgeDays"] = self.max_age_days

        try:
            await self.rate_limiter.acquire()
            async with httpx.AsyncClient(timeout=self.timeout, transport=self.transport) as client:
                resp = await client.get(self.base_url, params=params)
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPStatusError as exc:
            # não loga a URL: ela carrega a chave na query string
            logger.warning("Google Fact Check respondeu HTTP %s", exc.response.status_code)
            if exc.response.status_code == 429:
                self._blocked_until = time.monotonic() + _retry_after(exc.response)
            return []
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("Google Fact Check falhou: %s", type(exc).__name__)
            return []

        evidences: list[Evidence] = []
        for claim in data.get("claims", []):
            for review in claim.get("claimReview", []):
                publisher = review.get("publisher", {}).get("name", "Desconhecido")
                evidences.append(
                    Evidence(
                        source=self.name,
                        url=review.get("url", ""),
                        title=review.get("title") or claim.get("text", ""),
                        snippet=f"Checagem por {publisher}: {claim.get('text', '')}".strip(),
                        published_at=_parse_date(review.get("reviewDate")),
                        rating=review.get("textualRating"),
                    )
                )
                if len(evidences) >= limit:
                    break
            if len(evidences) >= limit:
                break

        self.cache.set(cache_key, evidences)
        return list(evidences)


def _parse_date(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def _retry_after(response: httpx.Response) -> float:
    try:
        return max(float(response.headers["Retry-After"]), 1.0)
    except (KeyError, ValueError):
        return DEFAULT_COOLDOWN_SECONDS
