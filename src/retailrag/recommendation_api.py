"""Recommendation generation, evidence snapshots, and customer preference routes."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from retailrag.catalog_api import ProductOutput, get_session
from retailrag.data_schemas import Channel
from retailrag.models import Recommendation, RecommendationItem, RecommendationSnapshot
from retailrag.preferences import get_customer_profile
from retailrag.recommendation_schemas import CustomerProfile, RecommendationMode, RecommendationRequest, RecommendationResponse
from retailrag.recommendations import generate_recommendations

router = APIRouter()


@router.get("/customers/{customer_id}/preferences", response_model=CustomerProfile, tags=["Customers"])
def preferences(customer_id: str, channel: Channel | None = None, session: Session = Depends(get_session)):
    try:
        return get_customer_profile(session, customer_id, channel)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from None


@router.post("/recommendations", response_model=RecommendationResponse, status_code=201, tags=["Recommendations"])
def recommend(request: RecommendationRequest, session: Session = Depends(get_session)):
    try:
        return generate_recommendations(session, request)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from None
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None


@router.get("/recommendations", tags=["Recommendations"])
def history(
    customer_id: str | None = Query(default=None, max_length=64), channel: Channel | None = None,
    mode: RecommendationMode | None = None,
    limit: int = Query(default=25, ge=1, le=100), offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
):
    statement = select(Recommendation)
    if customer_id is not None:
        statement = statement.where(Recommendation.customer_id == customer_id)
    if channel is not None:
        statement = statement.where(Recommendation.channel == channel)
    if mode is not None:
        statement = statement.where(Recommendation.mode == mode)
    total = session.scalar(select(func.count()).select_from(statement.subquery()))
    records = session.scalars(statement.options(selectinload(Recommendation.items)).order_by(Recommendation.id.desc()).offset(offset).limit(limit)).all()
    return {
        "total": total, "limit": limit, "offset": offset,
        "items": [{"id": record.id, "customer_id": record.customer_id, "query": record.query, "mode": record.mode,
                   "channel": record.channel, "created_at": record.created_at, "item_count": len(record.items)} for record in records],
    }


@router.get("/recommendations/{recommendation_id}", tags=["Recommendations"])
def details(recommendation_id: int, session: Session = Depends(get_session)):
    record = session.get(Recommendation, recommendation_id)
    if record is None:
        raise HTTPException(404, "Recommendation not found")
    snapshot = session.get(RecommendationSnapshot, recommendation_id)
    if snapshot:
        return snapshot.payload
    # Preserve access to older records without inventing missing evidence.
    rows = session.scalars(select(RecommendationItem).where(RecommendationItem.recommendation_id == record.id).order_by(RecommendationItem.rank)).all()
    return {
        "id": record.id, "customer_id": record.customer_id, "query": record.query, "mode": record.mode,
        "channel": record.channel, "created_at": record.created_at, "engine": "legacy_unknown", "llm_used": None,
        "message": "Legacy record without a complete snapshot. Product details below reflect the current catalog; price_snapshot is historical.",
        "items": [{"rank": item.rank, "product": ProductOutput.model_validate(item.product), "price_snapshot": str(item.price_snapshot),
                   "relevance_score": item.score, "explanation": item.explanation} for item in rows],
    }
