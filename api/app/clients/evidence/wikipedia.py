import httpx

from app.clients.evidence.base import EvidenceSource
from app.clients.evidence.cache import TTLCache
from app.domain.entities import Evidence


class WikipediaClient(EvidenceSource):
    """Cliente para a API pública da Wikipédia em Português com cache."""

    name: str = "wikipedia"

    def __init__(self, timeout: float = 10.0, ttl_seconds: int = 3600):
        self.timeout = timeout
        self.base_search_url = "https://pt.wikipedia.org/w/api.php"
        self.base_summary_url = "https://pt.wikipedia.org/api/rest_v1/page/summary"
        self.headers = {
            "User-Agent": (
                "ContrarIABot/1.0 (https://github.com/moonshinerd/ContrarIA; contato@contraria.org)"
            )
        }
        self.cache = TTLCache(ttl_seconds=ttl_seconds)

    async def search(self, query: str, *, limit: int = 5) -> list[Evidence]:
        cache_key = f"{query}:{limit}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached

        evidences: list[Evidence] = []
        params = {
            "action": "query",
            "list": "search",
            "srsearch": query,
            "format": "json",
            "srlimit": limit,
        }

        async with httpx.AsyncClient(timeout=self.timeout, headers=self.headers) as client:
            try:
                resp = await client.get(self.base_search_url, params=params)
                resp.raise_for_status()
                data = resp.json()
            except Exception:
                return []

            search_results = data.get("query", {}).get("search", [])

            for item in search_results:
                title = item.get("title")
                if not title:
                    continue

                fallback_page = f"https://pt.wikipedia.org/wiki/{title}"
                raw_snippet = item.get("snippet", "")
                clean_snippet = raw_snippet.replace('<span class="searchmatch">', "").replace(
                    "</span>", ""
                )

                try:
                    summary_resp = await client.get(f"{self.base_summary_url}/{title}")
                    if summary_resp.status_code == 200:
                        sdata = summary_resp.json()
                        snippet = sdata.get("extract", "") or clean_snippet
                        desktop_url = sdata.get("content_urls", {}).get("desktop", {})
                        page_url = desktop_url.get("page", fallback_page)
                    else:
                        snippet = clean_snippet
                        page_url = fallback_page
                except Exception:
                    snippet = clean_snippet
                    page_url = fallback_page

                evidences.append(
                    Evidence(
                        source=self.name,
                        url=page_url,
                        title=title,
                        snippet=snippet.strip(),
                        published_at=None,
                        rating=None,
                    )
                )

        self.cache.set(cache_key, evidences)
        return evidences
