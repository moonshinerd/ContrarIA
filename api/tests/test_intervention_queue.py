from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.base import Base
from app.db.orm.decisions import DecisionLog
from app.domain.entities import Account, Post, Verdict, VerdictLabel
from app.services.intervention_queue import InterventionCandidate, InterventionQueue


def make_queue(execute_results):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    intervention = MagicMock()
    intervention.execute_intervention = AsyncMock(side_effect=execute_results)
    ozone = AsyncMock()
    queue = InterventionQueue(Settings(_env_file=None), session, intervention, ozone)
    return queue, session, intervention


def add(queue, session, uri, confidence):
    decision = DecisionLog(
        post_uri=uri, post_snapshot={}, action="INTERVENE_QUEUED", justification="q"
    )
    session.add(decision)
    session.commit()
    post = Post(uri=uri, cid="c", author_did="d", text="t", created_at=datetime.now(UTC))
    verdict = Verdict(
        claim="c", label=VerdictLabel.MISLEADING, confidence=confidence, rationale="r"
    )
    queue.add(InterventionCandidate(decision.id, post, Account(did="d", handle="h"), verdict, 0.1))
    return decision.id


def actions(session):
    return {row.post_uri: row.action for row in session.query(DecisionLog)}


async def test_round_publishes_only_the_most_confident_candidate():
    queue, session, intervention = make_queue(["at://bot/1"])
    add(queue, session, "at://a", 0.85)
    add(queue, session, "at://b", 0.97)
    add(queue, session, "at://c", 0.90)

    published = await queue.run_round()

    assert published == "at://bot/1"
    assert intervention.execute_intervention.await_count == 1
    assert intervention.execute_intervention.await_args.args[0].uri == "at://b"
    assert actions(session) == {"at://a": "MONITOR", "at://b": "INTERVENE", "at://c": "MONITOR"}
    assert len(queue) == 0


async def test_round_falls_back_to_next_candidate_when_best_is_blocked():
    queue, session, intervention = make_queue([None, "at://bot/2"])
    add(queue, session, "at://a", 0.99)
    add(queue, session, "at://b", 0.90)

    published = await queue.run_round()

    assert published == "at://bot/2"
    assert actions(session) == {"at://a": "MONITOR", "at://b": "INTERVENE"}


async def test_empty_round_does_nothing():
    queue, _, intervention = make_queue([])
    assert await queue.run_round() is None
    intervention.execute_intervention.assert_not_called()


async def test_round_in_quiet_hours_publishes_nothing():
    queue, session, intervention = make_queue(["at://bot/1"])
    add(queue, session, "at://a", 0.95)
    three_am_brasilia = datetime(2026, 9, 28, 6, 0, tzinfo=UTC)

    assert await queue.run_round(now=three_am_brasilia) is None
    intervention.execute_intervention.assert_not_called()
    assert actions(session) == {"at://a": "MONITOR"}


def test_quiet_hours_boundaries():
    queue, _, _ = make_queue([])
    assert queue.in_quiet_hours(datetime(2026, 9, 28, 3, 0, tzinfo=UTC))  # 0h BRT
    assert queue.in_quiet_hours(datetime(2026, 9, 28, 9, 59, tzinfo=UTC))  # 6h59 BRT
    assert not queue.in_quiet_hours(datetime(2026, 9, 28, 10, 0, tzinfo=UTC))  # 7h BRT
    assert not queue.in_quiet_hours(datetime(2026, 9, 28, 2, 59, tzinfo=UTC))  # 23h59 BRT


def test_expire_stale_candidates_closes_them_as_monitor():
    from app.services.intervention_queue import expire_stale_candidates

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    stuck = DecisionLog(
        post_uri="at://a", post_snapshot={}, action="INTERVENE_QUEUED", justification="q"
    )
    already_done = DecisionLog(
        post_uri="at://b", post_snapshot={}, action="INTERVENE", justification="ok"
    )
    session.add_all([stuck, already_done])
    session.commit()

    expired = expire_stale_candidates(session)

    assert expired == 1
    session.refresh(stuck)
    session.refresh(already_done)
    assert stuck.action == "MONITOR"
    assert "expirado" in stuck.justification
    assert already_done.action == "INTERVENE"
