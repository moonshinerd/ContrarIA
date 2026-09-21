import asyncio
import json
from datetime import UTC, date, datetime

import pytest

from app.clients.evidence.base import EvidenceSource
from app.core.config import Settings
from app.domain.entities import Evidence, Verdict, VerdictLabel
from app.services.claim_verification import CoVeQuestionPlan
from app.services.self_rag import (
    SelfRAGCallLimitExceeded,
    SelfRAGLimits,
    SelfRAGService,
    StructuredSelfRAGOutputError,
    SupportLevel,
)
from tests.fakes import FakeLLM

QUESTION = "Qual fonte oficial confirma que o evento ocorreu em 20 de setembro de 2026?"
SECOND_QUESTION = "Em qual local ocorreu o evento de 20 de setembro de 2026?"


class FakeEvidenceSource(EvidenceSource):
    def __init__(self, name, evidences=None, error=None):
        self.name = name
        self.evidences = list(evidences or [])
        self.error = error
        self.calls = []

    async def search(self, query: str, *, limit: int = 5) -> list[Evidence]:
        self.calls.append({"query": query, "limit": limit})
        if self.error:
            raise self.error
        return self.evidences[:limit]


def evidence(source, title, snippet, url, *, published_at=None):
    return Evidence(
        source=source,
        url=url,
        title=title,
        snippet=snippet,
        published_at=published_at,
    )


def cove_plan():
    return CoVeQuestionPlan.model_validate(
        {
            "claims": [
                {
                    "claim": "O evento ocorreu em 20 de setembro de 2026.",
                    "questions": [
                        {"question": QUESTION, "purpose": "Confirmar a fonte primária."},
                        {"question": SECOND_QUESTION, "purpose": "Confirmar o local."},
                    ],
                }
            ]
        }
    )


def retrieve_response(retrieve=True):
    return json.dumps(
        {
            "retrieve": retrieve,
            "rationale": "O fato depende de evidência externa atualizada.",
        },
        ensure_ascii=False,
    )


def relevance_response(*items):
    return json.dumps(
        {
            "items": [
                {
                    "evidence_id": evidence_id,
                    "relevant": relevant,
                    "rationale": rationale,
                }
                for evidence_id, relevant, rationale in items
            ]
        },
        ensure_ascii=False,
    )


def answer_response(
    *,
    support="fully",
    evidence_ids=None,
    answer="O registro oficial confirma que o evento ocorreu na data informada.",
):
    return json.dumps(
        {
            "answer": answer,
            "support": support,
            "usefulness": 5 if support != "no_support" else 1,
            "evidence_ids": evidence_ids or [],
            "rationale": "A fonte primária registra diretamente o evento e a data.",
        },
        ensure_ascii=False,
    )


def one_question_limits(**overrides):
    values = {
        "max_questions": 1,
        "max_evidence_per_source": 3,
        "max_llm_calls": 6,
        "evidence_timeout_seconds": 1,
    }
    values.update(overrides)
    return SelfRAGLimits(**values)


@pytest.mark.asyncio
async def test_self_rag_discards_irrelevant_evidence_and_records_all_reflections():
    source = FakeEvidenceSource(
        "fonte_primaria",
        [
            evidence(
                "fonte_primaria",
                "Comunicado oficial",
                "O evento ocorreu em 20 de setembro de 2026.",
                "https://example.org/comunicado",
                published_at=datetime(2026, 9, 20, tzinfo=UTC),
            ),
            evidence(
                "fonte_primaria",
                "Outro evento",
                "Uma cerimônia sem relação ocorreu em 2024.",
                "https://example.org/outro",
            ),
        ],
    )
    llm = FakeLLM(
        responses=[
            retrieve_response(),
            relevance_response(
                ("q01:fonte_primaria:01", True, "Confirma diretamente o fato e a data."),
                ("q01:fonte_primaria:02", False, "Trata de outro evento e período."),
            ),
            answer_response(evidence_ids=["q01:fonte_primaria:01"]),
        ]
    )

    result = await SelfRAGService(llm, [source], limits=one_question_limits()).run(
        cove_plan(), current_date=date(2026, 9, 21)
    )

    assert result.llm_calls == 3
    assert len(result.supported_answers) == 1
    assert [item.evidence_id for item in result.supported_answers[0].evidence] == [
        "q01:fonte_primaria:01"
    ]
    assert [item.evidence_id for item in result.reflections[0].relevant_evidence] == [
        "q01:fonte_primaria:01"
    ]
    assert set(result.agent_outputs) == {
        "self_rag.q01.[Retrieve]",
        "self_rag.q01.[Sources]",
        "self_rag.q01.[IsRel]",
        "self_rag.q01.[IsSup][IsUse]",
        "self_rag.limits",
    }
    assert all(call["json_mode"] is True for call in llm.calls)
    assert [call["purpose"] for call in llm.calls] == [
        "self_rag_retrieve",
        "self_rag_isrel",
        "self_rag_answer",
    ]
    assert all("2026-09-21" in call["system"] for call in llm.calls)


@pytest.mark.asyncio
async def test_sources_run_in_parallel_and_respect_limit_per_source():
    started = set()
    both_started = asyncio.Event()

    class CoordinatedSource(FakeEvidenceSource):
        async def search(self, query: str, *, limit: int = 5) -> list[Evidence]:
            self.calls.append({"query": query, "limit": limit})
            started.add(self.name)
            if len(started) == 2:
                both_started.set()
            await asyncio.wait_for(both_started.wait(), timeout=0.5)
            return []

    first = CoordinatedSource("primeira")
    second = CoordinatedSource("segunda")
    service = SelfRAGService(
        FakeLLM(responses=[retrieve_response()]),
        [first, second],
        limits=one_question_limits(max_evidence_per_source=2),
    )

    result = await service.run(cove_plan())

    assert started == {"primeira", "segunda"}
    assert first.calls[0]["limit"] == second.calls[0]["limit"] == 2
    assert not result.supported_answers


@pytest.mark.asyncio
async def test_source_failure_is_isolated_without_exposing_error_message():
    failing = FakeEvidenceSource("indisponivel", error=RuntimeError("segredo-na-url"))
    working = FakeEvidenceSource(
        "funcional",
        [evidence("funcional", "Registro", "Confirma o evento.", "https://example.org/ok")],
    )
    llm = FakeLLM(
        responses=[
            retrieve_response(),
            relevance_response(("q01:funcional:01", True, "É um registro direto.")),
            answer_response(evidence_ids=["q01:funcional:01"]),
        ]
    )

    result = await SelfRAGService(llm, [failing, working], limits=one_question_limits()).run(
        cove_plan()
    )

    assert result.reflections[0].source_errors == {"indisponivel": "RuntimeError"}
    assert "segredo-na-url" not in json.dumps(result.agent_outputs)
    assert len(result.supported_answers) == 1


@pytest.mark.asyncio
async def test_retrieve_false_stops_before_sources_and_answer():
    source = FakeEvidenceSource("fonte")
    llm = FakeLLM(responses=[retrieve_response(retrieve=False)])

    result = await SelfRAGService(llm, [source], limits=one_question_limits()).run(cove_plan())

    assert llm.call_count == 1
    assert source.calls == []
    assert result.reflections[0].answer.support is SupportLevel.NO_SUPPORT
    assert not result.supported_answers


@pytest.mark.asyncio
async def test_no_support_answer_is_not_kept():
    source = FakeEvidenceSource(
        "fonte",
        [evidence("fonte", "Registro incompleto", "Não informa a data.", "https://example.org")],
    )
    llm = FakeLLM(
        responses=[
            retrieve_response(),
            relevance_response(("q01:fonte:01", True, "É relacionada, mas incompleta.")),
            answer_response(support="no_support", answer=None),
        ]
    )

    result = await SelfRAGService(llm, [source], limits=one_question_limits()).run(cove_plan())

    assert result.reflections[0].answer.support is SupportLevel.NO_SUPPORT
    assert result.supported_answers == []


@pytest.mark.asyncio
async def test_invalid_relevance_coverage_is_retried_and_validated():
    source = FakeEvidenceSource(
        "fonte",
        [evidence("fonte", "Registro", "Confirma a data.", "https://example.org")],
    )
    llm = FakeLLM(
        responses=[
            retrieve_response(),
            relevance_response(("id-inventado", True, "Parece relacionada.")),
            relevance_response(("q01:fonte:01", True, "Confirma diretamente.")),
            answer_response(evidence_ids=["q01:fonte:01"]),
        ]
    )

    result = await SelfRAGService(llm, [source], limits=one_question_limits()).run(cove_plan())

    assert result.llm_calls == 4
    assert "falhou na validação" in llm.calls[2]["system"]
    assert len(result.supported_answers) == 1


@pytest.mark.asyncio
async def test_ungrounded_answer_is_retried_and_never_kept():
    source = FakeEvidenceSource(
        "fonte",
        [
            evidence(
                "fonte",
                "Comunicado oficial",
                "O evento ocorreu em 20 de setembro de 2026.",
                "https://example.org",
            )
        ],
    )
    llm = FakeLLM(
        responses=[
            retrieve_response(),
            relevance_response(("q01:fonte:01", True, "Confirma diretamente.")),
            answer_response(
                evidence_ids=["q01:fonte:01"],
                answer="Uma conclusão completamente inventada.",
            ),
            answer_response(
                evidence_ids=["q01:fonte:01"],
                answer=" ".join(
                    (
                        "O comunicado oficial confirma que o evento ocorreu",
                        "em 20 de setembro de 2026.",
                    )
                ),
            ),
        ]
    )

    result = await SelfRAGService(llm, [source], limits=one_question_limits()).run(cove_plan())

    assert result.llm_calls == 4
    assert result.supported_answers[0].answer.startswith("O comunicado oficial")
    assert "falhou na validação" in llm.calls[3]["system"]


@pytest.mark.asyncio
async def test_invalid_output_twice_raises_typed_error():
    llm = FakeLLM(responses=["não é json", '{"retrieve": true}'])
    service = SelfRAGService(llm, [], limits=one_question_limits())

    with pytest.raises(StructuredSelfRAGOutputError, match="após 2 tentativas"):
        await service.run(cove_plan())


@pytest.mark.asyncio
async def test_llm_call_limit_is_enforced_before_next_step():
    source = FakeEvidenceSource(
        "fonte",
        [evidence("fonte", "Registro", "Confirma a data.", "https://example.org")],
    )
    llm = FakeLLM(responses=[retrieve_response()])
    service = SelfRAGService(
        llm,
        [source],
        limits=one_question_limits(max_llm_calls=1),
    )

    with pytest.raises(SelfRAGCallLimitExceeded, match="Limite de 1"):
        await service.run(cove_plan())
    assert llm.call_count == 1


@pytest.mark.asyncio
async def test_question_limit_is_reported_without_silent_extra_calls():
    llm = FakeLLM(responses=[retrieve_response(retrieve=False)])
    result = await SelfRAGService(llm, [], limits=one_question_limits()).run(cove_plan())

    assert len(result.reflections) == 1
    assert result.truncated_questions == 1
    assert llm.call_count == 1


def test_settings_enable_sources_individually(monkeypatch):
    created = []

    def fake_factory(name, **kwargs):
        created.append((name, kwargs["settings"]))
        return FakeEvidenceSource(name)

    monkeypatch.setattr("app.services.self_rag.get_evidence_source", fake_factory)
    settings = Settings(
        self_rag_enabled_sources=["wikipedia", "web_search"],
        self_rag_max_questions=4,
        self_rag_max_evidence_per_source=2,
        self_rag_max_llm_calls=12,
    )

    service = SelfRAGService.from_settings(FakeLLM(), settings)

    assert [source.name for source in service.sources] == ["wikipedia", "web_search"]
    assert [name for name, _ in created] == ["wikipedia", "web_search"]
    assert all(received is settings for _, received in created)
    assert service.limits.max_questions == 4
    assert service.limits.max_evidence_per_source == 2
    assert service.limits.max_llm_calls == 12


@pytest.mark.asyncio
async def test_reflections_are_persisted_in_verdict_agent_outputs():
    result = await SelfRAGService(
        FakeLLM(responses=[retrieve_response(retrieve=False)]),
        [],
        limits=one_question_limits(),
    ).run(cove_plan())
    verdict = Verdict(
        claim="O evento ocorreu em 20 de setembro de 2026.",
        label=VerdictLabel.INSUFFICIENT_EVIDENCE,
        confidence=0,
        rationale="Ainda sem evidência suficiente.",
    )

    result.persist_in_verdict(verdict)

    assert verdict.agent_outputs == result.agent_outputs
    assert "self_rag.q01.[Retrieve]" in verdict.agent_outputs
