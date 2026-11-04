"""Conservative rule-based context extraction; no LLM or agent is called."""

import re
from decimal import Decimal

from retailrag.data_schemas import clean_text
from retailrag.models import Product
from retailrag.recommendation_schemas import CustomerProfile, RecommendationRequest, ResolvedContext

NUMBER = r"(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{1,2})?(?:\s*k\b)?(?![\w.]|,\d)"
AMOUNT = r"(?:(?:₹|inr\b|rs\.?)\s*)?" + NUMBER + r"(?:\s*(?:inr\b|rs\.?))?"


def amount(value: str) -> Decimal:
    text = re.sub(r"(?:inr|rs\.?|₹|,|\s)", "", value, flags=re.I)
    result = Decimal(text.rstrip("kK")) * (1000 if text.lower().endswith("k") else 1)
    if result > Decimal("9999999999.99"):
        raise ValueError("Query budget exceeds the supported INR amount")
    return result.quantize(Decimal("0.01"))


def parse_budget(query: str) -> tuple[dict, str]:
    values = {}

    def add_bound(key, value, exclusive=False):
        flag = "max_exclusive" if key == "max_price" else "min_exclusive"
        tighter = key not in values or (value < values[key] if key == "max_price" else value > values[key])
        if tighter:
            values[key], values[flag] = value, exclusive
        elif value == values[key]:
            values[flag] = values[flag] or exclusive

    def between(match):
        add_bound("min_price", amount(match[1]))
        add_bound("max_price", amount(match[2]))
        return " "

    remainder = re.sub(r"\bbetween\s+(" + AMOUNT + r")\s+(?:and|to)\s+(" + AMOUNT + r")", between, query, flags=re.I)
    for key, pattern, exclusive_words in [
        ("max_price", r"\b(under|below|less than|up to|at most|maximum(?: of)?|budget(?: of)?)\s*(" + AMOUNT + r")", {"under", "below", "less than"}),
        ("min_price", r"\b(over|above|more than|at least|minimum(?: of)?)\s*(" + AMOUNT + r")", {"over", "above", "more than"}),
    ]:
        def bound(match):
            add_bound(key, amount(match[2]), match[1].lower() in exclusive_words)
            return " "
        remainder = re.sub(pattern, bound, remainder, flags=re.I)
    return values, clean_text(remainder)


def catalog_label(query: str, labels: set[str], kind: str, warnings: list[str]) -> str | None:
    matches = sorted(label for label in labels if re.search(r"(?<!\w)" + re.escape(label) + r"(?!\w)", query, flags=re.I))
    if len(matches) > 1:
        warnings.append(f"Multiple {kind} names detected; no automatic {kind} filter was applied. Use the explicit field to choose one.")
        return None
    return matches[0] if matches else None


def resolve_context(request: RecommendationRequest, products: list[Product], profile: CustomerProfile | None):
    warnings = []
    if re.search(r"\b(?:not|except|exclude|without)\b", request.query, flags=re.I):
        raise ValueError("Negative query constraints are not supported in Phase 3; use the explicit filters or rephrase positively")
    if re.search(r"[$€£]|\b(?:usd|eur|gbp|dollars|euros|pounds)\b", request.query, flags=re.I):
        raise ValueError("Phase 3 supports INR budgets only")
    parsed, text_query = parse_budget(request.query)
    if request.mode == "budget" and request.min_price is None and request.max_price is None and not parsed:
        raise ValueError("No budget was recognized; supply min_price or max_price explicitly")
    category, brand = request.category, request.brand
    if request.mode == "context_aware":
        category = category or catalog_label(request.query, {p.category for p in products}, "category", warnings)
        brand = brand or catalog_label(request.query, {p.brand for p in products}, "brand", warnings)
    has_requested_budget = request.min_price is not None or request.max_price is not None or bool(parsed)
    bounds, sources = {}, {}
    for key, profile_value in (("min_price", profile.budget_min if profile else None), ("max_price", profile.budget_max if profile else None)):
        explicit = getattr(request, key)
        if explicit is not None:
            bounds[key], sources[key] = explicit, "explicit"
        elif key in parsed:
            bounds[key], sources[key] = parsed[key], "query"
        elif not has_requested_budget and profile_value is not None:
            bounds[key], sources[key] = profile_value, "declared_customer_budget"
        else:
            bounds[key] = None
    if bounds["min_price"] is not None and bounds["max_price"] is not None and bounds["min_price"] > bounds["max_price"]:
        raise ValueError("Effective minimum price exceeds maximum price")
    context = ResolvedContext(
        category=category, brand=brand, **bounds, budget_sources=sources,
        category_source="explicit" if request.category else "query" if category else None,
        brand_source="explicit" if request.brand else "query" if brand else None,
        min_exclusive=bool(parsed.get("min_exclusive")) and sources.get("min_price") == "query",
        max_exclusive=bool(parsed.get("max_exclusive")) and sources.get("max_price") == "query",
        strict_budget=request.strict_budget, available_only=request.available_only,
        exclude_purchased=request.exclude_purchased, text_query=text_query,
    )
    return context, warnings
