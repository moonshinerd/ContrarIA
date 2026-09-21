import asyncio

import httpx
import pytest

from app.clients.evidence.rss_checkers import RSSCheckersSource
from app.core.config import Settings
from app.jobs.ingest_fact_articles import FeedIngestor, parse_articles

RSS = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>Teste</title>
<item><title>Urnas &amp; votos</title><link>https://example.org/1#ref</link>
<description>&lt;p&gt;Resumo limpo&lt;/p&gt;</description>
<pubDate>Mon, 21 Sep 2026 12:00:00 GMT</pubDate></item>
<item><title>Sem data</title><link>https://example.org/2</link></item>
<item><title>Invalido</title><link>javascript:alert(1)</link></item>
</channel></rss>"""


class MemoryRepository:
    def __init__(self):
        self.rows = {}

    def unchanged(self, article):
        return all(self.rows.get(article["url"], {}).get(k) == v for k, v in article.items())

    def upsert(self, articles):
        self.rows.update({a["url"]: a.copy() for a in articles})
        return len(articles)

    def count(self):
        return len(self.rows)


class FakeEmbedder:
    def __init__(self):
        self.calls = []

    def encode(self, texts):
        self.calls.extend(texts)
        return [[1.0] + [0.0] * 383 for _ in texts]


def test_parser_strips_html_and_preserves_date():
    articles = parse_articles(RSS, "test")
    assert len(articles) == 2
    assert articles[0]["url"] == "https://example.org/1"
    assert articles[0]["summary"] == "Resumo limpo"
    assert articles[0]["published_at"].hour == 12
    assert articles[1]["published_at"] is None
    with pytest.raises(ValueError, match="RSS/Atom"):
        parse_articles(b"<html>login</html>", "test")


def test_ingestion_idempotent_and_partial_failure():
    config = Settings(
        _env_file=None,
        rss_enabled_sources=["good", "bad", "unknown"],
        rss_feed_urls={"good": "https://example.org/good", "bad": "https://example.org/bad"},
    )
    repo, embedder = MemoryRepository(), FakeEmbedder()
    transport = httpx.MockTransport(
        lambda r: httpx.Response(200 if r.url.path == "/good" else 503, content=RSS)
    )
    job = FeedIngestor(config, repo, embedder=embedder, transport=transport)

    async def run():
        first = await job.run()
        second = await job.run()
        assert first["updated"] == 2
        assert second["updated"] == 0
        assert second["total"] == 2
        assert set(second["errors"]) == {"bad", "unknown"}

    asyncio.run(run())
    assert len(embedder.calls) == 2


def test_rss_disabled_never_embeds_or_connects():
    config = Settings(_env_file=None, rss_checkers_enabled=False)
    embedder = FakeEmbedder()
    repo = MemoryRepository()
    source = RSSCheckersSource(config, repository=repo, embedder=embedder)
    assert asyncio.run(source.search("urna")) == []
    assert asyncio.run(FeedIngestor(config, repo, embedder=embedder).run())["updated"] == 0
    assert embedder.calls == []


def test_registry_and_search_config():
    from app.clients.evidence import EVIDENCE_SOURCES, get_evidence_source

    assert {"tavily", "duckduckgo", "web_search", "rss_checkers"} <= set(EVIDENCE_SOURCES)
    config = Settings(_env_file=None, rss_enabled_sources=["aos_fatos"], rss_recency_weight=0.2)

    class SearchRepository:
        def search(self, vector, **kwargs):
            assert len(vector) == 384
            assert kwargs["sources"] == ["aos_fatos"]
            assert kwargs["weight"] == 0.2
            return []

    source = get_evidence_source(
        "rss_checkers", settings=config, repository=SearchRepository(), embedder=FakeEmbedder()
    )
    assert asyncio.run(source.search("alegação")) == []
    with pytest.raises(ValueError, match="Fonte de evidência desconhecida"):
        get_evidence_source("inexistente")
