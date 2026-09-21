"""Testes reais de pgvector; TEST_DATABASE_URL deve apontar a um banco de testes."""

import os
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, text

from app.db.base import Base
from app.repositories.fact_articles import FactArticleRepository


@pytest.fixture
def repo():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Defina TEST_DATABASE_URL para executar integração PostgreSQL/pgvector")
    engine = create_engine(url)
    with engine.connect() as connection:
        transaction = connection.begin()
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        Base.metadata.create_all(connection)
        # Banco de teste explicitamente separado; alterações sempre revertidas.
        connection.execute(text("DELETE FROM fact_articles"))
        yield FactArticleRepository(connection)
        transaction.rollback()
    engine.dispose()


def article(url, vector, date=None, source="boatos"):
    return dict(
        url=url,
        source=source,
        title=url,
        summary="Resumo",
        published_at=date,
        embedding=vector + [0.0] * (384 - len(vector)),
    )


def search(repo, vector, **kwargs):
    options = dict(sources=["boatos"], limit=5, weight=0.1, half_life=30, min_similarity=0.3)
    options.update(kwargs)
    return repo.search(vector + [0.0] * (384 - len(vector)), **options)


def test_upsert_and_recency_ranking(repo):
    now = datetime.now(UTC)
    rows = [
        article("old", [1, 0], now - timedelta(days=300)),
        article("new", [1, 0], now),
        article("irrelevant", [0, 1], now),
        article("disabled", [1, 0], now, source="tse"),
        article("undated", [1, 0]),
    ]
    repo.upsert(rows)
    assert repo.count() == 5
    assert repo.unchanged({k: v for k, v in rows[0].items() if k != "embedding"})
    rows[0]["title"] = "Atualizado"
    repo.upsert([rows[0]])
    assert repo.count() == 5
    results = search(repo, [1, 0])
    assert [r.url for r in results] == ["new", "old", "undated"]
    assert results[1].title == "Atualizado"


def test_semantic_filter_and_limit(repo):
    repo.upsert([article("relevant", [1, 0]), article("opposite", [-1, 0])])
    assert [r.url for r in search(repo, [1, 0], limit=1)] == ["relevant"]
    assert search(repo, [0, 1]) == []
    assert search(repo, [1, 0], sources=[]) == []
