"""Busca de notícias com cache limitado e fallback sem chave."""

import asyncio
import logging
from collections import OrderedDict
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from time import monotonic
from urllib.parse import urlparse

import httpx

from app.clients.evidence.base import EvidenceSource
from app.core.config import Settings
from app.domain.entities import Evidence

logger = logging.getLogger(__name__)

BLOCKED_EVIDENCE_DOMAINS = {
    "instagram.com",
    "facebook.com",
    "fb.com",
    "tiktok.com",
    "twitter.com",
    "x.com",
    "bsky.app",
    "threads.net",
    "reddit.com",
    "youtube.com",
    "youtu.be",
    "pinterest.com",
}


def is_valid_evidence_url(url: str) -> bool:
    """Rejeita redes sociais e plataformas de UGC como fontes de verificação factual."""
    if not url:
        return False
    try:
        domain = urlparse(url).netloc.lower()
        if domain.startswith("www."):
            domain = domain[4:]
        if domain.startswith("m."):
            domain = domain[2:]
        for blocked in BLOCKED_EVIDENCE_DOMAINS:
            if domain == blocked or domain.endswith("." + blocked):
                return False
        return True
    except Exception:
        return False


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


class SearXNGClient(CachedSource):
    name = "searxng"

    def __init__(self, settings: Settings, *, transport=None):
        super().__init__(settings)
        self.transport = transport
        self._unavailable_until = 0.0

    @property
    def enabled(self) -> bool:
        if monotonic() < self._unavailable_until:
            return False
        return self.settings.searxng_enabled and bool(self.settings.searxng_base_url)

    async def _search(self, query: str, limit: int) -> list[Evidence]:
        if monotonic() < self._unavailable_until:
            raise RuntimeError("SearXNG temporariamente em espera")

        params: dict[str, str] = {
            "q": query,
            "format": "json",
            "language": self.settings.searxng_language,
        }
        if self.settings.searxng_categories:
            params["categories"] = self.settings.searxng_categories

        base_url = self.settings.searxng_base_url.rstrip("/")
        try:
            async with httpx.AsyncClient(
                timeout=self.settings.evidence_timeout_seconds, transport=self.transport
            ) as client:
                response = await client.get(f"{base_url}/search", params=params)
        except Exception:
            self._unavailable_until = monotonic() + 10.0
            raise

        if response.status_code != 200:
            self._unavailable_until = monotonic() + 10.0
            response.raise_for_status()

        data = response.json()
        raw_results = data.get("results", [])

        evidences: list[Evidence] = []
        seen_urls: set[str] = set()

        for row in raw_results:
            url = row.get("url")
            if not url or url in seen_urls or not is_valid_evidence_url(url):
                continue
            seen_urls.add(url)
            title = (row.get("title") or "").strip()
            content = (row.get("content") or row.get("snippet") or "").strip()
            published_date = row.get("publishedDate") or row.get("pubdate")
            evidences.append(
                Evidence(
                    source=self.name,
                    url=url,
                    title=title,
                    snippet=content,
                    published_at=parse_date(published_date),
                )
            )
            if len(evidences) >= limit:
                break

        return evidences


class TavilyClient(CachedSource):
    name = "tavily"

    def __init__(self, settings: Settings, *, transport=None):
        super().__init__(settings)
        self.transport = transport
        self._unavailable_until = 0.0

    @property
    def enabled(self) -> bool:
        if monotonic() < self._unavailable_until:
            return False
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
            logger.warning(
                "Tavily atingiu limite de créditos/plano (status %d). Em espera por %ds.",
                response.status_code,
                self.settings.tavily_cooldown_seconds,
            )
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
            if row.get("url") and is_valid_evidence_url(row["url"])
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
            if (row.get("url") or row.get("href"))
            and is_valid_evidence_url(row.get("url") or row.get("href", ""))
        ][:limit]


class EvidenceSearchUnavailable(RuntimeError):
    """Nenhum resultado utilizável e ao menos um provedor falhou."""


class WebSearchSource(EvidenceSource):
    """Usar esta fonte no pipeline para aplicar a ordem SearXNG → Tavily → DuckDuckGo."""

    name = "web_search"

    def __init__(
        self,
        settings: Settings,
        *,
        searxng=None,
        tavily=None,
        duckduckgo=None,
        raise_on_failure: bool = False,
    ):
        self.raise_on_failure = raise_on_failure
        if searxng is not None:
            self.searxng = searxng
        elif tavily is not None or duckduckgo is not None:
            self.searxng = None
        else:
            self.searxng = SearXNGClient(settings)

        self.tavily = tavily or TavilyClient(settings)
        self.duckduckgo = duckduckgo or DuckDuckGoClient(settings)

    async def search(self, query: str, *, limit: int = 5) -> list[Evidence]:
        failures = []
        sources = [
            s for s in (self.searxng, self.tavily, self.duckduckgo) if s is not None and s.enabled
        ]
        for source in sources:
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
