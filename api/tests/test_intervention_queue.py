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
