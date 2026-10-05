import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.entities import Post as DomainPost
from app.jobs.refresh_engagement import EngagementRefresher


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
    client.get_posts.return_value = [
        DomainPost(
            uri="at://p1",
            cid="c1",
            author_did="did:1",
            text="t",
            created_at=datetime.now(UTC),
            like_count=10000,
            repost_count=5,
            reply_count=2,
            quote_count=1,
        )
    ]
    return client


@pytest.mark.asyncio
async def test_refresh_engagement_run_cycle(mock_engine, mock_bsky, monkeypatch):
    refresher = EngagementRefresher(mock_engine, mock_bsky, tick_seconds=0)

    # Mock candidate uris
    monkeypatch.setattr(refresher, "_get_candidate_uris", MagicMock(return_value=["at://p1"]))

    # Run a single cycle by overriding the infinite loop
    async def single_run():
        uris = refresher._get_candidate_uris()
        if uris:
            hydrated = await refresher.bsky_client.get_posts(uris)
            refresher._save_snapshots_and_update_priority(hydrated)

    await single_run()

    mock_bsky.get_posts.assert_called_once_with(["at://p1"])


def test_get_candidate_uris(mock_engine, mock_bsky):
    from sqlalchemy.orm import Session

    from app.db.orm.posts import Post

    refresher = EngagementRefresher(mock_engine, mock_bsky, tick_seconds=0)

    with Session(mock_engine) as session:
        now = datetime.now(UTC)
        p = Post(
            uri="at://p1", cid="c1", author_did="d1", text="t", created_at=now, source="jetstream"
        )
        p.triage_status = "monitor"
        p.first_seen_at = now - timedelta(hours=1)
        session.add(p)
        session.commit()

    uris = refresher._get_candidate_uris()
    assert "at://p1" in uris


def test_save_snapshots(mock_engine, mock_bsky):
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    from app.db.orm.posts import Post, PostEngagementSnapshot

    refresher = EngagementRefresher(mock_engine, mock_bsky, tick_seconds=0)

    with Session(mock_engine) as session:
        now = datetime.now(UTC)
        p = Post(
            uri="at://p1",
            cid="c1",
            author_did="d1",
            text="urna",
            created_at=now,
            source="jetstream",
        )
        p.triage_status = "monitor"
        p.first_seen_at = now - timedelta(hours=1)
        session.add(p)
        session.commit()

    # Snapshot
    post1 = DomainPost(
        uri="at://p1",
        cid="c1",
        author_did="d1",
        text="urna",
        created_at=now,
        like_count=10000,
        repost_count=5,
        reply_count=2,
        quote_count=1,
    )

    refresher._save_snapshots_and_update_priority([post1])

    with Session(mock_engine) as session:
        snaps = list(session.scalars(select(PostEngagementSnapshot)))
        assert len(snaps) == 1
        assert snaps[0].likes == 10000

        post_db = session.get(Post, "at://p1")
        assert post_db.priority is not None
        assert post_db.triage_status == "monitor"


def test_save_snapshots_with_velocity(mock_engine, mock_bsky):
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    from app.db.orm.posts import Post, PostEngagementSnapshot

    refresher = EngagementRefresher(mock_engine, mock_bsky, tick_seconds=0)

    now = datetime.now(UTC)
    with Session(mock_engine) as session:
        p = Post(
            uri="at://p2", cid="c2", author_did="d2", text="u", created_at=now, source="search"
        )
        p.triage_status = "monitor"
        p.first_seen_at = now - timedelta(hours=2)
        session.add(p)

        # Add an old snapshot
        snap = PostEngagementSnapshot(
            uri="at://p2", ts=now - timedelta(hours=1), likes=2, reposts=1, replies=0, quotes=0
        )
        session.add(snap)
        session.commit()

    # Snapshot updated
    post_updated = DomainPost(
        uri="at://p2",
        cid="c2",
        author_did="d2",
        text="u",
        created_at=now,
        like_count=12,
        repost_count=2,
        reply_count=1,
        quote_count=1,
    )

    refresher._save_snapshots_and_update_priority([post_updated])

    with Session(mock_engine) as session:
        snaps = list(
            session.scalars(
                select(PostEngagementSnapshot).order_by(PostEngagementSnapshot.ts.desc())
            )
        )
        assert len(snaps) == 2
        assert snaps[0].likes == 12

        post_db = session.get(Post, "at://p2")
        assert post_db.priority is not None
        assert post_db.priority > 0


@pytest.mark.parametrize("final_status", ["processed", "ignored"])
def test_refresh_does_not_requeue_already_decided_post(mock_engine, mock_bsky, final_status):
    from sqlalchemy.orm import Session

    from app.db.orm.posts import Post

    refresher = EngagementRefresher(mock_engine, mock_bsky, tick_seconds=0)
    now = datetime.now(UTC)
    with Session(mock_engine) as session:
        p = Post(
            uri="at://p3", cid="c3", author_did="d3", text="u", created_at=now, source="search"
        )
        p.triage_status = final_status
        p.first_seen_at = now - timedelta(hours=1)
        session.add(p)
        session.commit()

    refresher._save_snapshots_and_update_priority(
        [
            DomainPost(
                uri="at://p3",
                cid="c3",
                author_did="d3",
                text="u",
                created_at=now,
                like_count=10000,
                repost_count=5,
                reply_count=2,
                quote_count=1,
            )
        ]
    )

    with Session(mock_engine) as session:
        post_db = session.get(Post, "at://p3")
        assert post_db.triage_status == final_status
        assert post_db.priority is not None


@pytest.mark.asyncio
async def test_refresh_poda_a_fila_quando_ha_teto(mock_engine, mock_bsky, monkeypatch):
    """Depois do refresh a fila volta a ter só os de maior prioridade (teto configurado)."""
    from unittest.mock import patch

    refresher = EngagementRefresher(mock_engine, mock_bsky, tick_seconds=0, queue_max_pending=100)
    monkeypatch.setattr(refresher, "_get_candidate_uris", MagicMock(return_value=["at://p1"]))
    monkeypatch.setattr(refresher, "_save_snapshots_and_update_priority", MagicMock())

    async def parar(_):
        raise asyncio.CancelledError

    with patch("app.jobs.refresh_engagement.PostRepository") as repo_cls:
        repo_cls.return_value.trim_pending.return_value = 7
        monkeypatch.setattr("app.jobs.refresh_engagement.asyncio.sleep", parar)
        with pytest.raises(asyncio.CancelledError):
            await refresher.run()

    repo_cls.return_value.trim_pending.assert_called_once_with(100)


@pytest.mark.asyncio
async def test_refresh_sem_teto_nao_poda(mock_engine, mock_bsky, monkeypatch):
    from unittest.mock import patch

    refresher = EngagementRefresher(mock_engine, mock_bsky, tick_seconds=0)
    monkeypatch.setattr(refresher, "_get_candidate_uris", MagicMock(return_value=["at://p1"]))
    monkeypatch.setattr(refresher, "_save_snapshots_and_update_priority", MagicMock())

    async def parar(_):
        raise asyncio.CancelledError

    with patch("app.jobs.refresh_engagement.PostRepository") as repo_cls:
        monkeypatch.setattr("app.jobs.refresh_engagement.asyncio.sleep", parar)
        with pytest.raises(asyncio.CancelledError):
            await refresher.run()

    repo_cls.return_value.trim_pending.assert_not_called()
