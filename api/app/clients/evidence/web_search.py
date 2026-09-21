"""Busca de notícias com cache limitado e fallback sem chave."""

import asyncio
import logging
from collections import OrderedDict
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from time import monotonic

import httpx

from app.clients.evidence.base import EvidenceSource
from app.core.config import Settings
from app.domain.entities import Evidence

logger = logging.getLogger(__name__)


def parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        date = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            date = parsedate_to_datetime(value)
        except (ValueError, TypeError):
            return None
    return date.replace(tzinfo=UTC) if date.tzinfo is None else date.astimezone(UTC)


class CachedSource(EvidenceSource):
    def __init__(self, settings: Settings):
        self.settings = settings
        self._cache: OrderedDict[tuple, tuple[float, list[Evidence]]] = OrderedDict()
        self._lock = asyncio.Lock()

    async def search(self, query: str, *, limit: int = 5) -> list[Evidence]:
        query = " ".join(query.split())
        if not query or limit <= 0 or not self.enabled:
            return []
        limit = min(limit, 20)
        key = (query, limit)
        async with self._lock:
            cached = self._cache.get(key)
            if cached and cached[0] > monotonic():
                self._cache.move_to_end(key)
                return list(cached[1])
            result = await self._search(query, limit)
            self._cache[key] = (monotonic() + self.settings.web_cache_ttl_seconds, result)
            self._cache.move_to_end(key)
            while len(self._cache) > self.settings.web_cache_max_entries:
                self._cache.popitem(last=False)
            return list(result)

    @property
    def enabled(self) -> bool:
        raise NotImplementedError

    async def _search(self, query: str, limit: int) -> list[Evidence]:
        raise NotImplementedError


class TavilyClient(CachedSource):
    name = "tavily"

    def __init__(self, settings: Settings, *, transport=None):
        super().__init__(settings)
        self.transport = transport
        self._unavailable_until = 0.0

    @property
    def enabled(self) -> bool:
        return self.settings.tavily_enabled and bool(self.settings.tavily_api_key)

    async def _search(self, query: str, limit: int) -> list[Evidence]:
        if monotonic() < self._unavailable_until:
            raise RuntimeError("Tavily em espera após limite de uso")
        async with httpx.AsyncClient(
            timeout=self.settings.evidence_timeout_seconds, transport=self.transport
        ) as client:
            response = await client.post(
                "https://api.tavily.com/search",
                headers={"Authorization": f"Bearer {self.settings.tavily_api_key}"},
                json={
                    "query": query,
                    "topic": "news",
                    "search_depth": "basic",
                    "days": self.settings.web_search_days,
                    "max_results": limit,
                },
            )
        if response.status_code in (429, 432, 433):
            self._unavailable_until = monotonic() + self.settings.tavily_cooldown_seconds
        response.raise_for_status()
        return [
            Evidence(
                source=self.name,
                url=row["url"],
                title=row.get("title", ""),
                snippet=row.get("content", ""),
                published_at=parse_date(row.get("published_date")),
            )
            for row in response.json().get("results", [])
            if row.get("url")
        ][:limit]


class DuckDuckGoClient(CachedSource):
    name = "duckduckgo"

    def __init__(self, settings: Settings, *, search_fn=None):
        super().__init__(settings)
        self.search_fn = search_fn

    @property
    def enabled(self) -> bool:
        return self.settings.duckduckgo_enabled

    def _web(self, query, limit):
        from ddgs import DDGS
        from ddgs.exceptions import DDGSException

        client = DDGS(timeout=int(self.settings.evidence_timeout_seconds))
        for method in (client.news, client.text):
            try:
                rows = method(query, region="br-pt", max_results=limit, backend="duckduckgo")
            except DDGSException as exc:
                # ddgs usa a exceção base também para uma resposta legitimamente vazia.
                # Não confundir subclasses (timeout/cota) ou outros erros com esse caso.
                is_empty = (
                    type(exc) is DDGSException
                    and str(exc).strip().rstrip(".").lower() == "no results found"
                )
                if is_empty:
                    rows = []
                else:
                    raise
            if rows:
                return rows
        return []

    async def _search(self, query: str, limit: int) -> list[Evidence]:
        rows = await asyncio.to_thread(self.search_fn or self._web, query, limit)
        return [
            Evidence(
                source=self.name,
                url=row.get("url") or row.get("href", ""),
                title=row.get("title", ""),
                snippet=row.get("body", ""),
                published_at=parse_date(row.get("date")),
            )
            for row in rows
            if row.get("url") or row.get("href")
        ][:limit]


class EvidenceSearchUnavailable(RuntimeError):
    """Nenhum resultado utilizável e ao menos um provedor falhou."""


class WebSearchSource(EvidenceSource):
    """Usar esta fonte no pipeline para aplicar a ordem Tavily → DuckDuckGo."""

    name = "web_search"

    def __init__(self, settings: Settings, *, tavily=None, duckduckgo=None, raise_on_failure=False):
        self.raise_on_failure = raise_on_failure
        self.tavily = tavily or TavilyClient(settings)
        self.duckduckgo = duckduckgo or DuckDuckGoClient(settings)

    async def search(self, query: str, *, limit: int = 5) -> list[Evidence]:
        failures = []
        for source in (self.tavily, self.duckduckgo):
            try:
                result = await source.search(query, limit=limit)
                if result:
                    return result
            except Exception as exc:
                # Não registrar URL/body de exceções: podem conter credenciais e consultas.
                failures.append(source.name)
                logger.warning("Fonte %s indisponível (%s)", source.name, type(exc).__name__)
        if failures and self.raise_on_failure:
            raise EvidenceSearchUnavailable("Falha ao consultar: " + ", ".join(failures))
        return []
