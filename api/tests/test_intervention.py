from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.entities import Account, Evidence, Post, Verdict, VerdictLabel
from app.services.intervention import InterventionService, _build_source_batches


@pytest.fixture(autouse=True)
def mock_article_fetch(monkeypatch):
    """Evita I/O externo: a produção lê fontes antes de chamar o redator."""

    async def fetch(url: str, *, max_chars: int | None = None):
        return f"texto completo de {url}"

    from app.services import intervention

    monkeypatch.setattr(intervention, "fetch_article_text", fetch)


@pytest.fixture
def mock_repo():
    repo = MagicMock()
    repo.has_intervened_on_post.return_value = False
    repo.count_interventions_by_author_in_last_24h.return_value = 0
    repo.count_interventions_in_last_24h.return_value = 0
    return repo


@pytest.fixture
def mock_bsky():
    client = AsyncMock()
    client.login.return_value = "did:bot:self"
    client.has_postgate_quote_disabled.return_value = False
    client.quote_post.return_value = ("at://did:bot:self/app.bsky.feed.post/123", "cid_quote")
    client.reply_post.return_value = ("at://did:bot:self/app.bsky.feed.post/124", "cid_reply")
    return client


@pytest.fixture
def mock_llm():
    llm = AsyncMock()
    llm.complete.return_value = "FONTE 1: CONTRADIZ\nCITAÇÃO: trecho\nNOTA: nota factual"
    llm.complete_with_tools.return_value = (
        "TIPO: FATO\nVEREDITO: DESMENTE\nFONTE: 1\n"
        "Isso não confere com os dados públicos. O que acha?"
    )
    return llm


@pytest.mark.asyncio
async def test_intervention_dry_run(mock_repo, mock_bsky, mock_llm, monkeypatch):
    service = InterventionService(mock_repo, mock_bsky, mock_llm)
    service.settings.intervention_dry_run = True

    post = Post(
        uri="at://did:1/post/1",
        cid="cid1",
        author_did="did:1",
        text="fake",
        created_at=datetime.now(UTC),
    )
    author = Account(did="did:1", handle="user")
    verdict = Verdict(
        claim="fake claim",
        label=VerdictLabel.FALSE,
        confidence=0.9,
        rationale="It is fake.",
        evidences=[Evidence("test", "http://example.com", "t", "s")],
    )

    res = await service.execute_intervention(post, author, verdict, bot_score=0.1)

    assert res == "dry_run_uri"
    mock_llm.complete_with_tools.assert_called_once()
    mock_bsky.quote_post.assert_not_called()
    mock_repo.record_intervention.assert_not_called()


@pytest.mark.asyncio
async def test_intervention_live(mock_repo, mock_bsky, mock_llm):
    service = InterventionService(mock_repo, mock_bsky, mock_llm)
    service.settings.intervention_dry_run = False

    post = Post(
        uri="at://did:1/post/1",
        cid="cid1",
        author_did="did:1",
        text="fake",
        created_at=datetime.now(UTC),
    )
    author = Account(did="did:1", handle="user")
    verdict = Verdict(
        claim="fake claim",
        label=VerdictLabel.FALSE,
        confidence=0.9,
        rationale="It is fake.",
        evidences=[Evidence("test", "http://example.com", "t", "s")],
    )

    res = await service.execute_intervention(post, author, verdict, bot_score=0.1)

    assert res == "at://did:bot:self/app.bsky.feed.post/123"
    mock_bsky.quote_post.assert_called_once()


@pytest.mark.asyncio
async def test_intervention_anti_loop_daily_limit(mock_repo, mock_bsky, mock_llm):
    service = InterventionService(mock_repo, mock_bsky, mock_llm)
    service.settings.daily_max_interventions = 2
    mock_repo.count_interventions_in_last_24h.return_value = 2

    post = Post(
        uri="at://did:1/post/1",
        cid="cid1",
        author_did="did:1",
        text="fake",
        created_at=datetime.now(UTC),
    )
    author = Account(did="did:1", handle="user")
    verdict = Verdict(
        claim="fake claim",
        label=VerdictLabel.FALSE,
        confidence=0.9,
        rationale="It is fake.",
        evidences=[Evidence("test", "http://example.com", "t", "s")],
    )

    res = await service.execute_intervention(post, author, verdict, bot_score=0.1)
    assert res is None


@pytest.mark.asyncio
async def test_intervention_anti_loop_postgate(mock_repo, mock_bsky, mock_llm):
    service = InterventionService(mock_repo, mock_bsky, mock_llm)
    mock_bsky.has_postgate_quote_disabled.return_value = True

    post = Post(
        uri="at://did:1/post/1",
        cid="cid1",
        author_did="did:1",
        text="fake",
        created_at=datetime.now(UTC),
    )
    author = Account(did="did:1", handle="user")
    verdict = Verdict(
        claim="fake claim",
        label=VerdictLabel.FALSE,
        confidence=0.9,
        rationale="It is fake.",
        evidences=[Evidence("test", "http://example.com", "t", "s")],
    )

    res = await service.execute_intervention(post, author, verdict, bot_score=0.1)
    assert res is None


@pytest.mark.asyncio
async def test_intervention_low_confidence(mock_repo, mock_bsky, mock_llm):
    service = InterventionService(mock_repo, mock_bsky, mock_llm)
    post = Post(
        uri="at://p1", cid="c1", author_did="did:1", text="fake", created_at=datetime.now(UTC)
    )
    author = Account(did="did:1", handle="user")
    verdict = Verdict(
        claim="c", label=VerdictLabel.FALSE, confidence=0.7, rationale="r", evidences=[]
    )
    res = await service.execute_intervention(post, author, verdict, 0.1)
    assert res is None


@pytest.mark.asyncio
async def test_intervention_author_is_bot_self(mock_repo, mock_bsky, mock_llm):
    service = InterventionService(mock_repo, mock_bsky, mock_llm)
    post = Post(
        uri="at://p1",
        cid="c1",
        author_did="did:bot:self",
        text="fake",
        created_at=datetime.now(UTC),
    )
    author = Account(did="did:bot:self", handle="user")
    verdict = Verdict(
        claim="c", label=VerdictLabel.FALSE, confidence=0.9, rationale="r", evidences=[]
    )
    res = await service.execute_intervention(post, author, verdict, 0.1)
    assert res is None


@pytest.mark.asyncio
async def test_intervention_author_self_labeled_bot(mock_repo, mock_bsky, mock_llm):
    service = InterventionService(mock_repo, mock_bsky, mock_llm)
    post = Post(
        uri="at://p1", cid="c1", author_did="did:1", text="fake", created_at=datetime.now(UTC)
    )
    author = Account(did="did:1", handle="user", self_labels=["bot"])
    verdict = Verdict(
        claim="c", label=VerdictLabel.FALSE, confidence=0.9, rationale="r", evidences=[]
    )
    res = await service.execute_intervention(post, author, verdict, 0.1)
    assert res is None


@pytest.mark.asyncio
async def test_intervention_post_already_intervened(mock_repo, mock_bsky, mock_llm):
    service = InterventionService(mock_repo, mock_bsky, mock_llm)
    mock_repo.has_intervened_on_post.return_value = True
    post = Post(
        uri="at://p1", cid="c1", author_did="did:1", text="fake", created_at=datetime.now(UTC)
    )
    author = Account(did="did:1", handle="user")
    verdict = Verdict(
        claim="c", label=VerdictLabel.FALSE, confidence=0.9, rationale="r", evidences=[]
    )
    res = await service.execute_intervention(post, author, verdict, 0.1)
    assert res is None


@pytest.mark.asyncio
async def test_intervention_author_already_intervened(mock_repo, mock_bsky, mock_llm):
    service = InterventionService(mock_repo, mock_bsky, mock_llm)
    mock_repo.count_interventions_by_author_in_last_24h.return_value = 1
    post = Post(
        uri="at://p1", cid="c1", author_did="did:1", text="fake", created_at=datetime.now(UTC)
    )
    author = Account(did="did:1", handle="user")
    verdict = Verdict(
        claim="c", label=VerdictLabel.FALSE, confidence=0.9, rationale="r", evidences=[]
    )
    res = await service.execute_intervention(post, author, verdict, 0.1)
    assert res is None


@pytest.mark.asyncio
async def test_intervention_live_fail(mock_repo, mock_bsky, mock_llm):
    service = InterventionService(mock_repo, mock_bsky, mock_llm)
    service.settings.intervention_dry_run = False
    mock_bsky.quote_post.side_effect = Exception("API fail")
    post = Post(
        uri="at://p1", cid="c1", author_did="did:1", text="fake", created_at=datetime.now(UTC)
    )
    author = Account(did="did:1", handle="user")
    verdict = Verdict(
        claim="c",
        label=VerdictLabel.FALSE,
        confidence=0.9,
        rationale="r",
        evidences=[Evidence("t", "u", "s", "d")],
    )
    res = await service.execute_intervention(post, author, verdict, 0.1)
    assert res is None


@pytest.mark.asyncio
async def test_intervention_splits_long_text_into_thread(mock_repo, mock_bsky, mock_llm):
    """Texto acima do limite do Bluesky vira quote + replies encadeadas, com
    🧵 nos pedaços intermediários e o link da fonte só no último."""
    long_text = " ".join(f"palavra{i}" for i in range(120))  # bem acima de 300 grafemas
    mock_llm.complete_with_tools.return_value = (
        "TIPO: FATO\nVEREDITO: DESMENTE\nFONTE: 1\n" + long_text
    )
    mock_bsky.reply_post.side_effect = [
        (f"at://did:bot:self/app.bsky.feed.post/{124 + i}", f"cid_reply_{i}") for i in range(10)
    ]
    service = InterventionService(mock_repo, mock_bsky, mock_llm)
    service.settings.intervention_dry_run = False

    post = Post(
        uri="at://did:1/post/1",
        cid="cid1",
        author_did="did:1",
        text="fake",
        created_at=datetime.now(UTC),
    )
    author = Account(did="did:1", handle="user")
    verdict = Verdict(
        claim="fake claim",
        label=VerdictLabel.FALSE,
        confidence=0.9,
        rationale="It is fake.",
        evidences=[Evidence("test", "http://example.com", "t", "s")],
    )

    res = await service.execute_intervention(post, author, verdict, bot_score=0.1)

    assert res == "at://did:bot:self/app.bsky.feed.post/123"
    assert mock_bsky.reply_post.call_count >= 1

    first_call_text = mock_bsky.quote_post.call_args.kwargs["text"]
    assert first_call_text.endswith("🧵")
    assert mock_bsky.quote_post.call_args.kwargs["source_url"] is None

    last_call = mock_bsky.reply_post.call_args
    assert last_call.kwargs["source_url"] == "http://example.com"
    assert "🧵" not in last_call.kwargs["text"]

    # a primeira reply encadeia no quote (root e parent apontam pro post 123)
    first_reply_call = mock_bsky.reply_post.call_args_list[0]
    assert first_reply_call.kwargs["root_uri"] == "at://did:bot:self/app.bsky.feed.post/123"
    assert first_reply_call.kwargs["parent_uri"] == "at://did:bot:self/app.bsky.feed.post/123"


@pytest.mark.asyncio
async def test_intervention_consults_sources_and_cites_the_chosen_one(
    mock_repo, mock_bsky, mock_llm, monkeypatch
):
    from app.services import intervention

    opened: list[str] = []

    async def fake_fetch(url: str, *, max_chars: int | None = None):
        opened.append(url)
        return f"texto completo de {url}"

    monkeypatch.setattr(intervention, "fetch_article_text", fake_fetch)

    async def agent(system, user, *, tools, call_tool, max_tool_calls, purpose):
        assert max_tool_calls == 0
        assert tools == []
        assert "DATA E HORA ATUAIS: " in system and "horário de Brasília" in system
        assert "1. Fonte A (https://a)" in system and "2. Fonte B (https://b)" in system
        assert "FONTE 1: CONTRADIZ" in system
        return "TIPO: FATO\nVEREDITO: DISTORCE\nFONTE: 2\nSerá que a matéria B diz isso mesmo?"

    mock_llm.complete_with_tools.side_effect = agent
    service = InterventionService(mock_repo, mock_bsky, mock_llm)
    service.settings.intervention_dry_run = False
    post = Post(
        uri="at://did:1/post/1",
        cid="cid1",
        author_did="did:1",
        text="post",
        created_at=datetime.now(UTC),
    )
    verdict = Verdict(
        claim="c",
        label=VerdictLabel.MISLEADING,
        confidence=0.9,
        rationale="r",
        evidences=[
            Evidence("t", "https://a", "Fonte A", "trecho a"),
            Evidence("t", "https://b", "Fonte B", "trecho b"),
        ],
    )

    await service.execute_intervention(post, Account(did="did:1", handle="user"), verdict, 0.1)

    assert opened == ["https://a", "https://b"]
    source_reviews = [
        c for c in mock_llm.complete.call_args_list if c.kwargs.get("purpose") == "source_review"
    ]
    assert len(source_reviews) == 1
    _, kwargs = mock_bsky.quote_post.call_args
    assert kwargs["text"] == "Será que a matéria B diz isso mesmo?"
    assert kwargs["source_url"] == "https://b"


@pytest.mark.asyncio
async def test_intervention_abstains_when_no_evidence_article_can_be_read(
    mock_repo, mock_bsky, mock_llm, monkeypatch
):
    from app.services import intervention

    async def unavailable(url: str, *, max_chars: int | None = None):
        return None

    monkeypatch.setattr(intervention, "fetch_article_text", unavailable)
    service = InterventionService(mock_repo, mock_bsky, mock_llm)
    verdict = Verdict(
        claim="c",
        label=VerdictLabel.FALSE,
        confidence=0.9,
        rationale="r",
        evidences=[Evidence("t", "https://a", "Fonte A", "trecho")],
    )
    post = Post(
        uri="at://did:1/post/1",
        cid="cid1",
        author_did="did:1",
        text="post",
        created_at=datetime.now(UTC),
    )

    result = await service.execute_intervention(
        post, Account(did="did:1", handle="user"), verdict, 0.1
    )

    assert result is None
    mock_llm.complete_with_tools.assert_not_called()
    mock_bsky.quote_post.assert_not_called()


@pytest.mark.asyncio
async def test_intervention_abstains_when_full_sources_exceed_cost_cap(
    mock_repo, mock_bsky, mock_llm, monkeypatch
):
    service = InterventionService(mock_repo, mock_bsky, mock_llm)
    monkeypatch.setattr(service.settings, "llm_source_review_max_chars", 1)
    verdict = Verdict(
        claim="c",
        label=VerdictLabel.FALSE,
        confidence=0.9,
        rationale="r",
        evidences=[Evidence("t", "https://a", "Fonte A", "trecho")],
    )
    post = Post(
        uri="at://did:1/post/1",
        cid="cid1",
        author_did="did:1",
        text="post",
        created_at=datetime.now(UTC),
    )

    result = await service.execute_intervention(
        post, Account(did="did:1", handle="user"), verdict, 0.1
    )

    assert result is None
    mock_llm.complete.assert_not_called()
    mock_bsky.quote_post.assert_not_called()


def test_source_batches_preserve_every_character_and_split_large_articles():
    sources = [
        Evidence("t", "https://a", "Fonte A", "s"),
        Evidence("t", "https://b", "Fonte B", "s"),
    ]
    articles = ["A" * 100, "B" * 100]

    batches = _build_source_batches(sources, articles, input_budget_tokens=40)

    combined = "".join(batches)
    assert len(batches) >= 2
    assert combined.count("A") >= 100
    assert combined.count("B") >= 100
    assert "FONTE 1: Fonte A" in combined
    assert "FONTE 2: Fonte B" in combined


@pytest.mark.asyncio
async def test_intervention_without_source_line_cites_the_most_relevant(
    mock_repo, mock_bsky, mock_llm
):
    mock_llm.complete_with_tools.return_value = (
        "TIPO: FATO\nVEREDITO: DESMENTE\nSerá que isso confere?"
    )
    service = InterventionService(mock_repo, mock_bsky, mock_llm)
    service.settings.intervention_dry_run = False
    post = Post(
        uri="at://did:1/post/1",
        cid="cid1",
        author_did="did:1",
        text="post",
        created_at=datetime.now(UTC),
    )
    verdict = Verdict(
        claim="c",
        label=VerdictLabel.FALSE,
        confidence=0.9,
        rationale="r",
        evidences=[Evidence("t", "https://a", "A", "a"), Evidence("t", "https://b", "B", "b")],
    )

    await service.execute_intervention(post, Account(did="did:1", handle="user"), verdict, 0.1)

    _, kwargs = mock_bsky.quote_post.call_args
    assert kwargs["source_url"] == "https://a"


@pytest.mark.asyncio
async def test_intervention_vetoed_when_agent_says_sources_confirm_the_post(
    mock_repo, mock_bsky, mock_llm
):
    mock_llm.complete_with_tools.return_value = "TIPO: FATO\nVEREDITO: CONFIRMA\nFONTE: 0"
    service = InterventionService(mock_repo, mock_bsky, mock_llm)
    service.settings.intervention_dry_run = False
    post = Post(
        uri="at://did:1/post/1",
        cid="cid1",
        author_did="did:1",
        text="post",
        created_at=datetime.now(UTC),
    )
    verdict = Verdict(
        claim="c",
        label=VerdictLabel.MISLEADING,
        confidence=0.9,
        rationale="r",
        evidences=[Evidence("t", "https://a", "A", "a")],
    )

    result = await service.execute_intervention(
        post, Account(did="did:1", handle="user"), verdict, 0.1
    )

    assert result is None
    mock_bsky.quote_post.assert_not_called()
    mock_repo.record_intervention.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "agent_output",
    [
        "Será que isso confere?",
        "TIPO: FATO\nVEREDITO: CONFIRMA\nFONTE: 1\nMesmo assim, será?",
        "VEREDITO: DESMENTE\nFONTE: 1\nSem a linha de tipo.",
        "TIPO: OPINIAO\nVEREDITO: DISTORCE\nFONTE: 1\nPrevisão não se corrige.",
    ],
)
async def test_intervention_not_published_without_actionable_agent_verdict(
    mock_repo, mock_bsky, mock_llm, agent_output
):
    mock_llm.complete_with_tools.return_value = agent_output
    service = InterventionService(mock_repo, mock_bsky, mock_llm)
    service.settings.intervention_dry_run = False
    post = Post(
        uri="at://did:1/post/1",
        cid="cid1",
        author_did="did:1",
        text="post",
        created_at=datetime.now(UTC),
    )
    verdict = Verdict(
        claim="c",
        label=VerdictLabel.FALSE,
        confidence=0.9,
        rationale="r",
        evidences=[Evidence("t", "https://a", "A", "a")],
    )

    result = await service.execute_intervention(
        post, Account(did="did:1", handle="user"), verdict, 0.1
    )

    assert result is None
    mock_bsky.quote_post.assert_not_called()
