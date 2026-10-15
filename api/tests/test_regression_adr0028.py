"""Testes de regressão cobrindo as 5 anomalias auditadas no ADR 0028.

Casos auditados no banco de dados e nos logs de produção do ContrarIA:
1. Caso 1 (Decisão 7367 - dovahqueer): Meme MC Mirella / Tigrinho com risada explícita ("KKKK").
   -> Veredito do Critic V2: REPROVADA (Ato de fala de humor/meme sem afirmação factual séria).
2. Caso 2 (Decisão 7359 - tho47): Desabafo Temer / Tigrinho / IPVA.
   -> Veredito do Critic V2: REPROVADA (Não afirma a alegação checada sobre Lula).
3. Caso 3 (Decisão 7418 - netasgard): Matéria de evento evangélico x Checagem Polymarket.
   -> Veredito do Critic V2: REPROVADA (Unsupported Association: ausência de termos de aposta).
4. Caso 4 (Decisão 7411 - radarbaianooficial): Copacabana / Foto com IA.
   -> Veredito do Critic V2: APROVADA (Pergunta contextual legítima sobre autenticidade da foto).
5. Caso 5: Critic Semântico e Parser em regime Fail-Closed (timeout, formato quebrado, erro).
   -> Veredito: ABSTAIN absoluto.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.entities import Account, Evidence, Post, PostContextBundle, Verdict, VerdictLabel
from app.services.intervention import InterventionService, _is_claim_relevant_to_post


@pytest.fixture(autouse=True)
def mock_article_fetch(monkeypatch):
    async def fetch(url: str, *, max_chars: int | None = None):
        if "netasgard" in url:
            return "Matéria sobre evento religioso no Rio de Janeiro e declarações sobre fé."
        if "portal3dejulho" in url:
            return "Ato reúne apoiadores na orla de Copacabana no fim de semana."
        return f"Texto completo da checagem em {url}"

    from app.services import intervention

    monkeypatch.setattr(intervention, "fetch_article_text", fetch)


@pytest.fixture
def base_service():
    repo = MagicMock()
    repo.has_intervened_on_post.return_value = False
    repo.count_interventions_by_author_in_last_24h.return_value = 0
    repo.count_interventions_in_last_24h.return_value = 0

    bsky = AsyncMock()
    bsky.login.return_value = "did:bot:contraria"
    bsky.has_postgate_quote_disabled.return_value = False
    bsky.quote_post.return_value = ("at://did:bot:contraria/post/1001", "cid1001")

    llm = AsyncMock()
    service = InterventionService(repo, bsky, llm)
    service.settings.intervention_dry_run = False
    return service, bsky, llm


@pytest.mark.asyncio
async def test_regression_case_1_meme_mirella_tigrinho_abstains(base_service):
    """Caso 1: Meme 'KKKK' sem alegação fática séria -> REPROVADA."""
    service, bsky, llm = base_service

    post = Post(
        uri="at://did:plc:user1/app.bsky.feed.post/7367",
        cid="cid7367",
        author_did="did:plc:user1",
        text="ela falando 'Lula tirou meu tigrinho mais eu me resolvo com ele depois' KKKKKKKKKKKK",
        created_at=datetime.now(UTC),
    )
    author = Account(did="did:plc:user1", handle="dovahqueer.bsky.social")
    verdict = Verdict(
        claim="Lula não criou as apostas esportivas e o Tigrinho",
        label=VerdictLabel.FALSE,
        confidence=0.95,
        rationale="Checagem por Aos Fatos",
        evidences=[
            Evidence(
                source="google_factcheck",
                url="https://aosfatos.org/checagem-tigrinho",
                title="Lula não criou o jogo do Tigrinho",
                snippet="Regulação de apostas começou em 2018 com Temer.",
            )
        ],
        agent_outputs={"claim_harvest": "{}"},
    )

    async def fake_complete(*args, purpose=None, **kwargs):
        if purpose == "critic_coherence":
            return (
                "DECISAO: REPROVADA\n"
                "MOTIVO: Post identificado como meme ou sátira sem afirmação fática séria"
            )
        return "FONTE 1: CONTRADIZ\nCITAÇÃO: trecho\nNOTA: nota factual"

    llm.complete.side_effect = fake_complete
    llm.complete_with_tools.return_value = (
        "TIPO: FATO\nVEREDITO: DESMENTE\nFONTE: 1\n"
        "Você sabia que o Tigrinho não foi criado pelo Lula?"
    )

    result = await service.execute_intervention(post, author, verdict, bot_score=0.1)

    assert result is None
    bsky.quote_post.assert_not_called()


@pytest.mark.asyncio
async def test_regression_case_2_temer_ipva_rant_abstains(base_service):
    """Caso 2: Desabafo sobre Temer e IPVA sem afirmar mentira sobre Lula -> REPROVADA."""
    service, bsky, llm = base_service

    post = Post(
        uri="at://did:plc:user2/app.bsky.feed.post/7359",
        cid="cid7359",
        author_did="did:plc:user2",
        text="o temer não tinha criado o tigrinho? agora vem falar de ipva e gastos...",
        created_at=datetime.now(UTC),
    )
    author = Account(did="did:plc:user2", handle="tho47.bsky.social")
    verdict = Verdict(
        claim="Lula não criou as apostas esportivas e o Tigrinho",
        label=VerdictLabel.FALSE,
        confidence=0.9,
        rationale="Checagem por Lupa",
        evidences=[
            Evidence(
                source="google_factcheck",
                url="https://lupa.news/tigrinho",
                title="Lula não inventou o Tigrinho",
                snippet="Apostas foram liberadas pela Lei 13.756 de 2018.",
            )
        ],
    )

    async def fake_complete(*args, purpose=None, **kwargs):
        if purpose == "critic_coherence":
            return (
                "DECISAO: REPROVADA\n"
                "MOTIVO: O autor não afirmou que Lula criou o Tigrinho, "
                "apenas desabafou sobre Temer."
            )
        return "FONTE 1: CONTRADIZ\nCITAÇÃO: trecho\nNOTA: nota"

    llm.complete.side_effect = fake_complete
    llm.complete_with_tools.return_value = (
        "TIPO: FATO\nVEREDITO: DESMENTE\nFONTE: 1\nPor que afirmar que Lula criou o jogo?"
    )

    result = await service.execute_intervention(post, author, verdict, bot_score=0.1)

    assert result is None
    bsky.quote_post.assert_not_called()


@pytest.mark.asyncio
async def test_regression_case_3_netasgard_polymarket_unsupported_association_abstains(
    base_service,
):
    """Caso 3: Matéria de Flávio Bolsonaro sem citar apostas/Polymarket -> REPROVADA."""
    service, bsky, llm = base_service

    post = Post(
        uri="at://did:plc:user3/app.bsky.feed.post/7418",
        cid="cid7418",
        author_did="did:plc:user3",
        text="Pesquisa Netasgard: crescimento de evangélicos e falas de Flávio https://netasgard.com/materia",
        links=["https://netasgard.com/materia"],
        created_at=datetime.now(UTC),
    )
    author = Account(did="did:plc:user3", handle="radarbaiano.bsky.social")
    verdict = Verdict(
        claim="Flávio Bolsonaro tem 54,98% no Polymarket para 2026",
        label=VerdictLabel.FALSE,
        confidence=0.88,
        rationale="Checagem por Aos Fatos",
        evidences=[
            Evidence(
                source="google_factcheck",
                url="https://aosfatos.org/flavio-polymarket",
                title="Flávio Bolsonaro não lidera apostas no Polymarket com 54%",
                snippet="Site de apostas mostra outros números.",
            )
        ],
    )

    bundle = PostContextBundle(
        post=post,
        shared_link_text="Matéria sobre evento religioso no Rio de Janeiro e declarações sobre fé.",
    )

    # 1. Teste no filtro léxico/proposicional refinado:
    # A claim fala de Polymarket e 54,98%, o post/link fala de Netasgard e religião.
    assert _is_claim_relevant_to_post(verdict.claim, post.text, bundle.full_context_text()) is False

    # 2. Mesmo se passasse do filtro léxico, o Critic V2 veta:
    async def fake_complete(*args, purpose=None, **kwargs):
        if purpose == "critic_coherence":
            return (
                "DECISAO: REPROVADA\n"
                "MOTIVO: Unsupported Association: O post e o link não tratam de apostas "
                "nem de Polymarket."
            )
        return "FONTE 1: CONTRADIZ\nCITAÇÃO: trecho\nNOTA: nota"

    llm.complete.side_effect = fake_complete
    result = await service.execute_intervention(
        post, author, verdict, bot_score=0.1, context_bundle=bundle
    )

    assert result is None
    bsky.quote_post.assert_not_called()


@pytest.mark.asyncio
async def test_regression_case_4_copacabana_contextual_fact_check_allowed(base_service):
    """Caso 4: Post sobre Copacabana e IA; pergunta socrática educada -> APROVADA."""
    service, bsky, llm = base_service

    post = Post(
        uri="at://did:plc:user4/app.bsky.feed.post/7411",
        cid="cid7411",
        author_did="did:plc:user4",
        text="Multidão toma conta de Copacabana em ato https://portal3dejulho.com/copacabana",
        links=["https://portal3dejulho.com/copacabana"],
        created_at=datetime.now(UTC),
    )
    author = Account(did="did:plc:user4", handle="radarbaiano.bsky.social")
    verdict = Verdict(
        claim="Multidão em Copacabana foi gerada por inteligência artificial",
        label=VerdictLabel.FALSE,
        confidence=0.92,
        rationale="Checagem por UOL Confere",
        evidences=[
            Evidence(
                source="google_factcheck",
                url="https://uol.com.br/copacabana-ia",
                title="Imagem aérea de Copacabana lotada foi manipulada por IA",
                snippet="Análise pericial confirmou artefatos de IA na imagem da multidão.",
            )
        ],
    )

    bundle = PostContextBundle(
        post=post,
        shared_link_text="Ato reúne apoiadores na orla de Copacabana no fim de semana.",
    )

    async def fake_complete(*args, purpose=None, **kwargs):
        if purpose == "critic_coherence":
            return (
                "DECISAO: APROVADA\n"
                "MOTIVO: Pergunta contextual socrática pertinente sem acusação de má-fé."
            )
        return "FONTE 1: CONTRADIZ\nCITAÇÃO: trecho\nNOTA: nota"

    llm.complete.side_effect = fake_complete
    llm.complete_with_tools.return_value = (
        "TIPO: FATO\nVEREDITO: DESMENTE\nFONTE: 1\n"
        "Você notou se as fotos aéreas desse ato foram analisadas quanto a artefatos de IA?"
    )

    result = await service.execute_intervention(
        post, author, verdict, bot_score=0.1, context_bundle=bundle
    )

    assert result is not None
    bsky.quote_post.assert_called_once()


@pytest.mark.asyncio
async def test_regression_case_5_fail_closed_on_critic_network_error(base_service):
    """Caso 5: Queda de rede ou erro no OpenRouter nunca publica intervenção (fail-closed)."""
    service, bsky, llm = base_service

    post = Post(
        uri="at://did:plc:user5/post/555",
        cid="cid555",
        author_did="did:plc:user5",
        text="Lula e o Tigrinho",
        created_at=datetime.now(UTC),
    )
    author = Account(did="did:plc:user5", handle="alvo.bsky.social")
    verdict = Verdict(
        claim="Lula e o Tigrinho",
        label=VerdictLabel.FALSE,
        confidence=0.95,
        rationale="r",
        evidences=[Evidence("t", "https://checagem", "T", "S")],
    )

    async def fake_complete(*args, purpose=None, **kwargs):
        if purpose == "critic_coherence":
            raise RuntimeError("502 Bad Gateway from OpenRouter")
        return "FONTE 1: CONTRADIZ\nCITAÇÃO: trecho\nNOTA: nota"

    llm.complete.side_effect = fake_complete
    llm.complete_with_tools.return_value = (
        "TIPO: FATO\nVEREDITO: DESMENTE\nFONTE: 1\nPergunta socrática sobre Tigrinho?"
    )

    result = await service.execute_intervention(post, author, verdict, bot_score=0.1)

    assert result is None
    bsky.quote_post.assert_not_called()
