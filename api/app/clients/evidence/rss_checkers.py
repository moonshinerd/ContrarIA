import asyncio

from app.clients.evidence.base import EvidenceSource
from app.clients.evidence.embeddings import LocalEmbedder
from app.core.config import Settings
from app.domain.entities import Evidence
from app.repositories.fact_articles import FactArticleRepository


class RSSCheckersSource(EvidenceSource):
    name = "rss_checkers"

    def __init__(self, settings: Settings, *, repository=None, embedder=None):
        self.settings = settings
        if repository is None:
            from sqlalchemy import create_engine

            repository = FactArticleRepository(
                create_engine(settings.database_url, pool_pre_ping=True)
            )
        self.repository = repository
        self.embedder = embedder or LocalEmbedder()

    async def search(self, query: str, *, limit: int = 5) -> list[Evidence]:
        if not self.settings.rss_checkers_enabled or not query.strip() or limit <= 0:
            return []
        if not self.settings.rss_enabled_sources:
            return []
        vector = (await asyncio.to_thread(self.embedder.encode, [query]))[0]
        return await asyncio.to_thread(
            self.repository.search,
            vector,
            sources=self.settings.rss_enabled_sources,
            limit=min(limit, 100),
            weight=self.settings.rss_recency_weight,
            half_life=self.settings.rss_recency_half_life_days,
            min_similarity=self.settings.rss_min_similarity,
        )
