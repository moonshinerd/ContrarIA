"""Orquestrador do pipeline E2E (Issue #17).

Executa: bot score -> pré-filtro -> prioridade -> verificação -> GQ01.
Grava decisão imutável no log ao final de cada análise.
"""

import logging

from sqlalchemy.orm import Session

from app.clients.bluesky_client import BlueskyClient
from app.clients.ozone_client import OzoneClient
from app.core.config import Settings
from app.db.orm.decisions import DecisionLog
from app.domain.entities import Post, VerdictLabel
from app.services.bot_scoring import BotScoringService
from app.services.intervention import InterventionService
from app.services.verification import VerificationService

logger = logging.getLogger("contraria.services.pipeline")


class PipelineService:
    """Orquestrador do pipeline (Issue #17).

    Executa: bot score -> pré-filtro -> prioridade -> verificação -> GQ01.
    Grava decisão imutável no log.
    """

    def __init__(
        self,
        settings: Settings,
        db_session: Session,
        bluesky: BlueskyClient,
        ozone: OzoneClient,
        bots: BotScoringService,
        verification: VerificationService,
        intervention: InterventionService,
    ) -> None:
        self.settings = settings
        self.db = db_session
        self.bluesky = bluesky
        self.ozone = ozone
        self.bots = bots
        self.verification = verification
        self.intervention = intervention

    async def analyze(self, post: Post) -> DecisionLog:  # noqa: C901
        """Processa um post sob demanda (POST /analyze ou pelo worker)."""
        logger.info("Analisando post: %s", post.uri)

        # 1. Bot score
        author = await self.bluesky.get_profile(post.author_did)
        assessment = await self.bots.get_assessment(post.author_did)
        bot_score = assessment.score

        # 2/3. Engajamento / Prioridade (simplificado)
        # Engajamento alto = ≥1000 seguidores
        high_engagement = author.followers_count >= 1000

        # 4. Verificação
        verdict = await self.verification.verify(post)
        is_adverse = verdict.label in (VerdictLabel.FALSE, VerdictLabel.MISLEADING)
        is_insufficient = verdict.label == VerdictLabel.INSUFFICIENT_EVIDENCE

        # 5. Matriz GQ01
        action = "MONITOR"
        justification = "Condição não coberta pela matriz, monitorando."

        if bot_score > 0.9 and not high_engagement:
            action = "IGNORE"
            justification = "Alto bot score e baixo engajamento. Ignorado para evitar amplificação."
        elif is_insufficient:
            action = "MONITOR"
            justification = "Evidência insuficiente. Apenas monitoramento."
        elif high_engagement and is_adverse:
            action = "INTERVENE"
            justification = (
                "Alto engajamento e veredito adverso. Intervenção (quote) e rótulo aplicados."
            )
            try:
                await self.intervention.execute_intervention(post, author, verdict, bot_score)
                await self.ozone.emit_label(
                    post, label_val="possivel-desinformacao", action="create"
                )
            except Exception as e:
                logger.error("Erro na intervenção/rótulo: %s", e)
                action = "ERROR_INTERVENTION"
                justification = str(e)

        evidences = verdict.evidences or []
        decision = DecisionLog(
            post_uri=post.uri,
            post_snapshot={
                "text": post.text,
                "author_did": post.author_did,
                "created_at": post.created_at.isoformat(),
            },
            bot_score=bot_score,
            bot_features=assessment.features,
            sources=[s.__dict__ for s in evidences],
            agent_outputs=verdict.agent_outputs,
            verdict=verdict.label.value,
            confidence=verdict.confidence,
            crc_threshold_used=self.settings.crc_alpha,
            action=action,
            justification=justification,
        )

        self.db.add(decision)
        self.db.commit()
        self.db.refresh(decision)

        return decision
