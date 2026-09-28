from unittest.mock import AsyncMock, MagicMock

from app.worker import run_due_intervention_round


async def test_due_intervention_round_runs_and_schedules_next_window():
    queue = MagicMock()
    queue.run_round = AsyncMock()

    next_round = await run_due_intervention_round(
        queue, next_round=10.0, round_seconds=60.0, now=12.0
    )

    queue.run_round.assert_awaited_once()
    assert next_round == 72.0


async def test_intervention_round_waits_when_window_is_not_due():
    queue = MagicMock()
    queue.run_round = AsyncMock()

    next_round = await run_due_intervention_round(
        queue, next_round=10.0, round_seconds=60.0, now=9.0
    )

    queue.run_round.assert_not_awaited()
    assert next_round == 10.0


async def test_intervention_round_failure_rolls_back_and_keeps_worker_alive():
    queue = MagicMock()
    queue.run_round = AsyncMock(side_effect=RuntimeError("boom"))

    next_round = await run_due_intervention_round(
        queue, next_round=10.0, round_seconds=60.0, now=12.0
    )

    queue.db.rollback.assert_called_once()
    assert next_round == 72.0
