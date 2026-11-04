"""Atomic, explicitly synthetic shopping journeys with cross-channel continuity."""

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from retailrag.catalog_api import InteractionOutput, get_session
from retailrag.data_schemas import Channel, EventType, Identifier, InputRow, Money
from retailrag.models import Customer, CustomerInteraction, OmnichannelSimulation, Product, utc_now
from retailrag.preferences import get_customer_profile
from retailrag.recommendation_schemas import RecommendationRequest
from retailrag.recommendations import generate_recommendations
from retailrag.tool_registry import result_digest

CHANNELS = ("ecommerce", "mobile", "store")
router = APIRouter(prefix="/omnichannel", tags=["Omnichannel"])


class SimulationEvent(InputRow):
    product_id: Identifier
    event_type: EventType
    channel: Channel
    quantity: int = Field(default=1, ge=1, le=100)
    occurred_at: datetime | None = None

    @field_validator("occurred_at")
    @classmethod
    def timezone_required(cls, value):
        if value is not None and value.tzinfo is None:
            raise ValueError("Event timestamps must include a timezone")
        return value.astimezone(timezone.utc) if value else None


class SimulationRequest(InputRow):
    customer_id: Identifier
    events: list[SimulationEvent] = Field(min_length=1, max_length=100)
    query: str = Field(default="", max_length=2000)
    max_price: Money | None = None
    category: str | None = Field(default=None, min_length=1, max_length=100)
    brand: str | None = Field(default=None, min_length=1, max_length=100)
    available_only: bool = True
    limit: int = Field(default=3, ge=1, le=20)
    idempotency_key: str = Field(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")


def simulate(engine, request):
    arguments = request.model_dump(mode="json")
    digest = result_digest({key: value for key, value in arguments.items() if key != "idempotency_key"})
    simulation_id = uuid.uuid4().hex
    try:
        with Session(engine) as session, session.begin():
            previous = session.scalar(select(OmnichannelSimulation).where(OmnichannelSimulation.idempotency_key == request.idempotency_key))
            if previous:
                if previous.request_sha256 != digest:
                    raise HTTPException(409, "Simulation key belongs to a different request")
                return {**previous.result, "replayed": True}, False
            if session.get(Customer, request.customer_id) is None:
                raise HTTPException(404, "Customer not found")
            if any(session.get(Product, event.product_id) is None for event in request.events):
                raise HTTPException(404, "One or more simulation products were not found")
            before = get_customer_profile(session, request.customer_id).model_dump(mode="json")
            record = OmnichannelSimulation(id=simulation_id, customer_id=request.customer_id,
                                            idempotency_key=request.idempotency_key, request_sha256=digest, request=arguments, result={})
            session.add(record)
            session.flush()
            base_time = utc_now()
            events = []
            for index, event in enumerate(request.events):
                row = CustomerInteraction(id=f"sim_{simulation_id}_{index}", customer_id=request.customer_id,
                                          product_id=event.product_id, event_type=event.event_type, channel=event.channel,
                                          quantity=event.quantity, occurred_at=event.occurred_at or base_time + timedelta(seconds=index),
                                          source="synthetic_omnichannel")
                session.add(row)
                events.append(row)
            session.flush()
            profiles, recommendations = {}, {}
            for channel in CHANNELS:
                profiles[channel] = get_customer_profile(session, request.customer_id, channel).model_dump(mode="json")
                recommendation = generate_recommendations(session, RecommendationRequest(
                    mode="context_aware" if request.query else "personalized", query=request.query,
                    customer_id=request.customer_id, channel=channel, max_price=request.max_price,
                    category=request.category, brand=request.brand, available_only=request.available_only, limit=request.limit,
                ), commit=False)
                recommendations[channel] = recommendation.model_dump(mode="json")
            result = {"simulation_id": simulation_id, "customer_id": request.customer_id,
                      "source": "synthetic_omnichannel", "created_at": record.created_at.isoformat(), "replayed": False,
                      "events": [InteractionOutput.model_validate(event).model_dump(mode="json") for event in events],
                      "profile_before": before, "profiles_after": profiles, "recommendations": recommendations,
                      "message": "Synthetic shopping history only; no external retail integration, payment, or inventory change occurred."}
            record.result = result
        return result, True
    except IntegrityError:
        with Session(engine) as session:
            previous = session.scalar(select(OmnichannelSimulation).where(OmnichannelSimulation.idempotency_key == request.idempotency_key))
            if previous and previous.request_sha256 == digest:
                return {**previous.result, "replayed": True}, False
            if previous:
                raise HTTPException(409, "Simulation key belongs to a different request") from None
        raise


@router.post("/simulations")
def create_simulation(values: SimulationRequest, session=Depends(get_session)):
    from fastapi.responses import JSONResponse
    try:
        result, created = simulate(session.get_bind(), values)
    except HTTPException:
        raise
    except ValueError:
        raise HTTPException(422, "Simulation query or constraints failed validation") from None
    except Exception:
        raise HTTPException(503, "Simulation failed; its events and recommendations were rolled back") from None
    return JSONResponse(status_code=201 if created else 200, content=result)


@router.get("/simulations")
def simulations(customer_id: str | None = None, limit: int = Query(default=20, ge=1, le=100),
                offset: int = Query(default=0, ge=0), session=Depends(get_session)):
    statement = select(OmnichannelSimulation)
    if customer_id is not None:
        statement = statement.where(OmnichannelSimulation.customer_id == customer_id)
    total = session.scalar(select(func.count()).select_from(statement.subquery()))
    rows = session.scalars(statement.order_by(OmnichannelSimulation.created_at.desc(), OmnichannelSimulation.id).offset(offset).limit(limit)).all()
    return {"total": total, "limit": limit, "offset": offset,
            "items": [{"simulation_id": row.id, "customer_id": row.customer_id, "created_at": row.created_at,
                       "event_count": len(row.result["events"]),
                       "recommendation_ids": {channel: rec["id"] for channel, rec in row.result["recommendations"].items()}} for row in rows]}


@router.get("/simulations/{simulation_id}")
def details(simulation_id: str, session=Depends(get_session)):
    row = session.get(OmnichannelSimulation, simulation_id)
    if row is None:
        raise HTTPException(404, "Simulation not found")
    return row.result


@router.get("/customers/{customer_id}/context")
def continuity(customer_id: str, session=Depends(get_session)):
    if session.get(Customer, customer_id) is None:
        raise HTTPException(404, "Customer not found")
    return {"customer_id": customer_id, "shared_history": True,
            "profiles": {channel: get_customer_profile(session, customer_id, channel).model_dump(mode="json") for channel in CHANNELS}}
