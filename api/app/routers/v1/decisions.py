import re

from fastapi import APIRouter, Depends, HTTPException, Query

# Precisamos injetar as dependências reais. Para os endpoints, 
# podemos instanciar sob demanda ou usar um dependency provider.
# Neste exemplo usaremos um provider simples se necessário, ou mockamos a injeção via Request.
# Idealmente usar FastAPI Depends para obter db session.
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.clients.bluesky_client import BlueskyClient
from app.clients.ozone_client import OzoneClient
from app.core.config import get_settings
from app.db.orm.decisions import DecisionLog
from app.domain.entities import Post
from app.models.llm.litellm_model import LiteLLMModel
from app.repositories.interventions import InterventionRepository
from app.schemas.decisions import AnalyzeRequest, DecisionLogOut
from app.services.bot_scoring import BotScoringService
from app.services.intervention import InterventionService
from app.services.pipeline import PipelineService
from app.services.verification import VerificationService

router = APIRouter(prefix="/v1", tags=["decisions"])

def get_db():
    settings = get_settings()
    engine = create_engine(settings.database_url)
    with Session(engine) as session:
        yield session

def get_pipeline(db: Session = Depends(get_db)):
    settings = get_settings()
    bluesky = BlueskyClient(settings)
    ozone = OzoneClient(bluesky.get_auth_client())
    bots = BotScoringService(db.get_bind(), bluesky)
    llm = LiteLLMModel(settings)
    verification = VerificationService.from_settings(llm, settings=settings, engine=db.get_bind())
    intervention = InterventionService(InterventionRepository(db.get_bind()), bluesky, llm)
    
    return PipelineService(
        settings=settings,
        db_session=db,
        bluesky=bluesky,
        ozone=ozone,
        bots=bots,
        verification=verification,
        intervention=intervention
    )


@router.get("/decisions", response_model=list[DecisionLogOut])
def list_decisions(
    action: str | None = None,
    verdict: str | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    query = db.query(DecisionLog)
    if action:
        query = query.filter(DecisionLog.action == action)
    if verdict:
        query = query.filter(DecisionLog.verdict == verdict)
        
    return query.order_by(DecisionLog.created_at.desc()).offset(skip).limit(limit).all()


@router.get("/decisions/{decision_id}", response_model=DecisionLogOut)
def get_decision(decision_id: int, db: Session = Depends(get_db)):
    decision = db.query(DecisionLog).filter(DecisionLog.id == decision_id).first()
    if not decision:
        raise HTTPException(status_code=404, detail="Decisão não encontrada")
    return decision


@router.post("/analyze", response_model=DecisionLogOut)
async def analyze_post(req: AnalyzeRequest, pipeline: PipelineService = Depends(get_pipeline)):
    # Converter a URL pública (ex: https://bsky.app/profile/user/post/rkey) em URI do ATProto
    # did = resolver o handle, depois uri = at://did/app.bsky.feed.post/rkey
    # Como simplificação, esperamos que a pipeline.bluesky consiga buscar isso.
    # Mas vamos tentar extrair handle e rkey.
    
    match = re.search(r"profile/([^/]+)/post/([^/]+)", req.post_url)
    if not match:
        raise HTTPException(status_code=400, detail="Formato de URL inválido")
    
    handle = match.group(1)
    rkey = match.group(2)
    
    try:
        profile = await pipeline.bluesky.get_profile(handle)
        did = profile.did
        uri = f"at://{did}/app.bsky.feed.post/{rkey}"
        
        # Buscar o post de verdade usando client bluesky
        posts = await pipeline.bluesky.get_posts([uri])
        if not posts:
            raise HTTPException(status_code=404, detail="Post não encontrado no bsky")
            
        post = posts[0]
        decision = await pipeline.analyze(post)
        return decision
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{decision_id}/review", response_model=DecisionLogOut)
async def review_decision(decision_id: int, review_action: str = Query(..., description="Ação: confirmar, reverter"), pipeline: PipelineService = Depends(get_pipeline)):
    decision = pipeline.db.query(DecisionLog).filter(DecisionLog.id == decision_id).first()
    if not decision:
        raise HTTPException(status_code=404, detail="Decisão não encontrada")
        
    if review_action == "reverter" and decision.action == "INTERVENE":
        try:
            # Negar rótulo (Issue #16)
            from datetime import UTC, datetime
            post = Post(uri=decision.post_uri, cid="", author_did=decision.post_snapshot.get("author_did", ""), text=decision.post_snapshot.get("text", ""), created_at=datetime.now(UTC))
            await pipeline.ozone.emit_label(post, label_val="possivel-desinformacao", action="negate")
            decision.action = "MONITOR"
            decision.justification += " [REVERTIDO MANUAMENTE]"
            pipeline.db.commit()
            pipeline.db.refresh(decision)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
            
    return decision
