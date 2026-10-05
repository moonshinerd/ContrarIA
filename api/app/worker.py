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
from app.jobs.collector import IngestGate, JetstreamConsumer, SearchPoller
from app.jobs.ingest_fact_articles import FeedIngestor
from app.models.llm.litellm_model import LiteLLMModel
from app.repositories.crc_calibration import CRCCalibrationRepository
from app.repositories.fact_articles import FactArticleRepository
from app.repositories.interventions import InterventionRepository
from app.repositories.posts import PostRepository
from app.services import build_verification_service
from app.services.account_labeling import AccountLabelService
from app.services.analysis_pool import AnalysisPool
from app.services.bot_scoring import BotScoringService
from app.services.crc_seed import ensure_calibration_seeded
from app.services.intervention import InterventionService
from app.services.intervention_queue import InterventionQueue, expire_stale_candidates
from app.services.pipeline import PipelineService

logger = logging.getLogger("contraria.worker")


async def run_due_intervention_round(
    queue: InterventionQueue,
    next_round: float,
    round_seconds: float,
    *,
    now: float | None = None,
) -> float:
    """Publica a rodada vencida sem deixar um lote lento segurar a fila."""
    current = monotonic() if now is None else now
    if current < next_round:
        return next_round
    try:
        await queue.run_round()
    except Exception:
        logger.exception("Falha na rodada de intervenção")
        queue.db.rollback()
    return current + round_seconds


async def main() -> None:
    settings = get_settings()
    configure_logging(settings)
    logger.info("worker started", extra={"tick_seconds": settings.worker_tick_seconds})
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    ensure_calibration_seeded(CRCCalibrationRepository(engine), settings)

    # Repositórios e Clientes
    bsky_client = BlueskyClient(settings)
    post_repo = PostRepository(engine)

    ingestor = FeedIngestor(settings, FactArticleRepository(engine))
    if settings.worker_queue_max_pending > 0:
        expired = post_repo.trim_pending(settings.worker_queue_max_pending)
        if expired:
            logger.warning(
                "Fila acima do teto de %d: %d post(s) de menor prioridade expirados",
                settings.worker_queue_max_pending,
                expired,
            )
    gate = IngestGate(
        post_repo,
        settings.worker_queue_max_pending,
        search_reserve=settings.worker_queue_search_reserve,
    )
    jetstream = JetstreamConsumer(post_repo, gate=gate)
    poller = SearchPoller(post_repo, bsky_client, poll_interval_seconds=600, gate=gate)
    llm = LiteLLMModel(settings)
    ozone = OzoneClient(settings=settings)
    intervention = InterventionService(InterventionRepository(engine), bsky_client, llm)
    queue_session = Session(engine)
    expired = expire_stale_candidates(queue_session)
    if expired:
        logger.warning("%d candidato(s) de intervenção expirado(s) ao iniciar", expired)
    queue = InterventionQueue(settings, queue_session, intervention, ozone)
    pipeline = PipelineService(
        settings=settings,
        db_session=Session(engine),
        bluesky=bsky_client,
        ozone=ozone,
        bots=BotScoringService(engine, bsky_client),
        verification=build_verification_service(llm, settings=settings, engine=engine),
        intervention=intervention,
        intervention_queue=queue,
        account_labels=AccountLabelService(settings, Session(engine), ozone),
    )

    # Inicia as tasks em background
    jetstream_task = asyncio.create_task(jetstream.run())
    poller_task = asyncio.create_task(poller.run())

    from app.jobs.refresh_engagement import EngagementRefresher

    refresher = EngagementRefresher(engine, bsky_client)
    refresher_task = asyncio.create_task(refresher.run())

    pool = AnalysisPool(
        post_repo,
        pipeline,
        concurrency=settings.worker_pipeline_concurrency,
        tick_seconds=settings.worker_tick_seconds,
        max_attempts=settings.worker_pipeline_max_attempts,
    )
    logger.info(
        "pool de análises: concorrência=%d, fila máxima=%d",
        settings.worker_pipeline_concurrency,
        settings.worker_queue_max_pending,
    )
    next_ingestion = 0.0
    round_seconds = settings.intervention_round_minutes * 60
    next_round = monotonic() + round_seconds
    try:
        while True:
            next_round = await run_due_intervention_round(queue, next_round, round_seconds)
            if settings.rss_checkers_enabled and monotonic() >= next_ingestion:
                try:
                    report = await ingestor.run()
                    logger.info("Coleta RSS: %s", report)
                except Exception as exc:
                    logger.error("Falha no job RSS (%s)", type(exc).__name__)
                next_ingestion = monotonic() + settings.rss_poll_seconds
            await pool.step()
    finally:
        pool.cancel()
        jetstream_task.cancel()
        poller_task.cancel()
        refresher_task.cancel()
        engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
