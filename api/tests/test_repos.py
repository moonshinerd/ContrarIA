from datetime import UTC, datetime

import pytest

from app.repositories.interventions import InterventionRepository
from app.repositories.posts import PostRepository


@pytest.fixture
def mock_engine():
    from sqlalchemy import create_engine

    from app.db.base import Base

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


def test_interventions_repo(mock_engine):
    repo = InterventionRepository(mock_engine)

    repo.record_intervention("at://p1", "did:1", "quote_post")

    assert repo.has_intervened_on_post("at://p1", "quote_post") is True
    assert repo.has_intervened_on_post("at://p2", "quote_post") is False

    assert repo.count_interventions_by_author_in_last_24h("did:1", "quote_post") == 1
    assert repo.count_interventions_in_last_24h("quote_post") == 1

    # record same again should do nothing (conflict handling)
    repo.record_intervention("at://p1", "did:1", "quote_post")
    assert repo.count_interventions_in_last_24h("quote_post") == 1


def test_posts_repo(mock_engine):
    repo = PostRepository(mock_engine)

    repo.set_cursor("jetstream", 100)
    assert repo.get_cursor("jetstream") == 100

    repo.set_cursor("jetstream", 200)
    assert repo.get_cursor("jetstream") == 200

    assert repo.get_cursor("search") == 0

    posts_data = [
        {
            "uri": "at://p1",
            "cid": "c1",
            "author_did": "did:1",
            "text": "t",
            "langs": ["pt"],
            "created_at": datetime.now(UTC),
            "source": "search",
        }
    ]
    repo.upsert_posts(posts_data)
    # Upsert same
    repo.upsert_posts(posts_data)
