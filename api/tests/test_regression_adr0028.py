"""Testes de regressão cobrindo as anomalias de produção e o fechamento de brechas no ADR 0028.

Casos auditados no banco de dados e nos logs de produção do ContrarIA:
1. Caso 1 (Decisão 7367 - dovahqueer): Meme MC Mirella / Tigrinho com risada explícita ("KKKK").
   -> Veredito do Critic V2: REPROVADA (Ato de fala de humor/meme sem afirmação factual séria).
2. Caso 2 (Decisão 7359 - tho47): Desabafo Temer / Tigrinho / IPVA.
   -> Veredito do Critic V2: REPROVADA (Não afirma a alegação checada sobre Lula).
3. Caso 3 (Decisão 7418 - netasgard): Matéria de evento evangélico x Checagem Polymarket.
   -> Veredito do Critic V2: REPROVADA (Unsupported Association: ausência de termos de aposta).
4. Caso 4 (Wilson / Radar Baiano - Copacabana): Multidão em Copacabana SEM compartilhar foto de IA.
   -> Veredito do Critic V2: REPROVADA (Unsupported Association: co-ocorrência).
5. Caso 4b (Copacabana com foto de IA efetivamente compartilhada):
   -> Veredito do Critic V2: APROVADA (Contradição fática positiva com a mídia compartilhada).
6. Caso 6 (Alexandre Oliva - Tornozeleira no bolso): Metáfora / Uso figurado de termo fático.
   -> Veredito do Critic V2: REPROVADA (Uso figurado / metafórico de termo fático).
7. Caso 7 (BrunoAntifa - Copacabana Palace): Comentário desconexo da checagem.
   -> Veredito: REPROVADA (Unsupported Association).
8. Caso 8 (G1 - Decisão do TSE): Compartilhamento legítimo de notícia.
   -> Veredito: REPROVADA (Citação sem alegação falsa).
9. Caso 9 (Paulo Pimenta / Mídia NINJA): Compartilhamento de vídeo sem a mídia falsa da checagem.
   -> Veredito: REPROVADA (Unsupported Association).
10. Caso 10 (Dilma Resistente - Brasil 247): Compartilhamento de matéria sem afirmar boato.
    -> Veredito: REPROVADA (Unsupported Association).
11. Caso 11: Critic Semântico e Parser em regime Fail-Closed (timeout, formato quebrado, erro).
    -> Veredito: ABSTAIN absoluto.
12. Caso 12: Endurecimento do parser do Critic V2 (rejeição de "NAO APROVADA", etc.).
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
        if "g1.globo" in url:
            return "TSE mantém regras eleitorais para as próximas eleições municipais."
        if "brasil247" in url:
            return "Ato político em defesa da democracia reúne milhares no Rio de Janeiro."
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
async def test_regression_case_2_desabafo_temer_tigrinho_abstains(base_service):
    """Caso 2: Desabafo genérico sem afirmação da alegação checada -> REPROVADA."""
    service, bsky, llm = base_service

    post = Post(
        uri="at://did:plc:user2/app.bsky.feed.post/7359",
        cid="cid7359",
        author_did="did:plc:user2",
        text="Culpa do Temer, do Tigrinho e do IPVA que não para de subir!",
        created_at=datetime.now(UTC),
    )
    author = Account(did="did:plc:user2", handle="tho47.bsky.social")
    verdict = Verdict(
        claim="Lula aprovou a criação do Tigrinho no Brasil",
        label=VerdictLabel.FALSE,
        confidence=0.90,
        rationale="Checagem por Lupa",
        evidences=[
            Evidence(
                source="google_factcheck",
                url="https://lupa.com.br/tigrinho-temer",
                title="Jogo do Tigrinho não foi regulamentado por Lula",
                snippet="Lei 13.756 sancionada por Temer em 2018.",
            )
        ],
        agent_outputs={"claim_harvest": "{}"},
    )

    async def fake_complete(*args, purpose=None, **kwargs):
        if purpose == "critic_coherence":
            return (
                "DECISAO: REPROVADA\n"
                "MOTIVO: Desabafo genérico que não afirma que Lula criou o Tigrinho."
            )
        return "FONTE 1: CONTRADIZ\nCITAÇÃO: trecho\nNOTA: nota"

    llm.complete.side_effect = fake_complete
    llm.complete_with_tools.return_value = (
        "TIPO: FATO\nVEREDITO: DESMENTE\nFONTE: 1\n"
        "Você sabia que o Temer já havia regulado as apostas?"
    )

    result = await service.execute_intervention(post, author, verdict, bot_score=0.1)

    assert result is None
    bsky.quote_post.assert_not_called()


@pytest.mark.asyncio
async def test_regression_case_3_netasgard_polymarket_abstains(base_service):
    """Caso 3: Matéria evangélica vs checagem de Polymarket -> REPROVADA."""
    service, bsky, llm = base_service

    post = Post(
        uri="at://did:plc:user3/app.bsky.feed.post/7418",
        cid="cid7418",
        author_did="did:plc:user3",
        text="Culto reúne milhares em evento religioso no RJ https://netasgard.com/culto",
        links=["https://netasgard.com/culto"],
        created_at=datetime.now(UTC),
    )
    author = Account(did="did:plc:user3", handle="netasgard.bsky.social")
    verdict = Verdict(
        claim="Polymarket aponta 54,98% de chance de vitória de candidato",
        label=VerdictLabel.FALSE,
        confidence=0.91,
        rationale="Checagem por Comprova",
        evidences=[
            Evidence(
                source="google_factcheck",
                url="https://comprova.com.br/polymarket",
                title="Apostas no Polymarket não refletem pesquisa eleitoral",
                snippet="Site de apostas mostra outros números.",
            )
        ],
    )

    bundle = PostContextBundle(
        post=post,
        shared_link_text="Matéria sobre evento religioso no Rio de Janeiro e declarações sobre fé.",
    )

    assert _is_claim_relevant_to_post(verdict.claim, post.text, bundle.full_context_text()) is False

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
async def test_regression_case_4_copacabana_event_mention_without_fake_media_abstains(base_service):
    """Caso 4: Post apenas noticia multidão em Copacabana sem a foto de IA -> REPROVADA (ABSTAIN).

    A co-ocorrência temática de evento não justifica perguntar sobre imagens manipuladas.
    """
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
                "DECISAO: REPROVADA\n"
                "MOTIVO: Unsupported Association: O autor noticiou a manifestação real mas não "
                "compartilhou nem endossou a imagem aérea manipulada por inteligência artificial."
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

    assert result is None
    bsky.quote_post.assert_not_called()


@pytest.mark.asyncio
async def test_regression_case_4b_copacabana_with_fake_media_shared_allowed(base_service):
    """Caso 4b: Post compartilha expressamente a imagem de IA desmentida -> APROVADA."""
    service, bsky, llm = base_service

    post = Post(
        uri="at://did:plc:user4b/app.bsky.feed.post/7412",
        cid="cid7412",
        author_did="did:plc:user4b",
        text="Vejam essa foto aérea de Copacabana que a grande mídia escondeu! Lotado! https://uol.com.br/copacabana-ia",
        links=["https://uol.com.br/copacabana-ia"],
        created_at=datetime.now(UTC),
    )
    author = Account(did="did:plc:user4b", handle="militante.bsky.social")
    verdict = Verdict(
        claim="Imagem aérea de Copacabana lotada foi manipulada por inteligência artificial",
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
        shared_link_text="Imagem aérea manipulada com IA viralizou nas redes sociais.",
    )

    async def fake_complete(*args, purpose=None, **kwargs):
        if purpose == "critic_coherence":
            return (
                "DECISAO: APROVADA\n"
                "MOTIVO: Contradição fática direta com a foto aérea compartilhada pelo autor."
            )
        return "FONTE 1: CONTRADIZ\nCITAÇÃO: trecho\nNOTA: nota"

    llm.complete.side_effect = fake_complete
    llm.complete_with_tools.return_value = (
        "TIPO: FATO\nVEREDITO: DESMENTE\nFONTE: 1\n"
        "Ao compartilhar esta imagem aérea, você verificou a análise pericial do UOL Confere?"
    )

    result = await service.execute_intervention(
        post, author, verdict, bot_score=0.1, context_bundle=bundle
    )

    assert result is not None
    bsky.quote_post.assert_called_once()


@pytest.mark.asyncio
async def test_regression_case_alexandre_oliva_metaphor_tornozeleira_abstains(base_service):
    """Caso 6 (Alexandre Oliva): Uso metafórico de 'tornozeleira eletrônica' -> REPROVADA."""
    service, bsky, llm = base_service

    post = Post(
        uri="at://did:plc:oliva/post/999",
        cid="cid999",
        author_did="did:plc:oliva",
        text=(
            "Colocou a tornozeleira eletrônica no bolso e foi "
            "pro comício discursar sobre liberdade."
        ),
        created_at=datetime.now(UTC),
    )
    author = Account(did="did:plc:oliva", handle="oliva.bsky.social")
    verdict = Verdict(
        claim="Político X usa tornozeleira eletrônica em prisão domiciliar",
        label=VerdictLabel.FALSE,
        confidence=0.91,
        rationale="Checagem por Aos Fatos",
        evidences=[
            Evidence(
                source="google_factcheck",
                url="https://aosfatos.org/tornozeleira",
                title="Político X não usa tornozeleira eletrônica",
                snippet="SEAP desmente que político X tenha sido condenado ao uso de tornozeleira.",
            )
        ],
    )

    async def fake_complete(*args, purpose=None, **kwargs):
        if purpose == "critic_coherence":
            return (
                "DECISAO: REPROVADA\n"
                "MOTIVO: Uso figurado/metafórico de termo fático sem alegação literal."
            )
        return "FONTE 1: CONTRADIZ\nCITAÇÃO: trecho\nNOTA: nota"

    llm.complete.side_effect = fake_complete
    llm.complete_with_tools.return_value = (
        "TIPO: FATO\nVEREDITO: DESMENTE\nFONTE: 1\n"
        "Você conferiu a certidão da SEAP sobre tornozeleira eletrônica?"
    )

    result = await service.execute_intervention(post, author, verdict, bot_score=0.1)

    assert result is None
    bsky.quote_post.assert_not_called()


@pytest.mark.asyncio
async def test_regression_case_bruno_antifa_copacabana_palace_abstains(base_service):
    """Caso 7 (BrunoAntifa): Comentário sobre Copacabana Palace x checagem de foto -> REPROVADA."""
    service, bsky, llm = base_service

    post = Post(
        uri="at://did:plc:bruno/post/888",
        cid="cid888",
        author_did="did:plc:bruno",
        text="Todos na varanda do Copacabana Palace tomando champanhe enquanto o povo sofre.",
        created_at=datetime.now(UTC),
    )
    author = Account(did="did:plc:bruno", handle="bruno.bsky.social")
    verdict = Verdict(
        claim="Multidão em Copacabana foi gerada por inteligência artificial",
        label=VerdictLabel.FALSE,
        confidence=0.92,
        rationale="Checagem por UOL",
        evidences=[
            Evidence(
                source="google_factcheck",
                url="https://uol.com.br/ia",
                title="Foto de Copacabana é IA",
                snippet="Perícia confirmou IA.",
            )
        ],
    )

    async def fake_complete(*args, purpose=None, **kwargs):
        if purpose == "critic_coherence":
            return (
                "DECISAO: REPROVADA\n"
                "MOTIVO: Unsupported Association: Post comenta o hotel Copacabana Palace, "
                "não afirma nada sobre fotos aéreas de multidão."
            )
        return "FONTE 1: CONTRADIZ\nCITAÇÃO: trecho\nNOTA: nota"

    llm.complete.side_effect = fake_complete
    result = await service.execute_intervention(post, author, verdict, bot_score=0.1)

    assert result is None
    bsky.quote_post.assert_not_called()


@pytest.mark.asyncio
async def test_regression_case_g1_tse_legitimate_news_abstains(base_service):
    """Caso 8: Compartilhamento de matéria jornalística legítima do G1 sobre o TSE -> REPROVADA."""
    service, bsky, llm = base_service

    post = Post(
        uri="at://did:plc:cidadao/post/777",
        cid="cid777",
        author_did="did:plc:cidadao",
        text="TSE mantém decisão importante para o pleito https://g1.globo.com/tse",
        links=["https://g1.globo.com/tse"],
        created_at=datetime.now(UTC),
    )
    author = Account(did="did:plc:cidadao", handle="cidadao.bsky.social")
    verdict = Verdict(
        claim="TSE fraudou contagem de votos na eleição",
        label=VerdictLabel.FALSE,
        confidence=0.96,
        rationale="Checagem TSE",
        evidences=[
            Evidence(
                source="google_factcheck",
                url="https://tse.jus.br/fato",
                title="TSE não fraudou contagem",
                snippet="Urnas auditáveis.",
            )
        ],
    )

    bundle = PostContextBundle(
        post=post,
        shared_link_text="TSE mantém regras eleitorais para as próximas eleições municipais.",
    )

    async def fake_complete(*args, purpose=None, **kwargs):
        if purpose == "critic_coherence":
            return (
                "DECISAO: REPROVADA\n"
                "MOTIVO: Citação de matéria legítima do G1 sem alegação de fraude pelo autor."
            )
        return "FONTE 1: CONTRADIZ\nCITAÇÃO: trecho\nNOTA: nota"

    llm.complete.side_effect = fake_complete
    result = await service.execute_intervention(
        post, author, verdict, bot_score=0.1, context_bundle=bundle
    )

    assert result is None
    bsky.quote_post.assert_not_called()


@pytest.mark.asyncio
async def test_regression_case_paulo_pimenta_midia_ninja_abstains(base_service):
    """Caso 9 (Paulo Pimenta): Compartilhamento de vídeo do ato sem afirmar boato -> REPROVADA."""
    service, bsky, llm = base_service

    post = Post(
        uri="at://did:plc:pimenta/post/666",
        cid="cid666",
        author_did="did:plc:pimenta",
        text="Vídeo da Mídia NINJA mostrando o povo nas ruas pelo Brasil.",
        created_at=datetime.now(UTC),
    )
    author = Account(did="did:plc:pimenta", handle="pimenta.bsky.social")
    verdict = Verdict(
        claim="Multidão em Copacabana foi forjada com inteligência artificial",
        label=VerdictLabel.FALSE,
        confidence=0.93,
        rationale="Checagem por Lupa",
        evidences=[
            Evidence(
                source="google_factcheck",
                url="https://lupa.com.br/ia",
                title="Foto aérea de Copacabana é IA",
                snippet="Imagem foi gerada por software.",
            )
        ],
    )

    async def fake_complete(*args, purpose=None, **kwargs):
        if purpose == "critic_coherence":
            return (
                "DECISAO: REPROVADA\n"
                "MOTIVO: Unsupported Association: O autor compartilhou vídeo da Mídia NINJA, "
                "não compartilhou a foto de IA da checagem."
            )
        return "FONTE 1: CONTRADIZ\nCITAÇÃO: trecho\nNOTA: nota"

    llm.complete.side_effect = fake_complete
    result = await service.execute_intervention(post, author, verdict, bot_score=0.1)

    assert result is None
    bsky.quote_post.assert_not_called()


@pytest.mark.asyncio
async def test_regression_case_dilma_resistente_brasil247_abstains(base_service):
    """Caso 10 (Dilma Resistente): Compartilhamento de matéria do Brasil 247 -> REPROVADA."""
    service, bsky, llm = base_service

    post = Post(
        uri="at://did:plc:dilma/post/555",
        cid="cid555",
        author_did="did:plc:dilma",
        text="Brasil 247: Milhares participam de ato no Rio https://brasil247.com/ato",
        links=["https://brasil247.com/ato"],
        created_at=datetime.now(UTC),
    )
    author = Account(did="did:plc:dilma", handle="dilma.bsky.social")
    verdict = Verdict(
        claim="Foto de ato no Rio mostra público de 1984 na Candelária",
        label=VerdictLabel.FALSE,
        confidence=0.94,
        rationale="Checagem Aos Fatos",
        evidences=[
            Evidence(
                source="google_factcheck",
                url="https://aosfatos.org/foto-antiga",
                title="Foto de multidão é de 1984 e não de ato recente",
                snippet="Imagem tirada durante as Diretas Já.",
            )
        ],
    )

    bundle = PostContextBundle(
        post=post,
        shared_link_text="Ato político em defesa da democracia reúne milhares no Rio de Janeiro.",
    )

    async def fake_complete(*args, purpose=None, **kwargs):
        if purpose == "critic_coherence":
            return (
                "DECISAO: REPROVADA\n"
                "MOTIVO: O autor compartilhou link do Brasil 247, "
                "não a foto descontextualizada de 1984."
            )
        return "FONTE 1: CONTRADIZ\nCITAÇÃO: trecho\nNOTA: nota"

    llm.complete.side_effect = fake_complete
    result = await service.execute_intervention(
        post, author, verdict, bot_score=0.1, context_bundle=bundle
    )

    assert result is None
    bsky.quote_post.assert_not_called()


@pytest.mark.asyncio
async def test_regression_case_fail_closed_on_critic_network_error(base_service):
    """Caso 11: Queda de rede ou erro no OpenRouter nunca publica intervenção (fail-closed)."""
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


@pytest.mark.asyncio
async def test_regression_critic_v2_parser_strictness(base_service):
    """Caso 12: O parser do Critic V2 deve exigir token exato APROVADA e reprovar variações."""
    service, bsky, llm = base_service

    post_text = "Post qualquer"
    context_text = "Contexto"
    generated_text = "Pergunta socrática?"
    claim = "Alegação falsa"

    # 1. Aprovação exata padrão -> True
    llm.complete.return_value = "DECISAO: APROVADA\nMOTIVO: Pergunta bem ancorada."
    ok, _ = await service._validate_semantic_coherence(
        post_text, context_text, generated_text, claim
    )
    assert ok is True

    # 2. Aprovação com ponto final e minúsculas -> True
    llm.complete.return_value = "DECISAO: Aprovada.\nMOTIVO: Ancoragem válida."
    ok, _ = await service._validate_semantic_coherence(
        post_text, context_text, generated_text, claim
    )
    assert ok is True

    # 3. Negativa "NAO APROVADA" não pode passar -> False
    llm.complete.return_value = "DECISAO: NAO APROVADA\nMOTIVO: Não há correspondência."
    ok, reason = await service._validate_semantic_coherence(
        post_text, context_text, generated_text, claim
    )
    assert ok is False
    assert "Não há correspondência" in reason

    # 4. Negativa "NÃO APROVADA" com til -> False
    llm.complete.return_value = "DECISÃO: NÃO APROVADA\nMOTIVO: Desvio temático."
    ok, reason = await service._validate_semantic_coherence(
        post_text, context_text, generated_text, claim
    )
    assert ok is False

    # 5. "DESAPROVADA" -> False
    llm.complete.return_value = "DECISAO: DESAPROVADA\nMOTIVO: Associação desconexa."
    ok, reason = await service._validate_semantic_coherence(
        post_text, context_text, generated_text, claim
    )
    assert ok is False

    # 6. "REPROVADA" -> False
    llm.complete.return_value = "DECISAO: REPROVADA\nMOTIVO: Meme identificado."
    ok, reason = await service._validate_semantic_coherence(
        post_text, context_text, generated_text, claim
    )
    assert ok is False

    # 7. Resposta malformada sem linha de decisão -> False (fail-closed)
    llm.complete.return_value = "Não tenho certeza sobre essa postagem, parece humor."
    ok, reason = await service._validate_semantic_coherence(
        post_text, context_text, generated_text, claim
    )
    assert ok is False
