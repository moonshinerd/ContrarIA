from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.base import Base
from app.db.orm.label_events import LabelEvent
from app.domain.entities import Account, Post
from app.routers.v1.admin import check_ozone_health
from app.services.label_outbox import LabelOutbox
from app.worker import run_due_label_flush


def make(ozone=None, **settings):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    ozone = ozone or AsyncMock()
    outbox = LabelOutbox(Settings(_env_file=None, **settings), session, ozone)
    return outbox, session, ozone


def post(uri="at://p/1"):
    return Post(uri=uri, cid="cid1", author_did="d", text="t", created_at=datetime.now(UTC))


async def test_successful_emit_is_recorded_as_sent():
    outbox, session, ozone = make()

    event = await outbox.emit(post(), "possivel-desinformacao")

    ozone.emit_label.assert_awaited_once()
    assert event.status == "sent"
    assert event.attempts == 1
    assert event.sent_at is not None
    assert session.query(LabelEvent).count() == 1


async def test_failed_emit_stays_pending_with_backoff_and_does_not_raise():
    ozone = AsyncMock()
    ozone.emit_label.side_effect = RuntimeError("502 Bad Gateway")
    outbox, session, _ = make(ozone, label_retry_interval_seconds=60)

    event = await outbox.emit(post(), "possivel-desinformacao")

    assert event.status == "pending"
    assert event.attempts == 1
    assert "502" in event.last_error
    wait = event.next_attempt_at.replace(tzinfo=UTC) - datetime.now(UTC)
    assert timedelta(seconds=30) < wait <= timedelta(seconds=60)


async def test_flush_retries_due_events_and_delivers_after_recovery():
    ozone = AsyncMock()
    ozone.emit_label.side_effect = [RuntimeError("502"), None]
    outbox, session, _ = make(ozone, label_retry_interval_seconds=60)
    event = await outbox.emit(post(), "possivel-desinformacao")

    # Ainda não venceu: nada a repetir.
    assert await outbox.flush(now=datetime.now(UTC)) == 0
    assert ozone.emit_label.await_count == 1

    delivered = await outbox.flush(now=datetime.now(UTC) + timedelta(minutes=5))

    assert delivered == 1
    session.refresh(event)
    assert event.status == "sent"
    assert event.attempts == 2
    assert event.last_error is None


async def test_event_gives_up_as_failed_after_max_attempts():
    ozone = AsyncMock()
    ozone.emit_label.side_effect = RuntimeError("down")
    outbox, session, _ = make(ozone, label_retry_max_attempts=2, label_retry_interval_seconds=1)
    event = await outbox.emit(post(), "possivel-desinformacao")

    await outbox.flush(now=datetime.now(UTC) + timedelta(hours=1))

    session.refresh(event)
    assert event.status == "failed"
    assert event.attempts == 2
    # Evento falho não é mais repetido.
    ozone.emit_label.reset_mock()
    await outbox.flush(now=datetime.now(UTC) + timedelta(hours=2))
    ozone.emit_label.assert_not_awaited()


async def test_duplicate_pending_request_reuses_the_same_event():
    ozone = AsyncMock()
    ozone.emit_label.side_effect = RuntimeError("down")
    outbox, session, _ = make(ozone)

    await outbox.emit(post(), "possivel-desinformacao")
    await outbox.emit(post(), "possivel-desinformacao")

    assert session.query(LabelEvent).count() == 1


async def test_account_target_is_rebuilt_on_retry():
    ozone = AsyncMock()
    ozone.emit_label.side_effect = [RuntimeError("502"), None]
    outbox, session, _ = make(ozone, label_retry_interval_seconds=1)
    await outbox.emit(Account(did="did:plc:x", handle="h"), "provavel-bot")

    await outbox.flush(now=datetime.now(UTC) + timedelta(minutes=5))

    retried = ozone.emit_label.await_args.args[0]
    assert isinstance(retried, Account)
    assert retried.did == "did:plc:x"
    assert ozone.emit_label.await_args.kwargs["label_val"] == "provavel-bot"


async def test_post_target_keeps_uri_and_cid_on_retry():
    ozone = AsyncMock()
    ozone.emit_label.side_effect = [RuntimeError("502"), None]
    outbox, _, _ = make(ozone, label_retry_interval_seconds=1)
    await outbox.emit(post("at://p/9"), "possivel-desinformacao")

    await outbox.flush(now=datetime.now(UTC) + timedelta(minutes=5))

    retried = ozone.emit_label.await_args.args[0]
    assert (retried.uri, retried.cid) == ("at://p/9", "cid1")


async def test_worker_flush_waits_until_due_and_survives_errors():
    outbox = MagicMock()
    outbox.flush = AsyncMock()

    assert await run_due_label_flush(outbox, 10.0, 60.0, now=9.0) == 10.0
    outbox.flush.assert_not_awaited()

    assert await run_due_label_flush(outbox, 10.0, 60.0, now=12.0) == 72.0
    outbox.flush.assert_awaited_once()

    outbox.flush = AsyncMock(side_effect=RuntimeError("boom"))
    assert await run_due_label_flush(outbox, 10.0, 60.0, now=12.0) == 72.0
    outbox.db.rollback.assert_called_once()


def test_ozone_health_not_configured_and_reachable_and_down(monkeypatch):
    assert check_ozone_health("") == {"configured": False, "reachable": None}

    monkeypatch.setattr(httpx, "get", lambda *a, **k: httpx.Response(200))
    assert check_ozone_health("https://x/health") == {
        "configured": True,
        "reachable": True,
        "status_code": 200,
    }

    monkeypatch.setattr(httpx, "get", lambda *a, **k: httpx.Response(502))
    assert check_ozone_health("https://x/health")["reachable"] is False

    def boom(*a, **k):
        raise httpx.ConnectTimeout("t")

    monkeypatch.setattr(httpx, "get", boom)
    assert check_ozone_health("https://x/health") == {
        "configured": True,
        "reachable": False,
        "error": "ConnectTimeout",
    }
