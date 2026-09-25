import json
from datetime import date
from pathlib import Path

import pytest

from app.services.claim_verification import (
    ClaimExtraction,
    ClaimVerificationPlanner,
    ContentType,
    PostContext,
    StructuredLLMOutputError,
    VerificationQuestion,
)
from tests.fakes import FakeLLM

GOLDEN_PATH = Path(__file__).parents[2] / "research" / "claim_extraction_golden.json"


def extraction_response(expected):
    return json.dumps(
        {
            "items": [
                {
                    "text": " ".join(item["keywords"]),
                    "source": item["source"],
                    "classification": item["classification"],
                    "rationale": "Classificação anotada no conjunto dourado.",
                }
                for item in expected
            ]
        },
        ensure_ascii=False,
    )


def cove_response(expected):
    claims = [item for item in expected if item["classification"] == "factual"]
    return json.dumps(
        {
            "claims": [
                {
                    "claim": " ".join(item["keywords"]),
                    "questions": [
                        {
                            "question": (
                                f"Qual fonte oficial confirma {' '.join(item['keywords'])}?"
                            ),
                            "purpose": "Localizar a fonte primária.",
                        },
                        {
                            "question": f"Em que data ocorreu {' '.join(item['keywords'])}?",
                            "purpose": "Verificar a atualidade e o período.",
                        },
                    ],
                }
                for item in claims
            ]
        },
        ensure_ascii=False,
    )


@pytest.mark.anyio
async def test_golden_set_with_fake_llm():
    cases = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    assert len(cases) >= 10
    assert (
        sum(
            item["classification"] == "satira_ironia" for case in cases for item in case["expected"]
        )
        >= 2
    )
    assert (
        sum(item["classification"] == "opiniao" for case in cases for item in case["expected"]) >= 2
    )

    for case in cases:
        responses = [extraction_response(case["expected"])]
        factual = any(item["classification"] == "factual" for item in case["expected"])
        if factual:
            responses.append(cove_response(case["expected"]))
        fake = FakeLLM(responses=responses)
        result = await ClaimVerificationPlanner(fake).plan(
            PostContext.model_validate(case["context"]),
            current_date=date(2026, 9, 21),
        )

        assert [item.classification.value for item in result.extraction.items] == [
            item["classification"] for item in case["expected"]
        ]
        assert result.should_act is factual
        assert fake.call_count == (2 if factual else 1)
        assert all(call["json_mode"] is True for call in fake.calls)
        assert fake.calls[0]["purpose"] == "claim_extraction"
        assert "2026-09-21" in fake.calls[0]["system"]
        if factual:
            assert fake.calls[1]["purpose"] == "cove_questions"
            assert "2026-09-21" in fake.calls[1]["system"]
            assert result.cove is not None
            assert len(result.cove.claims) == len(result.extraction.factual_claims)
        else:
            assert result.cove is None


@pytest.mark.anyio
async def test_context_includes_post_quoted_parent_and_date():
    fake = FakeLLM(
        responses=[
            json.dumps(
                {
                    "items": [
                        {
                            "text": "A votação foi cancelada.",
                            "source": "pai",
                            "classification": "factual",
                            "rationale": "É verificável.",
                        }
                    ]
                }
            )
        ]
    )
    planner = ClaimVerificationPlanner(fake)
    await planner.extract(
        PostContext(post="Veja.", quoted="Texto citado.", parent="A votação foi cancelada."),
        current_date=date(2026, 9, 21),
    )
    payload = json.loads(fake.last_call["user"])
    assert payload == {
        "data_atual": "2026-09-21",
        "post": "Veja.",
        "quoted": "Texto citado.",
        "parent": "A votação foi cancelada.",
    }


@pytest.mark.anyio
async def test_source_is_derived_from_context_instead_of_trusting_model():
    fake = FakeLLM(
        responses=[
            json.dumps(
                {
                    "items": [
                        {
                            "text": "O desemprego caiu para 5%.",
                            "source": "pai",
                            "classification": "factual",
                            "rationale": "A taxa pode ser verificada.",
                        }
                    ]
                }
            )
        ]
    )
    extraction = await ClaimVerificationPlanner(fake).extract(
        PostContext(post="Confira o dado.", quoted="O desemprego caiu para 5%.")
    )
    assert extraction.items[0].source.value == "citado"


@pytest.mark.anyio
async def test_ungrounded_model_output_is_retried():
    fake = FakeLLM(
        responses=[
            json.dumps(
                {
                    "items": [
                        {
                            "text": "Eu prefiro X.",
                            "source": "post",
                            "classification": "opiniao",
                            "rationale": "É uma preferência.",
                        }
                    ]
                }
            ),
            json.dumps(
                {
                    "items": [
                        {
                            "text": "Este é o pior governo da história.",
                            "source": "post",
                            "classification": "opiniao",
                            "rationale": "É um juízo de valor.",
                        }
                    ]
                }
            ),
        ]
    )
    result = await ClaimVerificationPlanner(fake).extract(
        PostContext(post="Na minha opinião, este é o pior governo da história.")
    )
    assert result.items[0].text == "Este é o pior governo da história."
    assert fake.call_count == 2


@pytest.mark.anyio
async def test_invalid_json_is_retried_and_never_leaks_unvalidated_output():
    valid = extraction_response(
        [{"source": "post", "classification": "opiniao", "keywords": ["Gosto disso"]}]
    )
    fake = FakeLLM(responses=["```json\n{}\n```", valid])
    result = await ClaimVerificationPlanner(fake).extract(PostContext(post="Gosto disso."))
    assert result.items[0].classification is ContentType.OPINION
    assert fake.call_count == 2
    assert "falhou na validação" in fake.last_call["system"]


@pytest.mark.anyio
async def test_invalid_json_twice_raises_typed_error():
    fake = FakeLLM(responses=["não é json", '{"items": []}'])
    with pytest.raises(StructuredLLMOutputError, match="após 3 tentativas"):
        await ClaimVerificationPlanner(fake).extract(PostContext(post="Conteúdo."))


def test_schema_rejects_unknown_fields_and_duplicate_items():
    duplicate = {
        "text": "O evento ocorreu.",
        "source": "post",
        "classification": "factual",
        "rationale": "Verificável.",
    }
    with pytest.raises(ValueError):
        ClaimExtraction.model_validate({"items": [duplicate, duplicate]})
    with pytest.raises(ValueError):
        ClaimExtraction.model_validate({"items": [{**duplicate, "confidence": 0.9}]})


def test_schema_normalizes_double_escaped_unicode_from_local_models():
    extraction = ClaimExtraction.model_validate(
        {
            "items": [
                {
                    "text": r"Elei\u00e7\u00f5es",
                    "source": "post",
                    "classification": "factual",
                    "rationale": r"Informa\u00e7\u00e3o verific\u00e1vel.",
                }
            ]
        }
    )
    assert extraction.items[0].text == "Eleições"
    assert extraction.items[0].rationale == "Informação verificável."


@pytest.mark.parametrize(
    ("alias", "expected"),
    [("quoted", "citado"), ("cited", "citado"), ("parent", "pai")],
)
def test_schema_normalizes_source_aliases_used_by_models(alias, expected):
    extraction = ClaimExtraction.model_validate(
        {
            "items": [
                {
                    "text": "O evento ocorreu.",
                    "source": alias,
                    "classification": "factual",
                    "rationale": "A ocorrência pode ser verificada.",
                }
            ]
        }
    )
    assert extraction.items[0].source.value == expected


@pytest.mark.anyio
async def test_cove_requires_exact_factual_claim_coverage():
    extraction = ClaimExtraction.model_validate_json(
        extraction_response(
            [{"source": "post", "classification": "factual", "keywords": ["Fato A"]}]
        )
    )
    fake = FakeLLM(
        responses=[
            json.dumps(
                {
                    "claims": [
                        {
                            "claim": "Outro fato",
                            "questions": [
                                {"question": "Qual fonte confirma outro fato?", "purpose": "Fonte"},
                                {"question": "Quando ocorreu outro fato?", "purpose": "Data"},
                            ],
                        }
                    ]
                }
            )
        ]
    )
    with pytest.raises(StructuredLLMOutputError, match="após 3 tentativas"):
        await ClaimVerificationPlanner(fake).generate_questions(extraction)
    assert fake.call_count == 3


def test_post_context_rejects_blank_and_oversized_input():
    with pytest.raises(ValueError):
        PostContext(post="   ")
    with pytest.raises(ValueError):
        PostContext(post="x" * 3001)


@pytest.mark.parametrize(
    "question",
    [
        "Qual fonte confirma essa afirmação?",
        "Quando ocorreu a alegação acima?",
        "Que órgão publicou isso?",
    ],
)
def test_factored_cove_rejects_questions_that_depend_on_shared_context(question):
    with pytest.raises(ValueError, match="autossuficiente"):
        VerificationQuestion(question=question, purpose="Verificar uma dimensão do fato.")
