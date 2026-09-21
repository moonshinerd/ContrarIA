"""Worker de longa duração: roda o pipeline do ContrarIA em loop.

Esqueleto -- cada etapa entra pela issue correspondente (coleta, triagem,
bot score, verificação, intervenção). Rode com `python -m app.worker`.
"""

import asyncio
import logging
from time import monotonic

from sqlalchemy import create_engine

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.jobs.ingest_fact_articles import FeedIngestor
from app.repositories.fact_articles import FactArticleRepository

logger = logging.getLogger("contraria.worker")


async def main() -> None:
    settings = get_settings()
    configure_logging(settings)
    logger.info("worker started", extra={"tick_seconds": settings.worker_tick_seconds})
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    ingestor = FeedIngestor(settings, FactArticleRepository(engine))
    next_ingestion = 0.0
    try:
        while True:
            if settings.rss_checkers_enabled and monotonic() >= next_ingestion:
                try:
                    report = await ingestor.run()
                    logger.info("Coleta RSS: %s", report)
                except Exception as exc:
                    logger.error("Falha no job RSS (%s)", type(exc).__name__)
                next_ingestion = monotonic() + settings.rss_poll_seconds
            await asyncio.sleep(settings.worker_tick_seconds)
    finally:
        engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
