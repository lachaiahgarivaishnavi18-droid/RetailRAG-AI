"""Reusable cross-channel behavioral profiling, without invented purchase prices."""

from collections import Counter
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from retailrag.data_schemas import Channel
from retailrag.models import Customer, CustomerInteraction
from retailrag.recommendation_schemas import CustomerProfile

EVENT_WEIGHTS = {"view": 1.0, "wishlist": 3.0, "cart": 4.0, "purchase": 6.0}


def normalize_affinities(values: dict[str, float]) -> dict[str, float]:
    maximum = max(values.values(), default=0)
    return {key: round(value / maximum, 8) for key, value in sorted(values.items())} if maximum else {}


def get_customer_profile(session: Session, customer_id: str, channel: Channel | None = None) -> CustomerProfile:
    customer = session.get(Customer, customer_id)
    if customer is None:
        raise LookupError("Customer not found")
    events = session.scalars(
        select(CustomerInteraction).options(joinedload(CustomerInteraction.product))
        .where(CustomerInteraction.customer_id == customer_id)
        .order_by(CustomerInteraction.occurred_at, CustomerInteraction.id)
    ).all()
    categories, brands, products = Counter(), Counter(), Counter()
    for category in customer.preferred_categories:
        categories[category] += 2.0
    for brand in customer.preferred_brands:
        brands[brand] += 2.0
    purchase_prices = []
    for event in events:
        weight = EVENT_WEIGHTS[event.event_type] * min(event.quantity, 10)
        if event.channel == channel:
            weight *= 2.0
        categories[event.product.category] += weight
        brands[event.product.brand] += weight
        products[event.product_id] += weight
        if event.event_type == "purchase":
            purchase_prices.append(event.product.price)
    purchase_prices.sort()
    size = len(purchase_prices)
    median = None if not size else (purchase_prices[(size - 1) // 2] + purchase_prices[size // 2]) / Decimal("2")

    def ids(event_type):
        return sorted({event.product_id for event in events if event.event_type == event_type})

    return CustomerProfile(
        customer_id=customer.id, name=customer.name, channel=channel, cold_start=not events,
        declared_categories=customer.preferred_categories, declared_brands=customer.preferred_brands,
        category_affinities=normalize_affinities(categories), brand_affinities=normalize_affinities(brands),
        product_affinities=normalize_affinities(products), budget_min=customer.budget_min, budget_max=customer.budget_max,
        observed_purchase_median_price=median, event_counts=dict(Counter(e.event_type for e in events)),
        channel_counts=dict(Counter(e.channel for e in events)), viewed_product_ids=ids("view"),
        purchased_product_ids=ids("purchase"), wishlist_product_ids=ids("wishlist"),
        interaction_count=len(events), source=customer.source,
    )
