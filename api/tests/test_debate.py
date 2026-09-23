"""Testes unitários para o DebateService (Promotor, Defensor, Juiz, Humildade Epistêmica P(IK))."""

import pytest

from app.core.config import Settings
from app.domain.entities import Evidence, VerdictLabel
from app.services.debate import DebateService
from tests.fakes import FakeLLM


@pytest.fixture
def sample_evidences():
    """Fixture de evidências catalogadas."""
    return [
        Evidence(
            source="google_factcheck",
            url="https://lupa.piaui.folha.uol.com.br/checagem-urna",
            title="TSE e PF desmentem fraude em urnas eletrônicas",
            snippet="Laudo pericial conjunto atestou a integridade dos sistemas e votos.",
            rating="Falso",
        ),
        Evidence(
            source="wikipedia",
            url="https://pt.wikipedia.org/wiki/Urna_eletronica_brasileira",
            title="Urna eletrônica brasileira",
            snippet="Utilizada desde 1996 com testes públicos de segurança obrigatórios.",
        ),
    ]


@pytest.mark.anyio
async def test_debate_standard_two_rounds_with_fake_llm(sample_evidences):
    """Testa execução completa de 2 rodadas de debate e julgamento."""
    responses = [
        # Rodada 1 - Promotor
        "A alegação é falsa. De acordo com [EV-01], peritos atestaram a integridade das urnas.",
        # Rodada 1 - Defensor
        "A acusação não observou que o post cita [EV-02] e faz uma crítica institucional geral.",
        # Rodada 2 - Promotor
        "A réplica mantém a acusação. [EV-01] é categórico sobre a ausência de fraudes.",
        # Rodada 2 - Defensor
        "A defesa reitera que se trata de retórica política sem dolo de desinformação.",
        # Juiz
        """```json
        {
            "label": "false",
            "confidence": 0.95,
            "rationale": "O Promotor comprovou via [EV-01] a falsidade factual da afirmação.",
            "cited_evidence_ids": ["EV-01"],
            "consensus": true,
            "p_ik": 0.92
        }
        ```""",
    ]

    fake_llm = FakeLLM(responses=responses)
    service = DebateService(llm=fake_llm, settings=Settings(debate_rounds=2))

    verdict = await service.conduct_debate(
        claim="Houve fraude comprovada nas urnas",
        post_text="Urnas foram fraudadas segundo denúncia",
        evidences=sample_evidences,
    )

    assert verdict.label == VerdictLabel.FALSE
    assert verdict.confidence == 0.95
    assert verdict.consensus is True
    assert verdict.p_ik == 0.92
    assert verdict.abstained is False
    assert len(verdict.transcript) == 4  # 2 rodadas * 2 agentes

    # Checa turnos
    assert verdict.transcript[0].role == "promotor"
    assert "EV-01" in verdict.transcript[0].cited_evidence_ids
    assert verdict.transcript[1].role == "defensor"
    assert "EV-02" in verdict.transcript[1].cited_evidence_ids

    # Conversão para entidade de domínio Verdict
    domain_verdict = verdict.to_domain_verdict(sample_evidences)
    assert domain_verdict.claim == "Houve fraude comprovada nas urnas"
    assert domain_verdict.label == VerdictLabel.FALSE
    assert "promotor_r1" in domain_verdict.agent_outputs
    assert "defensor_r2" in domain_verdict.agent_outputs
    assert domain_verdict.agent_outputs["consensus"] == "true"


@pytest.mark.anyio
async def test_debate_satire_case_defensor_prevails(sample_evidences):
    """Critério da Issue: caso de sátira -> Defensor prevalece -> não classifica como falso."""
    responses = [
        # Rodada 1 - Promotor
        "A postagem alega que o STF proibiu a chuva, o que é incorreto segundo [EV-01].",
        # Rodada 1 - Defensor
        "Claramente trata-se de SÁTIRA e paródia humorística de um perfil satírico popular.",
        # Juiz
        """{
            "label": "insufficient_evidence",
            "confidence": 0.90,
            "rationale": "O Defensor comprovou que se trata de sátira/paródia humorística.",
            "cited_evidence_ids": [],
            "consensus": true,
            "p_ik": 0.85
        }""",
    ]

    fake_llm = FakeLLM(responses=responses)
    service = DebateService(llm=fake_llm, settings=Settings(debate_rounds=1))

    verdict = await service.conduct_debate(
        claim="STF proíbe chuva no fim de semana",
        post_text="Urgente: STF acaba de proibir a chuva em todo o país kkkkk",
        evidences=sample_evidences,
        rounds=1,
    )

    # O Defensor prevalece: NÃO classifica como FALSE!
    assert verdict.label != VerdictLabel.FALSE
    assert verdict.label == VerdictLabel.INSUFFICIENT_EVIDENCE
    assert "sátira" in verdict.rationale.lower()


@pytest.mark.anyio
async def test_debate_low_p_ik_or_lack_of_consensus_forces_abstention(sample_evidences):
    """Humildade Epistêmica P(IK): sem consenso ou P(IK) baixo -> abstenção automática."""
    responses = [
        "Argumento promotor...",
        "Argumento defensor...",
        """{
            "label": "false",
            "confidence": 0.85,
            "rationale": "Há séria divergência e evidências contraditórias.",
            "cited_evidence_ids": [],
            "consensus": false,
            "p_ik": 0.40
        }""",
    ]

    fake_llm = FakeLLM(responses=responses)
    # Configura threshold de 0.60
    service = DebateService(
        llm=fake_llm,
        settings=Settings(debate_rounds=1, debate_p_ik_threshold=0.60),
    )

    verdict = await service.conduct_debate(
        claim="Fato duvidoso sem evidência conclusiva",
        post_text="Texto do post",
        evidences=sample_evidences,
        rounds=1,
    )

    # Força abstenção
    assert verdict.label == VerdictLabel.INSUFFICIENT_EVIDENCE
    assert verdict.abstained is True
    assert verdict.consensus is False
    assert verdict.p_ik == 0.40


@pytest.mark.anyio
async def test_debate_robust_json_parsing_fallback(sample_evidences):
    """Testa resiliência a falhas ou saídas truncadas do Juiz."""
    responses = [
        "Arg promotor",
        "Arg defensor",
        "Texto corrompido sem JSON válido",
    ]
    fake_llm = FakeLLM(responses=responses)
    service = DebateService(llm=fake_llm, settings=Settings(debate_rounds=1))

    verdict = await service.conduct_debate(
        claim="Qualquer alegação",
        post_text="Texto",
        evidences=sample_evidences,
        rounds=1,
    )

    # Fallback seguro para abstenção
    assert verdict.label == VerdictLabel.INSUFFICIENT_EVIDENCE
    assert verdict.abstained is True
