import asyncio
import html
import logging
import re
from urllib.parse import quote

import httpx

from app.clients.evidence.base import EvidenceSource
from app.clients.evidence.cache import TTLCache
from app.domain.entities import Evidence

logger = logging.getLogger(__name__)

_TAGS = re.compile(r"<[^>]+>")


class WikipediaClient(EvidenceSource):
    """Cliente para a API pública da Wikipédia em Português com cache.

    Busca em duas etapas (list=search + page/summary). Falhas são logadas e a
    fonte devolve lista vazia; se só o summary falhar, usa o snippet da busca.
    """

    name: str = "wikipedia"

    def __init__(
        self,
        timeout: float = 10.0,
        ttl_seconds: int = 3600,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.timeout = timeout
        self.transport = transport
        self.base_search_url = "https://pt.wikipedia.org/w/api.php"
        self.base_summary_url = "https://pt.wikipedia.org/api/rest_v1/page/summary"
        # Política da Wikimedia: User-Agent identificável com forma de contato
        self.headers = {"User-Agent": "ContrarIABot/1.0 (https://github.com/moonshinerd/ContrarIA)"}
        self.cache = TTLCache(ttl_seconds=ttl_seconds)

    async def search(self, query: str, *, limit: int = 5) -> list[Evidence]:
        cache_key = f"{query}:{limit}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return list(cached)

        params = {
            "action": "query",
            "list": "search",
            "srsearch": query,
            "format": "json",
            "srlimit": limit,
        }

        async with httpx.AsyncClient(
            timeout=self.timeout, headers=self.headers, transport=self.transport
        ) as client:
            try:
                resp = await client.get(self.base_search_url, params=params)
                resp.raise_for_status()
                results = resp.json().get("query", {}).get("search", [])
            except (httpx.HTTPError, ValueError) as exc:
                logger.warning("Wikipédia: busca falhou: %s", _describe(exc))
                return []

            titled = [item for item in results if item.get("title")]
            evidences = list(await asyncio.gather(*(self._to_evidence(client, i) for i in titled)))

        self.cache.set(cache_key, evidences)
        return list(evidences)

    async def _to_evidence(self, client: httpx.AsyncClient, item: dict) -> Evidence:
        title = item["title"]
        slug = quote(title.replace(" ", "_"), safe="")
        page_url = f"https://pt.wikipedia.org/wiki/{slug}"
        snippet = html.unescape(_TAGS.sub("", item.get("snippet", "")))

        try:
            resp = await client.get(f"{self.base_summary_url}/{slug}")
            resp.raise_for_status()
            summary = resp.json()
            snippet = summary.get("extract") or snippet
            page_url = summary.get("content_urls", {}).get("desktop", {}).get("page", page_url)
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("Wikipédia: summary de %r falhou: %s", title, _describe(exc))

        return Evidence(
            source=self.name,
            url=page_url,
            title=title,
            snippet=snippet.strip(),
            published_at=None,
            rating=None,
        )


def _describe(exc: Exception) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        return f"HTTP {exc.response.status_code}"
    return type(exc).__name__
