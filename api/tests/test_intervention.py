from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.entities import Account, Evidence, Post, Verdict, VerdictLabel
from app.services.intervention import InterventionService


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
    client.quote_post.return_value = "at://did:bot:self/app.bsky.feed.post/123"
    return client


@pytest.fixture
def mock_llm():
    llm = AsyncMock()
    llm.generate.return_value = "Isso não confere com os dados públicos. O que acha?"
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
        created_at=datetime.now(UTC)
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
    mock_llm.generate.assert_called_once()
    mock_bsky.quote_post.assert_not_called()
    mock_repo.record_intervention.assert_called_once_with(post.uri, post.author_did, "quote_post")


@pytest.mark.asyncio
async def test_intervention_live(mock_repo, mock_bsky, mock_llm):
    service = InterventionService(mock_repo, mock_bsky, mock_llm)
    service.settings.intervention_dry_run = False

    post = Post(
        uri="at://did:1/post/1",
        cid="cid1",
        author_did="did:1",
        text="fake",
        created_at=datetime.now(UTC)
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
        created_at=datetime.now(UTC)
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
        created_at=datetime.now(UTC)
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
