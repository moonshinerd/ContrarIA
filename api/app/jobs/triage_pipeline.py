"""Liga triagem, bot score, verificação e intervenção no worker."""

import logging
import math

from app.core.config import Settings
from app.domain.entities import VerdictLabel
from app.domain.prioritization import evaluate_gq04_matrix
from app.repositories.posts import PostRepository
from app.services.bot_scoring import BotScoringService
from app.services.intervention import InterventionService
from app.services.verification import VerificationService

logger = logging.getLogger("contraria.jobs.triage_pipeline")

_PUBLIC_HARM_TERMS = (
    "fraude eleitoral",
    "saúde pública",
    "saude publica",
    "violência política",
    "violencia politica",
    "ataque institucional",
)


class TriagePipeline:
    """Processa uma pequena fila para não ultrapassar orçamento de LLM."""

    def __init__(
        self,
        settings: Settings,
        posts: PostRepository,
        bots: BotScoringService,
        verification: VerificationService,
        intervention: InterventionService,
    ) -> None:
        self.settings = settings
        self.posts = posts
        self.bots = bots
        self.verification = verification
        self.intervention = intervention
        self._processed_uris: set[str] = set()

    async def run_once(self) -> None:
        candidates = self.posts.get_triage_candidates(self.settings.worker_pipeline_batch_size)
        for post, base_relevance in candidates:
            if post.uri in self._processed_uris:
                continue
            self._processed_uris.add(post.uri)
            try:
                author = await self.bots.bsky_client.get_profile(post.author_did)
                assessment = await self.bots.get_assessment(post.author_did)
                verdict = await self.verification.verify(post)
                is_adverse = verdict.label in (VerdictLabel.FALSE, VerdictLabel.MISLEADING)
                relevance = base_relevance + (0.2 * math.log1p(author.followers_count))
                harm = any(term in post.text.casefold() for term in _PUBLIC_HARM_TERMS)
                from app.db.orm.decisions import DecisionLog
                triage = evaluate_gq04_matrix(
                    is_political=True,
                    relevance=relevance,
                    bot_suspicion=assessment.score,
                    falsehood_chance=verdict.confidence if is_adverse else 0.0,
                    public_harm_risk=harm,
                    threshold_relevance=self.settings.triage_threshold_relevance,
                    threshold_bot=self.settings.triage_threshold_bot,
                    threshold_falsehood=self.settings.triage_threshold_falsehood,
                )
                self.posts.update_triage(
                    post.uri, status=triage.triage_status, priority=triage.priority
                )
                
                action = "MONITOR"
                justification = f"GQ04 determinou triage_status={triage.triage_status}"
                
                if triage.triage_status == "queued":
                    action = "INTERVENE"
                    justification = "Alto engajamento e risco, elegível para quote."
                    await self.intervention.execute_intervention(
                        post, author, verdict, assessment.score
                    )
                elif triage.triage_status == "ignored":
                    action = "IGNORE"
                    justification = "Ignorado pela matriz GQ04"
                
                # Gravar decisão imutável (Issue #17)
                from sqlalchemy.orm import Session
                with Session(self.posts.engine) as session:
                    decision = DecisionLog(
                        post_uri=post.uri,
                        post_snapshot={"text": post.text, "author_did": post.author_did, "created_at": post.created_at.isoformat()},
                        bot_score=assessment.score,
                        bot_features=assessment.features,
                        sources=[s.__dict__ for s in verdict.evidences] if verdict.evidences else [],
                        agent_outputs={},
                        verdict=verdict.label.value,
                        confidence=verdict.confidence,
                        crc_threshold_used=self.settings.crc_alpha,
                        action=action,
                        justification=justification,
                    )
                    session.add(decision)
                    session.commit()
                
                logger.info(
                    "Candidato processado",
                    extra={
                        "uri": post.uri,
                        "triage_status": triage.triage_status,
                        "verdict": verdict.label.value,
                    },
                )
            except Exception:
                # Um candidato não pode encerrar o worker; fica elegível novamente após restart.
                self._processed_uris.discard(post.uri)
                logger.exception("Falha ao processar candidato %s", post.uri)
