from datetime import datetime
import os
import httpx

from app.domain.entities import Evidence
from app.clients.evidence.base import EvidenceSource
from app.clients.evidence.cache import TTLCache


class GoogleFactCheckClient(EvidenceSource):
    """Cliente para a Google Fact Check Tools API com cache."""

    name: str = "google_factcheck"

    def __init__(self, api_key: str | None = None, timeout: float = 10.0, ttl_seconds: int = 3600):
        self.api_key = api_key or os.getenv("GOOGLE_FACTCHECK_API_KEY") or os.getenv("GOOGLE_FACT_CHECK_API_KEY")
        self.timeout = timeout
        self.base_url = "https://factchecktools.googleapis.com/v1alpha1/claims:search"
        self.cache = TTLCache(ttl_seconds=ttl_seconds)

    async def search(self, query: str, *, limit: int = 5) -> list[Evidence]:
        if not self.api_key:
            return []

        cache_key = f"{query}:{limit}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached

        params = {
            "query": query,
            "languageCode": "pt",
            "pageSize": limit,
            "key": self.api_key,
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                resp = await client.get(self.base_url, params=params)
                resp.raise_for_status()
                data = resp.json()
            except Exception:
                return []

        evidences: list[Evidence] = []
        claims = data.get("claims", [])

        for claim in claims:
            reviews = claim.get("claimReview", [])
            for review in reviews:
                url = review.get("url", "")
                title = review.get("title") or claim.get("text", "")
                rating = review.get("textualRating")
                publisher_name = review.get("publisher", {}).get("name", "Desconhecido")
                snippet = f"Checagem por {publisher_name}: {claim.get('text', '')}"

                published_at = None
                raw_date = review.get("reviewDate")
                if raw_date:
                    try:
                        published_at = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
                    except Exception:
                        published_at = None

                evidences.append(
                    Evidence(
                        source=self.name,
                        url=url,
                        title=title,
                        snippet=snippet.strip(),
                        published_at=published_at,
                        rating=rating,
                    )
                )

                if len(evidences) >= limit:
                    break
            if len(evidences) >= limit:
                break

        self.cache.set(cache_key, evidences)
        return evidences