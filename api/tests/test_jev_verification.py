from datetime import UTC, datetime

import pytest

from app.core.config import Settings
from app.domain.entities import Evidence, Post, VerdictLabel
from app.services.crc import CRCCalibration
from app.services.jev_verification import JevVerificationService


class StaticCalibrations:
    def __init__(self, calibration: CRCCalibration | None) -> None:
        self.calibration = calibration

    def get_latest(self, model: str) -> CRCCalibration | None:
        return self.calibration


def build_service(calibration: CRCCalibration | None, **settings) -> JevVerificationService:
    return JevVerificationService(
        classifier=None,
        sources=[],
        calibration_repo=StaticCalibrations(calibration),
        settings=Settings(_env_file=None, **settings),
    )


def calibration(lambda_hat: float) -> CRCCalibration:
    return CRCCalibration(
        lambda_hat=lambda_hat, alpha=0.05, n=40, model="jev", created_at=datetime.now(UTC)
    )


def test_abstains_without_calibration_by_default():
    label, confidence, rationale = build_service(None)._apply_calibration(
        VerdictLabel.FALSE, 0.95, 2
    )
    assert label == VerdictLabel.INSUFFICIENT_EVIDENCE
    assert confidence == 0.0
    assert "não há calibração" in rationale


def test_allow_uncalibrated_keeps_raw_verdict_and_says_so():
    service = build_service(None, jev_allow_uncalibrated=True)
    label, confidence, rationale = service._apply_calibration(VerdictLabel.FALSE, 0.95, 2)
    assert label == VerdictLabel.FALSE
    assert confidence == 0.95
    assert "JEV_ALLOW_UNCALIBRATED" in rationale


@pytest.mark.parametrize("allow_uncalibrated", [False, True])
def test_existing_calibration_still_gates_low_confidence(allow_uncalibrated):
    service = build_service(calibration(0.9), jev_allow_uncalibrated=allow_uncalibrated)
    label, _, rationale = service._apply_calibration(VerdictLabel.MISLEADING, 0.85, 1)
    assert label == VerdictLabel.INSUFFICIENT_EVIDENCE
    assert "lambda_hat" in rationale


class ScriptedClassifier:
    """Relevância pelo título da evidência; veredito fixo. Registra os prompts."""

    def __init__(self, relevance_by_title: dict[str, float]) -> None:
        self.relevance_by_title = relevance_by_title
        self.questions: list[str] = []

    async def classify(self, question: str, options: list[str]) -> dict[str, float]:
        self.questions.append(question)
        if options == ["relevante", "irrelevante"]:
            score = next(v for title, v in self.relevance_by_title.items() if title in question)
            return {"relevante": score, "irrelevante": 1 - score}
        # Veredito: confirmam=0.1, desmentem=0.7, distorcem=0.2 (ordem de _LABEL_BY_OPTION).
        return dict(zip(options, [0.1, 0.7, 0.2], strict=True))

    async def count_tokens(self, texts: list[str]) -> list[int]:
        # Matéria completa "pesa" 3000 tokens; o resto, 10.
        return [3000 if "matéria completa" in text else 10 for text in texts]


def evidence(url: str, title: str) -> Evidence:
    return Evidence(source="test", url=url, title=title, snippet="")


async def test_filter_relevant_shortlists_by_word_overlap_and_sorts_by_margin():
    claim = "Dino suspendeu decisão de Mendonça sobre postagem de Tabet"
    unrelated = [f"futebol campeonato rodada {i}" for i in range(10)]
    evidences = [evidence(f"https://x/{i}", title) for i, title in enumerate(unrelated)] + [
        evidence("https://a", "Dino suspende decisão de Mendonça"),
        evidence("https://b", "Dino suspende decisão de Mendonça sobre postagem de Tabet"),
    ]
    scores = {title: 0.9 for title in unrelated} | {
        "Dino suspende decisão de Mendonça sobre": 0.95,
        "Dino suspende decisão de Mendonça": 0.8,
    }
    classifier = ScriptedClassifier(scores)
    service = build_service(None)
    service.classifier = classifier

    relevant, log = await service._filter_relevant(claim, evidences)

    assert len(log) == 8
    assert {"https://a", "https://b"} <= {entry["url"] for entry in log}
    assert relevant[0].url == "https://b"
    margins = [entry["relevante"] - entry["irrelevante"] for entry in log]
    assert len(relevant) == sum(margin >= 0.15 for margin in margins)


async def test_verdict_packs_full_articles_until_the_context_limit(monkeypatch):
    from app.services import jev_verification

    async def article(url: str):
        return f"matéria completa de {url}"

    monkeypatch.setattr(jev_verification, "_fetch_article_text", article)
    classifier = ScriptedClassifier({})
    service = build_service(None, jev_n_ctx=4096)
    service.classifier = classifier
    relevant = [
        Evidence(source="t", url=f"https://e{i}", title=f"Fonte {i}", snippet=f"trecho {i}")
        for i in range(7)
    ]

    label, confidence, _ = await service._classify_verdict("alegação", relevant)

    prompt = classifier.questions[-1]
    assert label == VerdictLabel.FALSE
    assert confidence == 0.7
    # 4096 de contexto: só a primeira matéria cabe inteira (3000); as outras
    # entram com o trecho da busca, até o teto de 5 evidências.
    assert "matéria completa de https://e0" in prompt
    assert "matéria completa de https://e1" not in prompt
    assert all(f"trecho {i}" in prompt for i in range(1, 5))
    assert "trecho 5" not in prompt


class EmptySource:
    name = "empty"

    async def search(self, query: str, *, limit: int = 5):
        return []


class ContextClassifier:
    def __init__(self) -> None:
        self.questions: list[str] = []

    async def classify(self, question: str, options: list[str]) -> dict[str, float]:
        self.questions.append(question)
        if options == ["factual", "opiniao"]:
            factual = "221 bi em depósitos" in question
            return {"factual": 0.9 if factual else 0.1, "opiniao": 0.1 if factual else 0.9}
        return dict.fromkeys(options, 1 / len(options))

    async def count_tokens(self, texts: list[str]) -> list[int]:
        return [10 for _ in texts]


async def test_jev_considers_limited_thread_context_as_candidate_claim():
    classifier = ContextClassifier()
    service = build_service(None)
    service.classifier = classifier
    service.sources = [EmptySource()]
    post = Post(
        uri="at://did:plc:a/app.bsky.feed.post/1",
        cid="c",
        author_did="did:plc:a",
        text="Acho esse assunto estranho.",
        created_at=datetime.now(UTC),
    )

    verdict = await service.verify(
        post,
        parent_text="continuação do autor: Os valores chegaram a 221 bi em depósitos.",
    )

    assert verdict.label == VerdictLabel.INSUFFICIENT_EVIDENCE
    assert "221 bi em depósitos" in verdict.claim
    assert any("221 bi em depósitos" in question for question in classifier.questions)
