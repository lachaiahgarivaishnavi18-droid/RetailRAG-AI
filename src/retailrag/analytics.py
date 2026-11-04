"""Database-derived analytics. Synthetic event counts are not sales attribution."""

from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from retailrag.catalog_api import get_session
from retailrag.models import AgentExecution, Customer, CustomerInteraction, OmnichannelSimulation, Product, Recommendation, ToolInvocation, WorkflowRun, utc_now
from retailrag.omnichannel import CHANNELS
from retailrag.analytics_schemas import ChannelAnalytics, OverviewAnalytics, RecommendationAnalytics

router = APIRouter(prefix="/analytics", tags=["Analytics"])


def bounds(date_from, date_to):
    if date_from and date_to and date_from > date_to:
        raise HTTPException(422, "date_from must be no later than date_to")
    start = datetime.combine(date_from, time.min, tzinfo=timezone.utc) if date_from else None
    end = datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=timezone.utc) if date_to and date_to < date.max else None
    return start, end


def filtered(statement, column, start, end):
    if start:
        statement = statement.where(column >= start)
    if end:
        statement = statement.where(column < end)
    return statement


def load_data(session, date_from=None, date_to=None):
    start, end = bounds(date_from, date_to)
    events = list(session.scalars(filtered(select(CustomerInteraction), CustomerInteraction.occurred_at, start, end)))
    recs = list(session.scalars(filtered(select(Recommendation).options(selectinload(Recommendation.items)), Recommendation.created_at, start, end)))
    products = {product.id: product for product in session.scalars(select(Product))}
    return start, end, events, recs, products


def period(date_from, date_to):
    return {"date_from": date_from.isoformat() if date_from else None, "date_to": date_to.isoformat() if date_to else None, "timezone": "UTC"}


def count_table(session, model, column, start, end):
    return session.scalar(filtered(select(func.count()).select_from(model), column, start, end))


def ranked(counter, label, limit=10):
    return [{label: key, "count": count} for key, count in sorted(counter.items(), key=lambda value: (-value[1], value[0]))[:limit]]


@router.get("/overview", response_model=OverviewAnalytics)
def overview(date_from: date | None = None, date_to: date | None = None, session=Depends(get_session)):
    start, end, events, recs, products = load_data(session, date_from, date_to)
    activity = Counter(event.product_id for event in events)
    categories = Counter(products[event.product_id].category for event in events if event.product_id in products)
    return {"generated_at": utc_now(), "period": period(date_from, date_to),
            "totals": {"products": len(products), "customers": session.scalar(select(func.count()).select_from(Customer)),
                       "interactions": len(events), "recommendations": len(recs),
                       "agent_executions": count_table(session, AgentExecution, AgentExecution.started_at, start, end),
                       "tool_invocations": count_table(session, ToolInvocation, ToolInvocation.started_at, start, end),
                       "simulations": count_table(session, OmnichannelSimulation, OmnichannelSimulation.created_at, start, end)},
            "inventory": {"available": sum(product.available for product in products.values()), "unavailable": sum(not product.available for product in products.values())},
            "popular_products": [{"product_id": row["product_id"], "name": products[row["product_id"]].name,
                                  "category": products[row["product_id"]].category, "interactions": row["count"]}
                                 for row in ranked(activity, "product_id") if row["product_id"] in products],
            "popular_categories": ranked(categories, "category"),
            "channel_activity": [{"channel": channel, "interactions": sum(event.channel == channel for event in events)} for channel in CHANNELS],
            "provenance": ranked(Counter(event.source for event in events), "source"),
            "recent_recommendations": [{"id": rec.id, "customer_id": rec.customer_id, "query": rec.query, "channel": rec.channel,
                                        "mode": rec.mode, "created_at": rec.created_at, "items": len(rec.items)}
                                       for rec in sorted(recs, key=lambda rec: (rec.created_at, rec.id), reverse=True)[:5]]}


@router.get("/recommendations", response_model=RecommendationAnalytics)
def recommendations(date_from: date | None = None, date_to: date | None = None, session=Depends(get_session)):
    _, _, events, recs, products = load_data(session, date_from, date_to)
    items = [item for rec in recs for item in rec.items]
    daily = defaultdict(lambda: {"runs": 0, "items": 0})
    for rec in recs:
        key = rec.created_at.date().isoformat()
        daily[key]["runs"] += 1
        daily[key]["items"] += len(rec.items)
    scores = defaultdict(list)
    for item in items:
        scores[item.product_id].append(item.score)
    performance = [{"product_id": key, "name": products[key].name if key in products else key,
                    "recommendation_count": len(values), "average_score": sum(values) / len(values)} for key, values in scores.items()]
    performance.sort(key=lambda row: (-row["recommendation_count"], row["product_id"]))
    return {"period": period(date_from, date_to), "total_runs": len(recs), "total_items": len(items),
            "average_items_per_run": len(items) / len(recs) if recs else 0,
            "average_score": sum(item.score for item in items) / len(items) if items else 0,
            "daily_trend": [{"date": key, **daily[key]} for key in sorted(daily)],
            "mode_distribution": ranked(Counter(rec.mode for rec in recs), "mode"),
            "category_distribution": ranked(Counter(products[item.product_id].category for item in items if item.product_id in products), "category"),
            "product_performance": performance[:20], "event_mix": ranked(Counter(event.event_type for event in events), "event_type"),
            "active_customers": len({event.customer_id for event in events}),
            "category_basis": "current_catalog_taxonomy", "measurement_notes": "Synthetic event and recommendation counts only. Recommendation clicks/exposures are not instrumented; CTR, attributed conversion, and revenue are not measured."}


@router.get("/channels", response_model=ChannelAnalytics)
def channels(date_from: date | None = None, date_to: date | None = None, session=Depends(get_session)):
    start, end, events, recs, _ = load_data(session, date_from, date_to)
    daily, customers = Counter(), defaultdict(set)
    for event in events:
        daily[(event.occurred_at.date().isoformat(), event.channel)] += 1
        customers[event.customer_id].add(event.channel)
    workflows = list(session.scalars(filtered(select(WorkflowRun), WorkflowRun.started_at, start, end)))
    result = []
    for channel in CHANNELS:
        activity = [event for event in events if event.channel == channel]
        selected = [rec for rec in recs if rec.channel == channel]
        scores = [item.score for rec in selected for item in rec.items]
        result.append({"channel": channel, "interactions": len(activity), "active_customers": len({event.customer_id for event in activity}),
                       "purchase_events": sum(event.event_type == "purchase" for event in activity),
                       "units_in_purchase_events": sum(event.quantity for event in activity if event.event_type == "purchase"),
                       "recommendation_runs": len(selected), "recommendation_items": len(scores),
                       "average_score": sum(scores) / len(scores) if scores else 0,
                       "workflow_runs": sum(row.request.get("channel") == channel for row in workflows),
                       "synthetic_simulation_events": sum(event.source == "synthetic_omnichannel" for event in activity)})
    return {"period": period(date_from, date_to), "channels": result,
            "cross_channel_customers": sum(len(values) > 1 for values in customers.values()),
            "daily_activity": [{"date": key[0], "channel": key[1], "interactions": value} for key, value in sorted(daily.items())],
            "event_mix": [{"channel": channel, "event_type": event_type, "count": sum(event.channel == channel and event.event_type == event_type for event in events)}
                          for channel in CHANNELS for event_type in ("view", "wishlist", "cart", "purchase")],
            "measurement_notes": "All channels are synthetic simulations; purchase-event quantities are not verified orders or revenue."}
