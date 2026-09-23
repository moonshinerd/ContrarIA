import pytest

from app.domain.prioritization import (
    calculate_relevance,
    evaluate_gq04_matrix,
)


def test_calculate_relevance():
    rel = calculate_relevance(
        likes=10,
        reposts=5,
        replies=2,
        quotes=1,
        velocity=2.0,
        followers=1000,
    )
    # engagement = 10 + 10 + 4 + 3 = 27
    # log(28) * 0.5 + log(3) * 0.3 + log(1001) * 0.2
    assert rel > 0


@pytest.mark.parametrize(
    "is_pol, relevance, bot, false, harm, expected_status, expected_priority_base",
    [
        (False, 100.0, 1.0, 1.0, False, "discarded", 0.0),
        (True, 10.0, 0.1, 0.1, True, "queued", 110.0),  # Harm overrides all -> 100 + relevance
        (True, 0.5, 0.1, 0.1, False, "monitor", 0.5),  # Low reach -> monitor
        (True, 5.0, 0.9, 0.1, False, "queued", 55.0),  # High reach, suspect bot -> queued
        (True, 5.0, 0.1, 0.9, False, "queued", 55.0),  # High reach, suspect false -> queued
        (True, 5.0, 0.1, 0.1, False, "monitor", 5.0),  # High reach, no suspicion -> monitor
    ],
)
def test_gq04_matrix(is_pol, relevance, bot, false, harm, expected_status, expected_priority_base):
    # Thresholds: relevance >= 1.0, bot >= 0.8, false >= 0.8
    res = evaluate_gq04_matrix(
        is_political=is_pol,
        relevance=relevance,
        bot_suspicion=bot,
        falsehood_chance=false,
        public_harm_risk=harm,
        threshold_relevance=1.0,
        threshold_bot=0.8,
        threshold_falsehood=0.8,
    )

    assert res.triage_status == expected_status
    assert res.priority == expected_priority_base
