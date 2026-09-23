import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from unittest.mock import AsyncMock, MagicMock, patch

from app.main import app
from app.db.base import Base
from app.routers.v1.decisions import get_db, get_pipeline
from app.db.orm.decisions import DecisionLog
from app.services.pipeline import PipelineService
from app.domain.entities import Post, Verdict, VerdictLabel, Evidence, BotAssessment

from sqlalchemy.pool import StaticPool
engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
Base.metadata.create_all(bind=engine)

def override_get_db():
    with Session(engine) as session:
        yield session

# Fake objects para injetar no pipeline
class FakeBlueskyClient:
    def __init__(self):
        self.get_profile = AsyncMock()
        self.get_posts = AsyncMock()
        
class FakeOzoneClient:
    def __init__(self):
        self.emit_label = AsyncMock()
        
class FakeBotScoringService:
    def __init__(self):
        self.get_assessment = AsyncMock()
        
class FakeVerificationService:
    def __init__(self):
        self.verify = AsyncMock()
        
class FakeInterventionService:
    def __init__(self):
        self.execute_intervention = AsyncMock()

_global_pipeline = None

def override_get_pipeline():
    global _global_pipeline
    if _global_pipeline is None:
        settings = MagicMock()
        settings.crc_alpha = 0.05
        
        bluesky = FakeBlueskyClient()
        ozone = FakeOzoneClient()
        bots = FakeBotScoringService()
        verif = FakeVerificationService()
        interv = FakeInterventionService()
        
        _global_pipeline = PipelineService(
            settings=settings,
            db_session=Session(engine),
            bluesky=bluesky,
            ozone=ozone,
            bots=bots,
            verification=verif,
            intervention=interv
        )
    return _global_pipeline

app.dependency_overrides[get_db] = override_get_db
app.dependency_overrides[get_pipeline] = override_get_pipeline

client = TestClient(app)

def test_analyze_endpoint():
    # Configurar mocks
    pipeline = override_get_pipeline()
    pipeline.db = Session(engine) # Refresh session

    
    # Mock Bluesky get_profile e get_posts
    profile = MagicMock()
    profile.did = "did:plc:fake"
    profile.followers_count = 5000 # High engagement
    pipeline.bluesky.get_profile.return_value = profile
    
    from datetime import datetime, UTC
    post = Post(uri="at://did:plc:fake/app.bsky.feed.post/123", cid="cid123", author_did="did:plc:fake", text="Fake news aqui", created_at=datetime.now(UTC))
    pipeline.bluesky.get_posts.return_value = [post]
    
    # Mock Bot Scoring
    assessment = BotAssessment(did="did:plc:fake", score=0.95, features={"followers_count": 5000})
    pipeline.bots.get_assessment.return_value = assessment
    
    # Mock Verification (Adverse verdict)
    verdict = Verdict(claim="fake news", label=VerdictLabel.FALSE, confidence=0.99, rationale="É falso", evidences=[])
    pipeline.verification.verify.return_value = verdict
    
    # Call endpoint
    response = client.post("/v1/analyze", json={"post_url": "https://bsky.app/profile/user/post/123"})
    
    assert response.status_code == 200
    data = response.json()
    assert data["post_uri"] == post.uri
    assert data["action"] == "INTERVENE"
    
    # Verificar se as chamadas de intervenção e rótulo foram feitas
    pipeline.intervention.execute_intervention.assert_called_once()
    pipeline.ozone.emit_label.assert_called_once()

def test_list_decisions_endpoint():
    response = client.get("/v1/decisions")
    assert response.status_code == 200
    assert isinstance(response.json(), list)
    assert len(response.json()) > 0
    
def test_review_decision_endpoint():
    # Obter o id da decisão criada
    decisions = client.get("/v1/decisions").json()
    decision_id = decisions[0]["id"]
    
    response = client.post(f"/v1/decisions/{decision_id}/review?review_action=reverter")
    assert response.status_code == 200
    data = response.json()
    assert data["action"] == "MONITOR"
    assert "REVERTIDO" in data["justification"]
