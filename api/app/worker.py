"""Worker de longa duração: roda o pipeline do ContrarIA em loop.

Esqueleto -- cada etapa entra pela issue correspondente (coleta, triagem,
bot score, verificação, intervenção). Rode com `python -m app.worker`.
"""

import asyncio
import logging
from time import monotonic

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.clients.bluesky_client import BlueskyClient
from app.clients.ozone_client import OzoneClient
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.jobs.collector import JetstreamConsumer, SearchPoller
from app.jobs.ingest_fact_articles import FeedIngestor
from app.models.llm.litellm_model import LiteLLMModel
from app.repositories.fact_articles import FactArticleRepository
from app.repositories.interventions import InterventionRepository
from app.repositories.posts import PostRepository
from app.services.bot_scoring import BotScoringService
from app.services.intervention import InterventionService
from app.services.pipeline import PipelineService
from app.services.verification import VerificationService

logger = logging.getLogger("contraria.worker")


async def main() -> None:
    settings = get_settings()
    configure_logging(settings)
    logger.info("worker started", extra={"tick_seconds": settings.worker_tick_seconds})
    engine = create_engine(settings.database_url, pool_pre_ping=True)

    # Repositórios e Clientes
    bsky_client = BlueskyClient(settings)
    post_repo = PostRepository(engine)

    ingestor = FeedIngestor(settings, FactArticleRepository(engine))
    jetstream = JetstreamConsumer(post_repo)
    poller = SearchPoller(post_repo, bsky_client, poll_interval_seconds=600)
    llm = LiteLLMModel(settings)
    pipeline = PipelineService(
        settings=settings,
        db_session=Session(engine),
        bluesky=bsky_client,
        ozone=OzoneClient(bsky_client.get_auth_client()),
        bots=BotScoringService(engine, bsky_client),
        verification=VerificationService.from_settings(llm, settings=settings, engine=engine),
        intervention=InterventionService(InterventionRepository(engine), bsky_client, llm),
    )

    # Inicia as tasks em background
    jetstream_task = asyncio.create_task(jetstream.run())
    poller_task = asyncio.create_task(poller.run())

    from app.jobs.refresh_engagement import EngagementRefresher

    refresher = EngagementRefresher(engine, bsky_client)
    refresher_task = asyncio.create_task(refresher.run())

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
            candidates = post_repo.get_triage_candidates(settings.worker_pipeline_batch_size)
            for post, _relevance in candidates:
                try:
                    decision = await pipeline.analyze(post)
                    status = "ignored" if decision.action == "IGNORE" else "processed"
                    post_repo.update_triage(post.uri, status=status, priority=0.0)
                except Exception:
                    logger.exception("Falha no pipeline GQ01 para %s", post.uri)
            await asyncio.sleep(settings.worker_tick_seconds)
    finally:
        jetstream_task.cancel()
        poller_task.cancel()
        refresher_task.cancel()
        engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
