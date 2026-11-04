"""Explainable content-based recommendations and atomic history persistence."""

from collections import Counter
from decimal import Decimal

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from retailrag.catalog_api import ProductOutput
from retailrag.content_index import ContentIndex
from retailrag.models import CustomerInteraction, Product, Recommendation, RecommendationItem, RecommendationSnapshot
from retailrag.preferences import EVENT_WEIGHTS, get_customer_profile
from retailrag.recommendation_context import resolve_context
from retailrag.recommendation_schemas import RecommendationRequest, RecommendationResponse, RecommendationResultItem


def filter_by_budget(products, minimum=None, maximum=None, min_exclusive=False, max_exclusive=False):
    """Inclusive explicit bounds; rule-extracted 'under/over' bounds can be exclusive."""
    return [p for p in products if
            (minimum is None or (p.price > minimum if min_exclusive else p.price >= minimum)) and
            (maximum is None or (p.price < maximum if max_exclusive else p.price <= maximum))]


def filter_by_availability(products, available_only=True):
    return [p for p in products if p.available or not available_only]


def budget_compatibility(price: Decimal, minimum: Decimal | None, maximum: Decimal | None) -> float:
    if maximum is not None and price > maximum:
        return float(maximum / price) if price else 1.0
    if minimum is not None and price < minimum:
        return float(price / minimum) if minimum else 1.0
    return 1.0


def rank_recommendations(components: dict[str, float], weights: dict[str, float]) -> float:
    """Weights are normalized over active signals by the caller."""
    return float(np.clip(sum(components[key] * weight for key, weight in weights.items()), 0, 1))


def affinity(values: dict[str, float], label: str) -> float:
    return max((score for key, score in values.items() if key.casefold() == label.casefold()), default=0.0)


def popularity_scores(session, products, channel):
    popularity = Counter()
    for event in session.scalars(select(CustomerInteraction)):
        popularity[event.product_id] += EVENT_WEIGHTS[event.event_type] * min(event.quantity, 10) * (2 if event.channel == channel else 1)
    maximum = max(popularity.values(), default=0)
    if maximum:
        return np.array([0.8 * popularity[p.id] / maximum + 0.2 * p.rating / 5 for p in products]), "catalog_popularity_and_rating"
    return np.array([p.rating / 5 for p in products]), "catalog_rating"


def explain(product, components, context, profile, preference_basis, has_text):
    reasons = []
    if has_text:
        reasons.append(f"TF-IDF cosine similarity: {components['text_relevance']:.4f}.")
    if profile and preference_basis == "customer_profile":
        reasons.append(f"Customer affinity {components['customer_preference']:.4f} uses declared preferences and {profile.interaction_count} cross-channel interactions.")
    else:
        reasons.append(f"Cold-start baseline: {preference_basis.replace('_', ' ')}.")
    if context.category:
        reasons.append(f"Matches category {product.category}.")
    elif components["category_match"]:
        reasons.append(f"Category affinity for {product.category}: {components['category_match']:.4f}.")
    if context.brand:
        reasons.append(f"Matches brand {product.brand}.")
    elif components["brand_match"]:
        reasons.append(f"Brand affinity for {product.brand}: {components['brand_match']:.4f}.")
    if context.min_price is not None or context.max_price is not None:
        inside = bool(filter_by_budget([product], context.min_price, context.max_price, context.min_exclusive, context.max_exclusive))
        reasons.append("Meets the effective price bounds." if inside else "Outside preferred price bounds; soft budget is enabled.")
    reasons.append(f"INR {product.price:.2f}; " + (f"in stock ({product.stock_quantity} units)." if product.available else "out of stock; availability filtering is disabled."))
    return " ".join(reasons)


def generate_recommendations(session: Session, request: RecommendationRequest, *, persist: bool = True,
                             candidate_ids: set[str] | None = None, commit: bool = True) -> RecommendationResponse:
    products = list(session.scalars(select(Product).order_by(Product.id)).all())
    profile = get_customer_profile(session, request.customer_id, request.channel) if request.customer_id else None
    index = ContentIndex(products)
    if request.product_id and request.product_id not in index.positions:
        raise LookupError("Product not found")
    context, warnings = resolve_context(request, products, profile)
    query_scores = index.query_scores(context.text_query)
    has_query = bool(context.text_query)
    similarities = query_scores
    anchor = products[index.positions[request.product_id]] if request.product_id else None
    if anchor:
        if context.category is None:
            context.category, context.category_source = anchor.category, "source_product"
        anchor_scores = index.similar_scores(anchor.id)
        similarities = 0.7 * anchor_scores + 0.3 * query_scores if has_query else anchor_scores
    if profile:
        declared = " ".join([*profile.declared_categories, *profile.declared_brands])
        preference_scores = index.preference_scores(profile.product_affinities, declared)
        preference_basis = "customer_profile"
        if not preference_scores.any():
            preference_scores, preference_basis = popularity_scores(session, products, request.channel)
    else:
        preference_scores, preference_basis = popularity_scores(session, products, request.channel)
    has_text = has_query or anchor is not None
    signals = {
        "text_relevance": has_text, "customer_preference": True,
        "category_match": bool(context.category or anchor or (profile and profile.category_affinities)),
        "brand_match": bool(context.brand or anchor or (profile and profile.brand_affinities)),
        "budget_compatibility": context.min_price is not None or context.max_price is not None,
        "availability": True,
    }
    active = {key: value for key, value in request.weights.model_dump().items() if signals[key] and value > 0}
    total_weight = sum(active.values())
    if not total_weight:
        raise ValueError("At least one positive weight must apply to the supplied context")
    active = {key: value / total_weight for key, value in active.items()}
    candidates = filter_by_availability(products, request.available_only)
    if candidate_ids is not None:
        candidates = [product for product in candidates if product.id in candidate_ids]
    if request.strict_budget:
        candidates = filter_by_budget(candidates, context.min_price, context.max_price, context.min_exclusive, context.max_exclusive)
    candidates = [p for p in candidates if
                  (not context.category or p.category.casefold() == context.category.casefold()) and
                  (not context.brand or p.brand.casefold() == context.brand.casefold()) and
                  (not anchor or p.id != anchor.id) and
                  (not request.exclude_purchased or not profile or p.id not in profile.purchased_product_ids)]
    if has_query:
        candidates = [p for p in candidates if query_scores[index.positions[p.id]] > 0]
        if products and not query_scores.any():
            warnings.append("No catalog vocabulary matched the query; unrelated products were not substituted.")
    if anchor:
        candidates = [p for p in candidates if anchor_scores[index.positions[p.id]] > 0]
    if not products:
        warnings.append("The product catalog is empty; import a dataset first.")
    if profile and profile.cold_start:
        warnings.append("This customer has no interaction history; declared preferences and/or the cold-start baseline were used.")
    if not request.strict_budget and signals["budget_compatibility"]:
        warnings.append("Budget is a soft preference; products outside its bounds may be returned.")
    if not request.available_only:
        warnings.append("Availability filtering is disabled; out-of-stock products may be returned.")
    scored = []
    for product in candidates:
        position = index.positions[product.id]
        components = {
            "text_relevance": float(similarities[position]),
            "customer_preference": float(preference_scores[position]),
            "category_match": float(product.category.casefold() == (context.category or (anchor.category if anchor else "")).casefold()) if context.category or anchor else affinity(profile.category_affinities, product.category) if profile else 0,
            "brand_match": float(product.brand.casefold() == (context.brand or (anchor.brand if anchor else "")).casefold()) if context.brand or anchor else affinity(profile.brand_affinities, product.brand) if profile else 0,
            "budget_compatibility": budget_compatibility(product.price, context.min_price, context.max_price),
            "availability": float(product.available),
        }
        score = rank_recommendations(components, active)
        scored.append((score, product, components))
    scored.sort(key=lambda row: (-row[0], -row[2]["text_relevance"], -row[1].rating, row[1].price, row[1].id))
    items = [RecommendationResultItem(
        rank=rank, product=ProductOutput.model_validate(product), similarity_score=round(components["text_relevance"], 8),
        relevance_score=round(score, 8), components={key: round(value, 8) for key, value in components.items()},
        explanation=explain(product, components, context, profile, preference_basis, has_text),
    ) for rank, (score, product, components) in enumerate(scored[:request.limit], start=1)]
    response = RecommendationResponse(
        mode=request.mode, query=request.query, customer_id=request.customer_id, channel=request.channel,
        message="Deterministic TF-IDF recommendations; no LLM was called." if items else "No products match the requested constraints. No filters were relaxed.",
        warnings=warnings, context=context, profile=profile, preference_basis=preference_basis,
        active_weights=active, catalog_size=len(products), candidate_count=len(candidates), items=items,
    )
    if persist:
        save_recommendation(session, request, response, commit=commit, candidate_ids=candidate_ids)
    return response


def save_recommendation(session: Session, request: RecommendationRequest, response: RecommendationResponse, *, commit: bool = True,
                        candidate_ids: set[str] | None = None) -> None:
    record = Recommendation(customer_id=request.customer_id, query=request.query, channel=request.channel, mode=request.mode)
    record.items = [RecommendationItem(
        product_id=item.product.id, rank=item.rank, score=item.relevance_score,
        price_snapshot=item.product.price, explanation=item.explanation,
    ) for item in response.items]
    try:
        session.add(record)
        session.flush()
        response.id, response.created_at = record.id, record.created_at
        saved_request = request.model_dump(mode="json")
        if candidate_ids is not None:
            saved_request["candidate_product_ids"] = sorted(candidate_ids)
        session.add(RecommendationSnapshot(recommendation_id=record.id, request=saved_request, payload=response.model_dump(mode="json")))
        if commit:
            session.commit()
        else:
            session.flush()
    except Exception:
        session.rollback()
        raise
