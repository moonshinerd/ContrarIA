"""Orquestração completa da verificação factual com abstenção calibrada."""

import json
import logging
from dataclasses import dataclass
from datetime import date
from math import isfinite
from typing import Protocol

from sqlalchemy import create_engine

from app.core.config import Settings, get_settings
from app.domain.entities import Evidence, Post, Verdict, VerdictLabel
from app.models.llm.base import LLMPort
from app.repositories.crc_calibration import CRCCalibrationRepository
from app.services.claim_verification import ClaimVerificationPlanner, PostContext
from app.services.crc import CRCCalibration
from app.services.debate import DebateService, DebateVerdict
from app.services.self_rag import EvidenceDocument, SelfRAGService, SupportedAnswer

logger = logging.getLogger(__name__)


class CalibrationProvider(Protocol):
    def get_latest(self, model: str) -> CRCCalibration | None: ...


@dataclass
class _ClaimDecision:
    claim: str
    label: VerdictLabel
    confidence: float
    rationale: str
    consensus: bool
    p_ik: float


class VerificationService:
    """Compõe Claim/CoVe, Self-RAG, debate e CRC em um único veredito."""

    def __init__(
        self,
        planner: ClaimVerificationPlanner,
        self_rag: SelfRAGService,
        debate: DebateService,
        calibrations: CalibrationProvider,
        *,
        settings: Settings | None = None,
    ) -> None:
        self.planner = planner
        self.self_rag = self_rag
        self.debate = debate
        self.calibrations = calibrations
        self.settings = settings or get_settings()

    @classmethod
    def from_settings(
        cls,
        llm: LLMPort,
        *,
        settings: Settings | None = None,
        engine=None,
    ) -> "VerificationService":
        resolved = settings or get_settings()
        resolved_engine = engine or create_engine(resolved.database_url)
        return cls(
            ClaimVerificationPlanner(llm),
            SelfRAGService.from_settings(llm, resolved),
            DebateService(llm, resolved),
            CRCCalibrationRepository(resolved_engine),
            settings=resolved,
        )

    async def verify(
        self,
        post: Post,
        *,
        quoted_text: str | None = None,
        parent_text: str | None = None,
        current_date: date | None = None,
    ) -> Verdict:
        """Produz um Verdict completo e abstém sempre que uma garantia falha."""
        plan = await self.planner.plan(
            PostContext(post=post.text, quoted=quoted_text, parent=parent_text),
            current_date=current_date,
        )
        outputs = {"claim_extraction": plan.extraction.model_dump_json()}
        factual_claims = [item.text for item in plan.extraction.factual_claims]
        if not factual_claims or plan.cove is None:
            return Verdict(
                claim=post.text,
                label=VerdictLabel.INSUFFICIENT_EVIDENCE,
                confidence=0.0,
                rationale="A postagem não contém alegação factual verificável.",
                agent_outputs=outputs,
            )

        outputs["cove_plan"] = plan.cove.model_dump_json()
        rag = await self.self_rag.run(plan.cove, current_date=current_date)
        outputs.update(rag.agent_outputs)
        outputs["self_rag.reflections"] = json.dumps(
            [item.model_dump(mode="json") for item in rag.reflections], ensure_ascii=False
        )

        model = self.settings.crc_model_name or self.settings.llm_model_name
        calibration = self.calibrations.get_latest(model)
        outputs["crc.calibration"] = self._serialize_calibration(calibration, model)

        all_evidences: list[Evidence] = []
        decisions: list[_ClaimDecision] = []
        for index, claim in enumerate(factual_claims, start=1):
            answers = [item for item in rag.supported_answers if item.claim == claim]
            evidences = self._evidences_from_answers(answers)
            all_evidences.extend(evidences)
            key = f"debate.claim_{index:02d}"
            if not answers or not evidences:
                decisions.append(
                    _ClaimDecision(
                        claim=claim,
                        label=VerdictLabel.INSUFFICIENT_EVIDENCE,
                        confidence=0.0,
                        rationale="O Self-RAG não encontrou evidência suficiente para o debate.",
                        consensus=False,
                        p_ik=0.0,
                    )
                )
                outputs[f"{key}.decision"] = "insufficient_evidence:no_supported_evidence"
                continue

            try:
                debated = await self.debate.conduct_debate(
                    claim=claim,
                    post_text=post.text,
                    evidences=evidences,
                    verified_answers=[item.answer for item in answers],
                )
            except Exception as exc:
                logger.exception("Falha no debate da alegação %s", claim)
                decisions.append(
                    _ClaimDecision(
                        claim=claim,
                        label=VerdictLabel.INSUFFICIENT_EVIDENCE,
                        confidence=0.0,
                        rationale="O debate não produziu uma saída estruturada confiável.",
                        consensus=False,
                        p_ik=0.0,
                    )
                )
                outputs[f"{key}.decision"] = f"insufficient_evidence:{type(exc).__name__}"
                continue

            outputs[f"{key}.transcript"] = self._serialize_debate(debated)
            decision = self._apply_runtime_guards(debated, calibration)
            decisions.append(decision)
            outputs[f"{key}.decision"] = json.dumps(
                {
                    "raw_label": debated.label.value,
                    "final_label": decision.label.value,
                    "confidence": debated.confidence,
                    "consensus": debated.consensus,
                    "p_ik": debated.p_ik,
                },
                ensure_ascii=False,
            )

        return self._aggregate(factual_claims, decisions, all_evidences, outputs)

    def _apply_runtime_guards(
        self,
        debated: DebateVerdict,
        calibration: CRCCalibration | None,
    ) -> _ClaimDecision:
        reasons: list[str] = []
        if calibration is None:
            reasons.append("não há calibração CRC para o modelo")
        elif debated.confidence < calibration.lambda_hat:
            reasons.append("confiança abaixo de lambda_hat")
        elif calibration.alpha > self.settings.crc_alpha:
            reasons.append("calibração usa alpha acima do limite configurado")
        if not isfinite(debated.confidence) or not 0 <= debated.confidence <= 1:
            reasons.append("confiança inválida")
        if not debated.consensus:
            reasons.append("não houve consenso")
        if not isfinite(debated.p_ik) or not 0 <= debated.p_ik <= 1:
            reasons.append("P(IK) inválido")
        elif debated.p_ik < self.settings.debate_p_ik_threshold:
            reasons.append("P(IK) abaixo do limiar")
        if debated.label is VerdictLabel.INSUFFICIENT_EVIDENCE:
            reasons.append("o juiz se absteve")

        label = VerdictLabel.INSUFFICIENT_EVIDENCE if reasons else debated.label
        rationale = debated.rationale
        if reasons:
            rationale = f"Abstenção: {', '.join(dict.fromkeys(reasons))}. {rationale}".strip()
        return _ClaimDecision(
            claim=debated.claim,
            label=label,
            confidence=(
                max(0.0, min(1.0, debated.confidence)) if isfinite(debated.confidence) else 0.0
            ),
            rationale=rationale,
            consensus=debated.consensus,
            p_ik=max(0.0, min(1.0, debated.p_ik)) if isfinite(debated.p_ik) else 0.0,
        )

    @staticmethod
    def _evidences_from_answers(answers: list[SupportedAnswer]) -> list[Evidence]:
        documents: list[EvidenceDocument] = [doc for answer in answers for doc in answer.evidence]
        result: list[Evidence] = []
        seen: set[tuple[str, str]] = set()
        for document in documents:
            identity = (document.source, document.url)
            if identity in seen:
                continue
            seen.add(identity)
            result.append(
                Evidence(
                    source=document.source,
                    url=document.url,
                    title=document.title,
                    snippet=document.snippet,
                    published_at=document.published_at,
                    rating=document.rating,
                )
            )
        return result

    @staticmethod
    def _serialize_calibration(calibration: CRCCalibration | None, model: str) -> str:
        if calibration is None:
            return json.dumps({"model": model, "lambda_hat": None}, ensure_ascii=False)
        return json.dumps(
            {
                "lambda_hat": calibration.lambda_hat,
                "alpha": calibration.alpha,
                "n": calibration.n,
                "model": calibration.model,
                "created_at": calibration.created_at.isoformat(),
            },
            ensure_ascii=False,
        )

    @staticmethod
    def _serialize_debate(debate: DebateVerdict) -> str:
        return json.dumps(
            {
                "rounds_conducted": debate.rounds_conducted,
                "transcript": [
                    {
                        "round": turn.round,
                        "role": turn.role,
                        "argument": turn.argument,
                        "cited_evidence_ids": turn.cited_evidence_ids,
                    }
                    for turn in debate.transcript
                ],
                "judge": debate.raw_judge_output,
            },
            ensure_ascii=False,
        )

    @staticmethod
    def _aggregate(
        claims: list[str],
        decisions: list[_ClaimDecision],
        evidences: list[Evidence],
        outputs: dict[str, str],
    ) -> Verdict:
        adverse = [
            item
            for item in decisions
            if item.label in (VerdictLabel.FALSE, VerdictLabel.MISLEADING)
        ]
        if adverse:
            selected = max(
                adverse,
                key=lambda item: (item.confidence, item.label is VerdictLabel.FALSE),
            )
        elif decisions and all(item.label is VerdictLabel.TRUE for item in decisions):
            selected = min(decisions, key=lambda item: item.confidence)
        else:
            abstentions = [
                item for item in decisions if item.label is VerdictLabel.INSUFFICIENT_EVIDENCE
            ]
            selected = (
                abstentions[0]
                if abstentions
                else _ClaimDecision(
                    claim=" | ".join(claims),
                    label=VerdictLabel.INSUFFICIENT_EVIDENCE,
                    confidence=0.0,
                    rationale="Não foi possível concluir a verificação.",
                    consensus=False,
                    p_ik=0.0,
                )
            )

        unique_evidences: list[Evidence] = []
        seen: set[tuple[str, str]] = set()
        for evidence in evidences:
            identity = (evidence.source, evidence.url)
            if identity not in seen:
                seen.add(identity)
                unique_evidences.append(evidence)

        return Verdict(
            claim=" | ".join(claims),
            label=selected.label,
            confidence=selected.confidence,
            rationale=selected.rationale,
            evidences=unique_evidences,
            agent_outputs=outputs,
        )
