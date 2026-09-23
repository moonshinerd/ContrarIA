from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from app.domain.entities import Account, Post
from app.services.bot_scoring import BotScoringService


@pytest.fixture
def mock_engine():
    from sqlalchemy import create_engine

    from app.db.base import Base

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def mock_bsky():
    client = AsyncMock()
    client.get_profile.return_value = Account(
        did="did:1", handle="bot123", created_at=datetime.now(UTC)
    )
    client.get_author_feed.return_value = [
        Post(uri="at://p1", cid="c1", author_did="did:1", text="t", created_at=datetime.now(UTC))
    ]
    return client


@pytest.mark.asyncio
async def test_bot_scoring_get_assessment(mock_engine, mock_bsky, monkeypatch):
    service = BotScoringService(mock_engine, mock_bsky)
    # mock load weights to avoid depending on yaml
    service.weights = {"demographic_digits_handle": 1.0, "bias": 0.0}

    # First call evaluates and caches
    assessment1 = await service.get_assessment("did:1")
    assert assessment1.did == "did:1"
    assert "demographic_digits_handle" in assessment1.features

    # Second call should fetch from cache
    # If it fetches from cache, bsky client won't be called again
    mock_bsky.get_profile.reset_mock()
    assessment2 = await service.get_assessment("did:1")

    assert assessment1.score == assessment2.score
    mock_bsky.get_profile.assert_not_called()

    # Test handling of empty or no feed
    mock_bsky.get_author_feed.side_effect = AttributeError("Not implemented")
    assessment3 = await service.get_assessment("did:2")
    assert assessment3.did == "did:2"
