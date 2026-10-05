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
from app.services.account_labeling import AccountLabelService
from app.services.bot_scoring import BotScoringService
from app.services.intervention import InterventionService
from app.services.intervention_queue import InterventionCandidate, InterventionQueue
from app.services.jev_verification import JevVerificationService
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
        verification: VerificationService | JevVerificationService,
        intervention: InterventionService,
        intervention_queue: InterventionQueue | None = None,
        account_labels: AccountLabelService | None = None,
    ) -> None:
        self.settings = settings
        self.db = db_session
        self.bluesky = bluesky
        self.ozone = ozone
        self.bots = bots
        self.verification = verification
        self.intervention = intervention
        # Com fila (worker), o candidato espera a rodada em vez de ser publicado já.
        self.intervention_queue = intervention_queue
        self.account_labels = account_labels

    async def analyze(self, post: Post) -> DecisionLog:  # noqa: C901
        """Processa um post sob demanda (POST /analyze ou pelo worker)."""
        logger.info("Analisando post: %s", post.uri)

        # 1. Bot score
        author = await self.bluesky.get_profile(post.author_did)
        bot_scoring_enabled = getattr(self.settings, "pipeline_bot_scoring_enabled", True)
        if bot_scoring_enabled:
            assessment = await self.bots.get_assessment(post.author_did)
        else:
            assessment = None
        bot_score = assessment.score if assessment else None
        if assessment is not None and self.account_labels is not None:
            try:
                await self.account_labels.sync(author, assessment.score)
            except Exception:
                logger.exception("Falha ao sincronizar rótulo da conta %s", post.author_did)

        # 2/3. Engajamento / Prioridade (simplificado)
        # Engajamento alto = ≥1000 seguidores
        high_engagement = author.followers_count >= getattr(
            self.settings, "pipeline_min_followers_for_intervention", 1000
        )

        # 4. Verificação
        verification_enabled = getattr(self.settings, "pipeline_verification_enabled", True)
        if not verification_enabled:
            raise RuntimeError("Pipeline de verificação está desabilitado")
        await self._attach_links(post)
        thread_context = await self._thread_context(post)
        verdict = await self.verification.verify(post, parent_text=thread_context)
        is_adverse = verdict.label in (VerdictLabel.FALSE, VerdictLabel.MISLEADING)
        is_insufficient = verdict.label == VerdictLabel.INSUFFICIENT_EVIDENCE

        # 5. Matriz GQ01
        action = "MONITOR"
        justification = "Condição não coberta pela matriz, monitorando."

        if (
            bot_score is not None
            and bot_score > getattr(self.settings, "pipeline_bot_ignore_threshold", 0.9)
            and not high_engagement
        ):
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
                if not getattr(self.settings, "pipeline_intervention_enabled", True):
                    action = "MONITOR"
                    justification = (
                        "Intervenção desabilitada por feature flag. Apenas monitoramento."
                    )
                elif self.intervention_queue is not None:
                    action = "INTERVENE_QUEUED"
                    justification = "Veredito adverso: candidato à próxima rodada de intervenção."
                else:
                    intervention_result = await self.intervention.execute_intervention(
                        post, author, verdict, bot_score or 0.0
                    )
                    if (
                        intervention_result
                        and not getattr(self.settings, "intervention_dry_run", True)
                        and getattr(self.settings, "pipeline_labeler_enabled", False)
                    ):
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
                "cid": post.cid,
                "created_at": post.created_at.isoformat(),
                "thread_context": thread_context,
            },
            bot_score=bot_score,
            bot_features=assessment.features if assessment else None,
            sources=[
                {
                    **s.__dict__,
                    "published_at": s.published_at.isoformat() if s.published_at else None,
                }
                for s in evidences
            ],
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

        if action == "INTERVENE_QUEUED" and self.intervention_queue is not None:
            self.intervention_queue.add(
                InterventionCandidate(decision.id, post, author, verdict, bot_score or 0.0)
            )

        return decision

    async def _attach_links(self, post: Post) -> None:
        """Busca no Bluesky as URLs que o post cita (card de link), que o texto não traz."""
        if post.links:
            return
        try:
            hydrated = await self.bluesky.get_posts([post.uri])
        except Exception as exc:
            logger.warning("Falha ao buscar links de %s: %s", post.uri, type(exc).__name__)
            return
        if hydrated:
            post.links = hydrated[0].links

    async def _thread_context(self, post: Post) -> str | None:
        try:
            return await self.bluesky.get_thread_context(
                post.uri,
                max_posts=self.settings.thread_context_max_posts,
                max_chars=self.settings.thread_context_max_chars,
            )
        except Exception as exc:
            logger.warning(
                "Falha ao buscar contexto do fio para %s: %s", post.uri, type(exc).__name__
            )
            return None
