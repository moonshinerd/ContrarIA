from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.domain.entities import Account, Post, Verdict, VerdictLabel
from app.domain.press_guard import is_press_or_official_author
from app.services.pipeline import PipelineService


def test_is_press_or_official_author_handles():
    # Handles específicos configurados por default
    assert is_press_or_official_author(handle="poder360.bsky.social")
    assert is_press_or_official_author(handle="folha.bsky.social")
    assert is_press_or_official_author(handle="estadao.bsky.social")
    assert is_press_or_official_author(handle="g1.bsky.social")
    assert is_press_or_official_author(handle="oglobo.bsky.social")
    assert is_press_or_official_author(handle="cnnbrasil.bsky.social")
    assert is_press_or_official_author(handle="correiocb.bsky.social")
    assert is_press_or_official_author(handle="capitalnews.bsky.social")
    assert is_press_or_official_author(handle="brasil247.bsky.social")
    assert is_press_or_official_author(handle="cartacapital.bsky.social")
    assert is_press_or_official_author(handle="metropoles.bsky.social")
    assert is_press_or_official_author(handle="uol.bsky.social")
    assert is_press_or_official_author(handle="bbc.bsky.social")
    assert is_press_or_official_author(handle="reuters.bsky.social")
    assert is_press_or_official_author(handle="aosfatos.bsky.social")
    assert is_press_or_official_author(handle="lupa.bsky.social")
    assert is_press_or_official_author(handle="g1-bot-rss.adilson.net.br")
    assert is_press_or_official_author(handle="tse.jus.br")
    assert is_press_or_official_author(handle="stf.jus.br")
    assert is_press_or_official_author(handle="camara.leg.br")
    assert is_press_or_official_author(handle="senado.leg.br")
    assert is_press_or_official_author(handle="planalto.gov.br")

    # Domínios jornalísticos e oficiais
    assert is_press_or_official_author(handle="g1.globo.com")
    assert is_press_or_official_author(handle="folha.uol.com.br")
    assert is_press_or_official_author(handle="metropoles.com")
    assert is_press_or_official_author(handle="tribunal.jus.br")
    assert is_press_or_official_author(handle="ministerio.gov.br")
    assert is_press_or_official_author(handle="aosfatos.org")

    # Usuário comum não deve casar
    assert not is_press_or_official_author(handle="joao123.bsky.social")
    assert not is_press_or_official_author(handle="maria_politica.bsky.social")


def test_is_press_or_official_author_display_names():
    # Heurística de palavras inteiras
    assert is_press_or_official_author(display_name="Poder360")
    assert is_press_or_official_author(display_name="Jornal Capital News")
    assert is_press_or_official_author(display_name="Folha de S.Paulo")
    assert is_press_or_official_author(display_name="Estadão")
    assert is_press_or_official_author(display_name="G1 - O portal de notícias da Globo")
    assert is_press_or_official_author(display_name="Correio Braziliense")
    assert is_press_or_official_author(display_name="Agência Lupa")
    assert is_press_or_official_author(display_name="Aos Fatos")
    assert is_press_or_official_author(display_name="Rádio CBN")
    assert is_press_or_official_author(display_name="TV Senado")
    assert is_press_or_official_author(display_name="TSE")
    assert is_press_or_official_author(display_name="STF")
    assert is_press_or_official_author(display_name="Câmara dos Deputados")
    assert is_press_or_official_author(display_name="Senado Federal")
    assert is_press_or_official_author(display_name="Portal UOL")

    # Usuário comum não deve casar
    assert not is_press_or_official_author(display_name="Carlos Eduardo")
    assert not is_press_or_official_author(display_name="Ana Silva")


@pytest.mark.anyio
async def test_pipeline_press_guard_poder360_false_verdict_monitors_without_intervention():
    """Poder360 com veredito adverso (FALSE) resulta em MONITOR sem intervenção."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session = Session(engine)

    settings = MagicMock()
    settings.crc_alpha = 0.05
    settings.pipeline_bot_scoring_enabled = True
    settings.pipeline_verification_enabled = True
    settings.pipeline_intervention_enabled = True
    settings.pipeline_labeler_enabled = True
    settings.pipeline_bot_ignore_threshold = 0.9
    settings.pipeline_min_followers_for_intervention = 0
    settings.intervention_dry_run = False
    settings.thread_context_max_posts = 4
    settings.thread_context_max_chars = 3000
    settings.press_account_handles = ["poder360.bsky.social"]

    bluesky = MagicMock()
    # Retorna perfil oficial do Poder360
    author_account = Account(
        did="did:plc:poder360fake",
        handle="poder360.bsky.social",
        display_name="Poder360",
        followers_count=150_000,
    )
    bluesky.get_profile = AsyncMock(return_value=author_account)
    bluesky.get_posts = AsyncMock(return_value=[])
    bluesky.get_thread_context = AsyncMock(return_value=None)

    ozone = MagicMock()
    ozone.emit_label = AsyncMock()

    bots = MagicMock()
    bots.get_assessment = AsyncMock(return_value=MagicMock(score=0.1, features={}))

    verification = MagicMock()
    adverse_verdict = Verdict(
        claim="Flávio Bolsonaro tem 61% das intenções",
        label=VerdictLabel.FALSE,
        confidence=0.99,
        rationale="Pesquisa falsa",
        evidences=[],
    )
    verification.verify = AsyncMock(return_value=adverse_verdict)

    intervention = MagicMock()
    intervention.execute_intervention = AsyncMock()

    pipeline = PipelineService(
        settings=settings,
        db_session=session,
        bluesky=bluesky,
        ozone=ozone,
        bots=bots,
        verification=verification,
        intervention=intervention,
    )

    post = Post(
        uri="at://did:plc:poder360fake/app.bsky.feed.post/999",
        cid="cid_poder360",
        author_did="did:plc:poder360fake",
        author_handle="poder360.bsky.social",
        text="#PoderData Pesquisa PoderData/Aya ... intenções de voto avançaram em 3 dias",
        created_at=datetime.now(UTC),
    )

    # Executa analyze passando veredito falso explicitamente (como o coletor faria)
    decision = await pipeline.analyze(post, verdict=adverse_verdict)

    # Decisão deve ser MONITOR com justificativa clara
    assert decision.action == "MONITOR"
    assert decision.justification == "Autor é veículo de imprensa/órgão oficial. Sem intervenção."
    assert decision.verdict == VerdictLabel.FALSE.value

    # Nenhuma intervenção ou rótulo deve ter sido executado
    intervention.execute_intervention.assert_not_called()
    ozone.emit_label.assert_not_called()
