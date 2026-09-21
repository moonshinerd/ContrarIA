"""Executar com python -m app.jobs.ingest_fact_articles [--min-articles 100]."""

import argparse
import asyncio
import calendar
import json
import logging
from datetime import UTC, datetime
from html.parser import HTMLParser
from urllib.parse import urlsplit, urlunsplit

import feedparser
import httpx
from bs4 import BeautifulSoup
from curl_cffi.requests import AsyncSession
from sqlalchemy import create_engine

from app.clients.evidence.embeddings import LocalEmbedder
from app.clients.evidence.feeds import FEEDS
from app.core.config import Settings, get_settings
from app.repositories.fact_articles import FactArticleRepository

logger = logging.getLogger(__name__)


class PlainText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def clean_text(value: str) -> str:
    parser = PlainText()
    parser.feed(value)
    return " ".join(" ".join(parser.parts).split())


def parse_articles(content: bytes, source: str) -> list[dict]:
    feed = feedparser.parse(content)
    if not feed.version:
        raise ValueError("Resposta não é RSS/Atom")
    articles = {}
    for item in feed.entries:
        url = item.get("link", "")
        parts = urlsplit(url)
        if parts.scheme not in ("http", "https") or not parts.netloc:
            continue
        url = urlunsplit(parts._replace(fragment=""))
        title = clean_text(item.get("title", ""))
        if not title:
            continue
        date = item.get("published_parsed") or item.get("updated_parsed")
        # Apenas resumo do feed: não guardar íntegra de artigos.
        summary = clean_text(item.get("summary", ""))[:3000]
        articles[url] = dict(
            url=url,
            source=source,
            title=title,
            summary=summary,
            published_at=datetime.fromtimestamp(calendar.timegm(date), UTC) if date else None,
        )
    return list(articles.values())


async def _fetch_custom_source(source: str, url: str, timeout: float) -> list[dict]:
    async with AsyncSession(impersonate="chrome120", timeout=timeout) as session:
        response = await session.get(url)
        response.raise_for_status()

    if source == "uol_confere":
        soup = BeautifulSoup(response.content, "lxml")
        articles = []
        for a in soup.select("a[href]"):
            href = a["href"]
            if "noticias.uol.com.br/confere/ultimas-noticias" in href and a.text.strip():
                articles.append(
                    {
                        "url": href,
                        "source": source,
                        "title": clean_text(a.text),
                        "summary": "",
                        "published_at": None,
                    }
                )
        return list({a["url"]: a for a in articles}.values())

    if source == "estadao_verifica":
        soup = BeautifulSoup(response.content, "lxml")
        articles = []
        for a in soup.select("a[href]"):
            href = a["href"]
            if "/estadao-verifica/" in href and a.text.strip() and len(a.text.strip()) > 20:
                if not href.startswith("http"):
                    href = "https://www.estadao.com.br" + href
                articles.append(
                    {
                        "url": href,
                        "source": source,
                        "title": clean_text(a.text),
                        "summary": "",
                        "published_at": None,
                    }
                )
        return list({a["url"]: a for a in articles}.values())

    return parse_articles(response.content, source)


class FeedIngestor:
    def __init__(self, settings: Settings, repository, *, embedder=None, transport=None):
        self.settings = settings
        self.repository = repository
        self.embedder = embedder or LocalEmbedder()
        self.transport = transport

    async def run(self) -> dict:
        report = {"updated": 0, "feeds": {}, "errors": {}}
        if not self.settings.rss_checkers_enabled:
            return report
        urls = FEEDS | self.settings.rss_feed_urls
        async with httpx.AsyncClient(
            timeout=self.settings.evidence_timeout_seconds,
            follow_redirects=True,
            headers={"User-Agent": "ContrarIA/0.1 (+https://github.com/moonshinerd/ContrarIA)"},
            transport=self.transport,
        ) as client:
            for source in self.settings.rss_enabled_sources:
                url = urls.get(source)
                if not url:
                    report["errors"][source] = "Feed sem URL confirmada; configure RSS_FEED_URLS"
                    continue
                try:
                    if source in ("tse", "estadao_verifica", "uol_confere"):
                        articles = await _fetch_custom_source(
                            source, url, self.settings.evidence_timeout_seconds
                        )
                    else:
                        response = await client.get(url)
                        response.raise_for_status()
                        articles = parse_articles(response.content, source)
                    report["feeds"][source] = len(articles)
                    pending = []
                    for article in articles:
                        if not await asyncio.to_thread(self.repository.unchanged, article):
                            pending.append(article)
                    for start in range(0, len(pending), 32):
                        batch = pending[start : start + 32]
                        vectors = await asyncio.to_thread(
                            self.embedder.encode,
                            [a["title"] + ". " + a["summary"] for a in batch],
                        )
                        for article, vector in zip(batch, vectors, strict=True):
                            article["embedding"] = vector
                        report["updated"] += await asyncio.to_thread(self.repository.upsert, batch)
                except Exception as exc:
                    report["errors"][source] = type(exc).__name__
                    logger.warning("Falha no feed %s (%s)", source, type(exc).__name__)
        report["total"] = await asyncio.to_thread(self.repository.count)
        return report


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--min-articles", type=int, default=0)
    args = parser.parse_args()
    settings = get_settings()
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    try:
        report = await FeedIngestor(settings, FactArticleRepository(engine)).run()
        print(json.dumps(report, ensure_ascii=False, indent=2))
        if report.get("total", 0) < args.min_articles:
            raise SystemExit(1)
    finally:
        engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
