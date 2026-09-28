import math
from dataclasses import dataclass
from typing import Literal


@dataclass
class PrioritizationResult:
    triage_status: Literal["monitor", "queued", "discarded"]
    priority: float


def calculate_relevance(
    likes: int,
    reposts: int,
    replies: int,
    quotes: int,
    velocity: float,
    followers: int,
    weight_engagement: float = 0.5,
    weight_velocity: float = 0.3,
    weight_followers: float = 0.2,
) -> float:
    """Relevância = combinação ponderada de log(engajamento), velocidade e seguidores."""
    engagement = likes + (reposts * 2) + (replies * 2) + (quotes * 3)
    log_engagement = math.log1p(engagement)
    log_followers = math.log1p(followers)
    log_velocity = math.log1p(velocity)

    return (
        (log_engagement * weight_engagement)
        + (log_velocity * weight_velocity)
        + (log_followers * weight_followers)
    )


def evaluate_gq04_matrix(
    is_political: bool,
    relevance: float,
    bot_suspicion: float,
    falsehood_chance: float,
    public_harm_risk: bool,
    threshold_relevance: float,
    threshold_bot: float,
    threshold_falsehood: float,
) -> PrioritizationResult:
    """Implementa a matriz de priorização da GQ04."""
    if not is_political:
        return PrioritizationResult("discarded", 0.0)

    if public_harm_risk:
        # Risco de dano público -> Prioridade Máxima
        return PrioritizationResult("queued", 100.0 + relevance)

    is_high_reach = relevance >= threshold_relevance
    is_suspect_bot = bot_suspicion >= threshold_bot
    is_suspect_false = falsehood_chance >= threshold_falsehood

    if not is_high_reach:
        return PrioritizationResult("monitor", relevance)

    if is_suspect_bot or is_suspect_false:
        return PrioritizationResult("queued", 50.0 + relevance)

    # Alto engajamento, mas sem suspeitas claras
    return PrioritizationResult("monitor", relevance)
