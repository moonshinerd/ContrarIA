"""Endpoints REST para o log de decisões e análise sob demanda (#17)."""

import re
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.clients.bluesky_client import BlueskyClient
from app.clients.ozone_client import OzoneClient
from app.core.config import get_settings
from app.db.orm.decisions import DecisionLog, DecisionReview
from app.domain.entities import Post
from app.models.llm.litellm_model import LiteLLMModel
from app.repositories.interventions import InterventionRepository
from app.schemas.decisions import AnalyzeRequest, DecisionLogOut, DecisionReviewOut
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


def get_pipeline(db: Session = Depends(get_db)):  # noqa: B008
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
        intervention=intervention,
    )


@router.get("/decisions", response_model=list[DecisionLogOut])
def list_decisions(
    action: str | None = None,
    verdict: str | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),  # noqa: B008
):
    query = db.query(DecisionLog)
    if action:
        query = query.filter(DecisionLog.action == action)
    if verdict:
        query = query.filter(DecisionLog.verdict == verdict)

    return query.order_by(DecisionLog.created_at.desc()).offset(skip).limit(limit).all()


@router.get("/decisions/{decision_id}", response_model=DecisionLogOut)
def get_decision(
    decision_id: int,
    db: Session = Depends(get_db),  # noqa: B008
):
    decision = db.query(DecisionLog).filter(DecisionLog.id == decision_id).first()
    if not decision:
        raise HTTPException(status_code=404, detail="Decisão não encontrada")
    return decision


@router.post("/analyze", response_model=DecisionLogOut)
async def analyze_post(
    req: AnalyzeRequest,
    pipeline: PipelineService = Depends(get_pipeline),  # noqa: B008
):
    """Roda o pipeline sob demanda para uma URL de post do Bluesky.

    Por padrão opera em dry-run (não publica). Ideal para demo do showcase.
    """
    match = re.search(r"profile/([^/]+)/post/([^/]+)", req.post_url)
    if not match:
        raise HTTPException(status_code=400, detail="Formato de URL inválido")

    handle = match.group(1)
    rkey = match.group(2)

    try:
        profile = await pipeline.bluesky.get_profile(handle)
        uri = f"at://{profile.did}/app.bsky.feed.post/{rkey}"

        posts = await pipeline.bluesky.get_posts([uri])
        if not posts:
            raise HTTPException(status_code=404, detail="Post não encontrado no bsky")

        decision = await pipeline.analyze(posts[0])
        return decision
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/decisions/{decision_id}/review", response_model=DecisionReviewOut)
async def review_decision(
    decision_id: int,
    review_action: str = Query(..., description="Ação: confirmar | reverter"),  # noqa: B008
    pipeline: PipelineService = Depends(get_pipeline),  # noqa: B008
):
    """Registra uma revisão e, quando aplicável, nega o rótulo Ozone.

    A decisão original nunca é atualizada: a revisão é um evento separado,
    preservando o requisito de auditoria insert-only.
    """
    decision = pipeline.db.query(DecisionLog).filter(DecisionLog.id == decision_id).first()
    if not decision:
        raise HTTPException(status_code=404, detail="Decisão não encontrada")

    if review_action not in {"confirmar", "reverter"}:
        raise HTTPException(status_code=422, detail="review_action deve ser confirmar ou reverter")

    justification = "Revisão humana confirmou a decisão."
    if review_action == "reverter" and decision.action == "INTERVENE":
        try:
            cid = decision.post_snapshot.get("cid")
            if not cid:
                raise HTTPException(
                    status_code=409,
                    detail="Decisão legada sem CID; não é seguro negar o rótulo.",
                )
            post = Post(
                uri=decision.post_uri,
                cid=cid,
                author_did=decision.post_snapshot.get("author_did", ""),
                text=decision.post_snapshot.get("text", ""),
                created_at=datetime.now(UTC),
            )
            await pipeline.ozone.emit_label(
                post, label_val="possivel-desinformacao", action="negate"
            )
            justification = "Revisão humana reverteu a decisão e negou o rótulo Ozone."
        except Exception as e:
            if isinstance(e, HTTPException):
                raise
            raise HTTPException(status_code=500, detail=str(e)) from e

    review = DecisionReview(
        decision_id=decision.id,
        action=review_action,
        justification=justification,
    )
    pipeline.db.add(review)
    pipeline.db.commit()
    pipeline.db.refresh(review)
    return review
