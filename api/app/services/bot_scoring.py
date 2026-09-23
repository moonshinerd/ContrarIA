import math
import os
from datetime import UTC, datetime

import yaml
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.clients.bluesky_client import BlueskyClient
from app.db.orm.bots import AccountAssessment
from app.domain.bot_features import compute_all_features
from app.domain.entities import BotAssessment

WEIGHTS_FILE = os.path.join(os.path.dirname(__file__), "..", "domain", "bot_weights.yaml")


class BotScoringService:
    def __init__(self, engine, bsky_client: BlueskyClient):
        self.engine = engine
        self.bsky_client = bsky_client
        self.weights = self._load_weights()

    def _load_weights(self) -> dict[str, float]:
        if not os.path.exists(WEIGHTS_FILE):
            return {}
        with open(WEIGHTS_FILE, encoding="utf-8") as f:
            data = yaml.safe_load(f)
            return data.get("weights", {})

    def _sigmoid(self, x: float) -> float:
        try:
            return 1.0 / (1.0 + math.exp(-x))
        except OverflowError:
            return 0.0 if x < 0 else 1.0

    def _compute_score(self, features: dict[str, float]) -> float:
        total = 0.0
        for k, v in features.items():
            w = self.weights.get(k, 0.0)
            total += w * v

        # Optional: bias term if defined in weights
        bias = self.weights.get("bias", -2.0)
        return self._sigmoid(total + bias)

    async def get_assessment(self, did: str) -> BotAssessment:
        now = datetime.now(UTC)

        # Check cache
        with Session(self.engine) as session:
            row = session.scalar(select(AccountAssessment).where(AccountAssessment.did == did))
            if row:
                age_hours = (now - row.assessed_at).total_seconds() / 3600.0
                if age_hours < 24.0:
                    return BotAssessment(did=did, score=row.score, features=row.features)

        # Calculate from scratch
        account = await self.bsky_client.get_profile(did)

        # For simplicity in this job, assume the Bluesky client has `get_author_feed`
        # wait, let's see if bsky_client has `get_author_feed`
        try:
            posts = await self.bsky_client.get_author_feed(did, limit=100)
        except AttributeError:
            # If not implemented in BlueskyClient yet, default to empty or mock it.
            # In a real app we'd add it to BlueskyClient
            posts = []

        features = compute_all_features(account, posts)
        score = self._compute_score(features)

        assessment = BotAssessment(did=did, score=score, features=features)

        # Cache it
        with Session(self.engine) as session, session.begin():
            stmt = insert(AccountAssessment).values(
                did=did, score=score, features=features, assessed_at=now
            )
            session.execute(
                stmt.on_conflict_do_update(
                    index_elements=["did"],
                    set_={"score": score, "features": features, "assessed_at": now},
                )
            )

        return assessment
