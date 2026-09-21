"""Entidades de domínio puras (sem SQLAlchemy/Pydantic/FastAPI).

São o contrato compartilhado entre as trilhas: coleta produz `Post`/`Account`,
bot score preenche `BotAssessment`, verificação produz `Verdict`, e o
orquestrador registra `Decision` (RF13). Mudar um campo aqui é mudança de
contrato -- combine com as outras duplas no PR.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class VerdictLabel(StrEnum):
    TRUE = "true"
    FALSE = "false"
    MISLEADING = "misleading"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"  # abstenção (GQ03, RNF01)


class Action(StrEnum):
    IGNORE = "ignore"
    MONITOR = "monitor"  # RF10
    QUOTE_POST = "quote_post"  # RF05
    LABEL = "label"  # RF07


@dataclass
class Account:
    did: str
    handle: str
    display_name: str = ""
    description: str = ""
    avatar_url: str | None = None
    created_at: datetime | None = None
    followers_count: int = 0
    follows_count: int = 0
    posts_count: int = 0
    self_labels: list[str] = field(default_factory=list)
    labels: list[str] = field(default_factory=list)  # todos os rótulos (inclui de labelers)


@dataclass
class Post:
    uri: str
    cid: str
    author_did: str
    text: str
    created_at: datetime
    langs: list[str] = field(default_factory=list)
    like_count: int = 0
    repost_count: int = 0
    reply_count: int = 0
    quote_count: int = 0
    author_handle: str = ""
    is_repost: bool = False  # só em feeds de autor: item é repost de outra conta


@dataclass
class BotAssessment:
    did: str
    score: float  # [0, 1]; maior = mais provável ser automatizada
    features: dict[str, float] = field(default_factory=dict)


@dataclass
class Evidence:
    source: str  # ex.: "google_factcheck", "wikipedia", "tavily"
    url: str
    title: str
    snippet: str
    published_at: datetime | None = None
    rating: str | None = None  # ClaimReview, quando houver


@dataclass
class Verdict:
    claim: str
    label: VerdictLabel
    confidence: float  # [0, 1]
    rationale: str
    evidences: list[Evidence] = field(default_factory=list)
    agent_outputs: dict[str, str] = field(default_factory=dict)  # Self-RAG e debate


@dataclass
class Decision:
    post_uri: str
    action: Action
    relevance_score: float
    bot_score: float | None
    verdict: Verdict | None
    reason: str
    decided_at: datetime
