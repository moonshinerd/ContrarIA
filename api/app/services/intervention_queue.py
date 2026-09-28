"""Rodadas de intervenção: publica só o melhor candidato a cada janela.

A diretriz de bots do Bluesky trata volume de interações não solicitadas como
spam ("It must be an opt-in interaction, or else your bot may be taken for
spam"). Em vez de citar todo post adverso na hora (8 quotes em 14 min, medido
ao vivo), o worker junta os candidatos e, a cada rodada, publica só o de maior
confiança; os demais são descartados.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.clients.ozone_client import OzoneClient
from app.core.config import Settings
from app.db.orm.decisions import DecisionLog
from app.domain.entities import Account, Post, Verdict
from app.services.intervention import InterventionService

logger = logging.getLogger("contraria.services.intervention_queue")

# Brasil sem horário de verão desde 2019: offset fixo, sem depender de tzdata.
_BRASILIA = timezone(timedelta(hours=-3))


@dataclass
class InterventionCandidate:
    decision_id: int
    post: Post
    author: Account
    verdict: Verdict
    bot_score: float


class InterventionQueue:
    def __init__(
        self,
        settings: Settings,
        db_session: Session,
        intervention: InterventionService,
        ozone: OzoneClient,
    ) -> None:
        self.settings = settings
        self.db = db_session
        self.intervention = intervention
        self.ozone = ozone
        self._candidates: list[InterventionCandidate] = []

    def add(self, candidate: InterventionCandidate) -> None:
        self._candidates.append(candidate)

    def __len__(self) -> int:
        return len(self._candidates)

    def in_quiet_hours(self, now: datetime | None = None) -> bool:
        hour = (now or datetime.now(UTC)).astimezone(_BRASILIA).hour
        start = self.settings.intervention_quiet_start_hour
        end = self.settings.intervention_quiet_end_hour
        return start <= hour < end if start <= end else hour >= start or hour < end

    async def run_round(self, now: datetime | None = None) -> str | None:
        """Tenta publicar o melhor candidato; os demais da rodada são descartados."""
        candidates = sorted(self._candidates, key=lambda c: c.verdict.confidence, reverse=True)
        self._candidates = []
        if not candidates:
            return None
        if self.in_quiet_hours(now):
            for candidate in candidates:
                self._set_action(candidate, "MONITOR", "Horário de silêncio: sem intervenções.")
            logger.info(
                "Rodada no horário de silêncio: %d candidato(s) descartado(s)", len(candidates)
            )
            return None

        published: str | None = None
        for candidate in candidates:
            if published is None:
                try:
                    published = await self.intervention.execute_intervention(
                        candidate.post, candidate.author, candidate.verdict, candidate.bot_score
                    )
                except Exception as exc:
                    logger.error("Erro na intervenção de %s: %s", candidate.post.uri, exc)
                    self._set_action(candidate, "ERROR_INTERVENTION", str(exc))
                    continue
                if published:
                    self._set_action(
                        candidate,
                        "INTERVENE",
                        "Melhor candidato da rodada: intervenção (quote) publicada.",
                    )
                    await self._label(candidate)
                    continue
                self._set_action(
                    candidate, "MONITOR", "Candidato da rodada barrado pelas travas da intervenção."
                )
            else:
                self._set_action(
                    candidate, "MONITOR", "Candidato da rodada preterido por outro mais confiante."
                )
        logger.info(
            "Rodada de intervenção: %d candidato(s), publicado=%s", len(candidates), published
        )
        return published

    async def _label(self, candidate: InterventionCandidate) -> None:
        if self.settings.intervention_dry_run or not self.settings.pipeline_labeler_enabled:
            return
        try:
            await self.ozone.emit_label(
                candidate.post, label_val="possivel-desinformacao", action="create"
            )
        except Exception as exc:
            logger.error("Erro ao rotular %s: %s", candidate.post.uri, exc)

    def _set_action(self, candidate: InterventionCandidate, action: str, reason: str) -> None:
        self.db.execute(
            update(DecisionLog)
            .where(DecisionLog.id == candidate.decision_id)
            .values(action=action, justification=reason)
        )
        self.db.commit()
