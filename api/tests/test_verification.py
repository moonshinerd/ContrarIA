"""Testes da composição completa de verificação da issue #25."""

import json
from datetime import UTC, datetime

import pytest

from app.core.config import Settings
from app.domain.entities import Post, VerdictLabel
from app.services.claim_verification import (
    ClaimCandidate,
    ClaimExtraction,
    ClaimQuestionSet,
    ClaimSource,
    ClaimVerificationPlan,
    ContentType,
    CoVeQuestionPlan,
    VerificationQuestion,
)
from app.services.crc import CRCCalibration
from app.services.debate import DebateTurn, DebateVerdict
from app.services.self_rag import EvidenceDocument, SelfRAGResult, SupportedAnswer, SupportLevel
from app.services.verification import VerificationService

CLAIM = "A vacina causa a doença que deveria prevenir"


def factual_plan() -> ClaimVerificationPlan:
    extraction = ClaimExtraction(
        items=[
            ClaimCandidate(
                text=CLAIM,
                source=ClaimSource.POST,
                classification=ContentType.FACTUAL,
                rationale="Afirmação verificável.",
            )
        ]
    )
    return ClaimVerificationPlan(
        extraction=extraction,
        cove=CoVeQuestionPlan(
            claims=[
                ClaimQuestionSet(
                    claim=CLAIM,
                    questions=[
                        VerificationQuestion(
                            question="Há estudos sobre a segurança dessa vacina específica?",
                            purpose="Verificar segurança.",
                        ),
                        VerificationQuestion(
                            question="Qual é a conclusão das autoridades sanitárias?",
                            purpose="Consultar consenso.",
                        ),
                    ],
                )
            ]
        ),
    )


class FakePlanner:
    def __init__(self, plan):
        self.result = plan

    async def plan(self, context, *, current_date=None):
        return self.result


class FakeSelfRAG:
    async def run(self, plan, *, current_date=None):
        document = EvidenceDocument(
            evidence_id="q01:factcheck:01",
            source="google_factcheck",
            url="https://example.org/check",
            title="Checagem independente",
            snippet="Os dados não sustentam a alegação.",
            rating="Falso",
        )
        return SelfRAGResult(
            reflections=[],
            supported_answers=[
                SupportedAnswer(
                    claim=CLAIM,
                    question="Há estudos sobre a segurança dessa vacina específica?",
                    answer="Estudos controlados não sustentam a relação alegada.",
                    support=SupportLevel.FULLY,
                    usefulness=5,
                    evidence=[document],
                )
            ],
            agent_outputs={"self_rag.q01.answer": "reflexão auditável"},
            llm_calls=3,
            truncated_questions=0,
        )


class FakeDebate:
    def __init__(self, *, confidence=0.91, consensus=True, p_ik=0.88):
        self.confidence = confidence
        self.consensus = consensus
        self.p_ik = p_ik
        self.verified_answers = []

    async def conduct_debate(self, claim, post_text, evidences, rounds=None, verified_answers=None):
        self.verified_answers = verified_answers or []
        return DebateVerdict(
            claim=claim,
            label=VerdictLabel.FALSE,
            confidence=self.confidence,
            rationale="As evidências contradizem a alegação.",
            cited_evidence_ids=["EV-01"],
            consensus=self.consensus,
            p_ik=self.p_ik,
            abstained=False,
            rounds_conducted=1,
            transcript=[DebateTurn(1, "promotor", "Argumento com [EV-01]", ["EV-01"])],
            raw_judge_output={"label": "false", "confidence": self.confidence},
        )


class StaticCalibrations:
    def __init__(self, threshold=0.80, available=True):
        self.threshold = threshold
        self.available = available

    def get_latest(self, model):
        if not self.available:
            return None
        return CRCCalibration(
            lambda_hat=self.threshold,
            alpha=0.05,
            n=100,
            model=model,
            created_at=datetime.now(UTC),
        )


def sample_post() -> Post:
    return Post(
        uri="at://did:plc:test/app.bsky.feed.post/1",
        cid="cid",
        author_did="did:plc:test",
        text=CLAIM,
        created_at=datetime.now(UTC),
    )


def build_service(debate, calibrations):
    settings = Settings(
        llm_model_name="test-model",
        debate_p_ik_threshold=0.60,
    )
    return VerificationService(
        FakePlanner(factual_plan()),
        FakeSelfRAG(),
        debate,
        calibrations,
        settings=settings,
    )


@pytest.mark.anyio
async def test_verify_returns_complete_calibrated_verdict_and_audit_log():
    debate = FakeDebate()
    service = build_service(debate, StaticCalibrations())

    verdict = await service.verify(sample_post())

    assert verdict.label is VerdictLabel.FALSE
    assert verdict.confidence == 0.91
    assert verdict.evidences[0].source == "google_factcheck"
    assert debate.verified_answers == ["Estudos controlados não sustentam a relação alegada."]
    assert "self_rag.q01.answer" in verdict.agent_outputs
    assert "debate.claim_01.transcript" in verdict.agent_outputs
    assert json.loads(verdict.agent_outputs["crc.calibration"])["lambda_hat"] == 0.8


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("debate", "calibrations", "reason"),
    [
        (FakeDebate(confidence=0.79), StaticCalibrations(0.80), "confiança"),
        (FakeDebate(p_ik=0.40), StaticCalibrations(), "P(IK)"),
        (FakeDebate(consensus=False), StaticCalibrations(), "consenso"),
        (FakeDebate(), StaticCalibrations(available=False), "calibração"),
    ],
)
async def test_verify_abstains_when_any_runtime_guard_fails(debate, calibrations, reason):
    verdict = await build_service(debate, calibrations).verify(sample_post())

    assert verdict.label is VerdictLabel.INSUFFICIENT_EVIDENCE
    assert reason in verdict.rationale


@pytest.mark.anyio
async def test_verify_ends_early_for_nonfactual_content():
    plan = ClaimVerificationPlan(
        extraction=ClaimExtraction(
            items=[
                ClaimCandidate(
                    text="Eu não gostei do debate.",
                    source=ClaimSource.POST,
                    classification=ContentType.OPINION,
                    rationale="Opinião pessoal.",
                )
            ]
        )
    )
    service = VerificationService(
        FakePlanner(plan),
        FakeSelfRAG(),
        FakeDebate(),
        StaticCalibrations(),
        settings=Settings(llm_model_name="test-model"),
    )

    verdict = await service.verify(sample_post())

    assert verdict.label is VerdictLabel.INSUFFICIENT_EVIDENCE
    assert verdict.evidences == []
    assert "não contém alegação factual" in verdict.rationale
