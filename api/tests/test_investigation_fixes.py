from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.entities import Account, Evidence, Verdict, VerdictLabel
from app.domain.entities import Post as DomainPost
from app.repositories.posts import PostRepository
from app.services.intervention import (
    InterventionService,
    _find_hallucinated_entity,
    _is_claim_relevant_to_post,
)
from app.services.jev_verification import _entity_conflict, _is_verifiable_claim


def test_is_verifiable_claim_rejects_orphan_fragment():
    # Fragmento nominal sem verbo nem nome próprio
    assert not _is_verifiable_claim("Deputado mais votado do ES.")
    # Com verbo e sujeito explícito, é uma alegação completa
    assert _is_verifiable_claim("Lucas Polese foi eleito deputado mais votado do ES.")
    # Com título político e verbo
    assert _is_verifiable_claim("Deputado votou contra a proposta salarial.")


def test_entity_conflict_blocks_cross_state_evidence():
    claim = "Lucas Polese foi o deputado mais votado do ES."
    ev_mg = Evidence(
        source="wikipedia",
        url="https://pt.wikipedia.org/wiki/Nikolas_Ferreira",
        title="Nikolas Ferreira",
        snippet="Nikolas Ferreira é deputado federal pelo estado de Minas Gerais.",
    )
    conflict = _entity_conflict(claim, ev_mg)
    assert conflict is not None
    assert "UF diferente" in conflict or "localidade diferente" in conflict

    ev_es = Evidence(
        source="gazeta",
        url="https://gazeta.example/polese",
        title="Lucas Polese no Espírito Santo",
        snippet="Lucas Polese foi o mais votado no ES.",
    )
    assert _entity_conflict(claim, ev_es) is None


def test_find_hallucinated_entity_detects_unmentioned_public_figures():
    post_text = (
        "O ES sempre teve governadores progressistas, vai eleger um governador do PL. "
        "O concorrente era cria do Casagrande e não conseguiu fazer o Ferraço vencer."
    )
    gen_text = (
        "O post afirma que Nikolas Ferreira foi o deputado mais votado do ES. "
        "Mas a fonte aponta que ele é de Minas Gerais."
    )
    hallucinated = _find_hallucinated_entity(gen_text, post_text)
    assert hallucinated == "Nikolas Ferreira"

    # Quando a entidade está no post, não é alucinação
    valid_gen = "Seria possível o Ferraço vencer no Espírito Santo com apoio de Casagrande?"
    assert _find_hallucinated_entity(valid_gen, post_text) is None


def test_is_claim_relevant_to_post():
    post_text = (
        "O ES sempre teve governadores progressistas, vai eleger governador do PL. "
        "Casagrande e Ferraço."
    )
    orphan_claim = "Jornada de 16 horas por dia no trabalho."
    assert not _is_claim_relevant_to_post(orphan_claim, post_text)

    relevant_claim = "Ferraço não conseguiu se eleger governador no ES."
    assert _is_claim_relevant_to_post(relevant_claim, post_text)


@pytest.mark.asyncio
async def test_intervention_blocks_hallucinated_entity_in_quote():
    mock_repo = MagicMock()
    mock_bsky = AsyncMock()
    mock_llm = AsyncMock()

    service = InterventionService(mock_repo, mock_bsky, mock_llm)
    service.settings.intervention_dry_run = False

    post = DomainPost(
        uri="at://did:1/post/1",
        cid="cid1",
        author_did="did:1",
        text="Casagrande e Ferraço disputam o governo do estado contra o candidato da oposição.",
        created_at=datetime.now(UTC),
    )
    verdict = Verdict(
        claim="Casagrande e Ferraço disputam o governo do estado",
        label=VerdictLabel.FALSE,
        confidence=0.95,
        rationale="r",
        evidences=[
            Evidence("t", "https://fonte.example", "Fonte Exemplo", "trecho explicativo"),
        ],
    )

    # Simula que o LLM alucinou Nikolas Ferreira na resposta
    mock_llm.complete_with_tools.return_value = (
        "TIPO: FATO\nVEREDITO: DESMENTE\nFONTE: 1\n"
        "O post afirma que Nikolas Ferreira participou dessa disputa eleitoral."
    )

    res = await service.execute_intervention(
        post, Account(did="did:1", handle="user"), verdict, 0.1
    )
    # A intervenção DEVE ser abortada pelo guardrail de grounding
    assert res is None
    mock_bsky.quote_post.assert_not_called()


def test_post_aging_delay_in_repository():
    from sqlalchemy import create_engine

    from app.db.base import Base

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    repo = PostRepository(engine)

    now = datetime(2026, 10, 7, 12, 0, 0, tzinfo=UTC)

    # Post 1: criado há 30 minutos (jovem, < 3h)
    # Post 2: criado há 20 horas (maduro, >= 3h e <= 48h)
    # Post 3: criado há 55 horas (velho, > 48h)
    posts_data = [
        {
            "uri": "at://recent",
            "cid": "c1",
            "author_did": "d1",
            "text": "post jovem",
            "created_at": now - timedelta(minutes=30),
            "source": "jetstream",
            "triage_status": "monitor",
            "priority": 1.0,
        },
        {
            "uri": "at://mature",
            "cid": "c2",
            "author_did": "d2",
            "text": "post maduro",
            "created_at": now - timedelta(hours=20),
            "source": "jetstream",
            "triage_status": "monitor",
            "priority": 1.0,
        },
        {
            "uri": "at://old",
            "cid": "c3",
            "author_did": "d3",
            "text": "post velho",
            "created_at": now - timedelta(hours=55),
            "source": "jetstream",
            "triage_status": "monitor",
            "priority": 1.0,
        },
    ]
    repo.upsert_posts(posts_data)

    # 1. Com aging delay (min_age_hours=3, max_age_hours=48), apenas o post maduro entra
    candidates = repo.get_triage_candidates(10, min_age_hours=3.0, max_age_hours=48.0, now=now)
    uris = [p.uri for p, _ in candidates]
    assert uris == ["at://mature"]

    # 2. Expiração de posts velhos (> 48h)
    expired_count = repo.expire_older_than(48.0, now=now)
    assert expired_count == 1

    # Após expiração, o post velho não consta mais como pendente
    all_pending = repo.get_triage_candidates(10, min_age_hours=0.0, max_age_hours=None, now=now)
    pending_uris = [p.uri for p, _ in all_pending]
    assert "at://old" not in pending_uris
    assert set(pending_uris) == {"at://recent", "at://mature"}


@pytest.mark.asyncio
async def test_semantic_critic_veto_blocks_intervention():
    mock_repo = MagicMock()
    mock_repo.has_intervened_on_post.return_value = False
    mock_repo.count_interventions_by_author_in_last_24h.return_value = 0
    mock_repo.count_interventions_in_last_24h.return_value = 0
    mock_bsky = AsyncMock()
    mock_bsky.has_postgate_quote_disabled.return_value = False
    mock_llm = AsyncMock()

    # Simula o critic reprovando por falta de pertinência socrática
    async def fake_complete(*args, **kwargs):
        if kwargs.get("purpose") == "critic_coherence":
            return "DECISAO: REPROVADA\nMOTIVO: A pergunta questiona dados que não constam no post."
        return "revisão de fontes"

    mock_llm.complete.side_effect = fake_complete
    mock_llm.complete_with_tools.return_value = (
        "TIPO: FATO\nVEREDITO: DESMENTE\nFONTE: 1\n"
        "Mas por que você afirma que o candidato gastou milhões na campanha?"
    )

    service = InterventionService(mock_repo, mock_bsky, mock_llm)
    service.settings.intervention_dry_run = False

    post = DomainPost(
        uri="at://did:1/post/drift",
        cid="cid1",
        author_did="did:1",
        text="Apoiando nosso candidato no segundo turno das eleições!",
        created_at=datetime.now(UTC),
    )
    verdict = Verdict(
        claim="Apoiando candidato no segundo turno",
        label=VerdictLabel.FALSE,
        confidence=0.9,
        rationale="r",
        evidences=[Evidence("t", "https://fonte.example", "Fonte", "trecho")],
    )

    res = await service.execute_intervention(
        post, Account(did="did:1", handle="user"), verdict, 0.1
    )
    # A intervenção DEVE ser abortada pelo Critic Semântico
    assert res is None
    mock_bsky.quote_post.assert_not_called()


@pytest.mark.asyncio
async def test_semantic_critic_approval_allows_intervention(monkeypatch):
    monkeypatch.setattr(
        "app.services.intervention.fetch_article_text",
        AsyncMock(return_value="texto completo da matéria sobre o resultado eleitoral"),
    )
    mock_repo = MagicMock()
    mock_repo.has_intervened_on_post.return_value = False
    mock_repo.count_interventions_by_author_in_last_24h.return_value = 0
    mock_repo.count_interventions_in_last_24h.return_value = 0
    mock_bsky = AsyncMock()
    mock_bsky.has_postgate_quote_disabled.return_value = False
    mock_bsky.quote_post.return_value = ("at://did:bot/quote/1", "cid_quote")
    mock_llm = AsyncMock()

    # Simula o critic aprovando a pertinência
    async def fake_complete(*args, **kwargs):
        if kwargs.get("purpose") == "critic_coherence":
            return "DECISAO: APROVADA\nMOTIVO: O questionamento dialoga diretamente com o post."
        return "revisão de fontes"

    mock_llm.complete.side_effect = fake_complete
    mock_llm.complete_with_tools.return_value = (
        "TIPO: FATO\nVEREDITO: DESMENTE\nFONTE: 1\n"
        "Será que a votação foi no 2º turno, já que a disputa encerrou no 1º?"
    )

    service = InterventionService(mock_repo, mock_bsky, mock_llm)
    service.settings.intervention_dry_run = False

    post = DomainPost(
        uri="at://did:1/post/valid",
        cid="cid1",
        author_did="did:1",
        text="Candidato venceu a disputa eleitoral no segundo turno das eleições.",
        created_at=datetime.now(UTC),
    )
    verdict = Verdict(
        claim="Candidato venceu disputa no segundo turno",
        label=VerdictLabel.FALSE,
        confidence=0.9,
        rationale="r",
        evidences=[Evidence("t", "https://fonte.example", "Fonte", "trecho")],
    )

    res = await service.execute_intervention(
        post, Account(did="did:1", handle="user"), verdict, 0.1
    )
    assert res == "at://did:bot/quote/1"
    mock_bsky.quote_post.assert_called_once()
