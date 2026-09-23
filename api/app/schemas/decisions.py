from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class DecisionLogOut(BaseModel):
    id: int
    post_uri: str
    created_at: datetime
    post_snapshot: dict[str, Any]
    bot_score: float | None = None
    bot_features: dict[str, Any] | None = None
    sources: list[dict[str, Any]] | None = None
    agent_outputs: dict[str, Any] | None = None
    verdict: str | None = None
    confidence: float | None = None
    crc_threshold_used: float | None = None
    action: str
    justification: str

    model_config = {"from_attributes": True}


class AnalyzeRequest(BaseModel):
    post_url: str = Field(..., description="URL pública do post no Bluesky")
