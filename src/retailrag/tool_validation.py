"""Independent product/history/document postconditions for public tool results."""

import math

from sqlalchemy import select

from retailrag.catalog_api import InteractionOutput, ProductOutput
from retailrag.models import CustomerInteraction, Product, Recommendation
from retailrag.preferences import get_customer_profile
from retailrag.recommendation_context import resolve_context
from retailrag.recommendation_schemas import RecommendationRequest
from retailrag.rag import validate_grounding
from retailrag.rag_documents import fingerprint
from retailrag.rag_generation import render_grounded_answer
from retailrag.rag_schemas import RagResponse
from retailrag.recommendation_schemas import RecommendationResponse
from retailrag.recommendations import explain, filter_by_budget


class ToolGroundingError(ValueError):
    pass


def product_snapshots(value):
    if isinstance(value, dict):
        if {"id", "name", "price", "stock_quantity", "features", "attributes", "source"} <= value.keys():
            yield ProductOutput.model_validate(value)
        else:
            for child in value.values():
                yield from product_snapshots(child)
    elif isinstance(value, list):
        for child in value:
            yield from product_snapshots(child)


def validate_tool_result(session, store, name, values, result):
    for product in product_snapshots(result):
        current = session.get(Product, product.id)
        if current is None or fingerprint(ProductOutput.model_validate(current)) != fingerprint(product):
            raise ToolGroundingError("Tool returned non-catalog product facts")
    if name == "check_product_availability":
        expected_ids = list(dict.fromkeys(values.product_ids))
        if [item["product_id"] for item in result["items"]] != expected_ids:
            raise ToolGroundingError("Availability IDs do not match request")
        for item in result["items"]:
            product = session.get(Product, item["product_id"])
            if product is None or item["stock_quantity"] != product.stock_quantity or item["available"] != product.available:
                raise ToolGroundingError("Availability facts do not match database")
        if result["unavailable_product_ids"] != [item["product_id"] for item in result["items"] if not item["available"]]:
            raise ToolGroundingError("Unavailable product references were altered")
    if name == "filter_by_budget":
        products = [session.get(Product, key) for key in dict.fromkeys(values.product_ids)]
        if any(product is None for product in products):
            raise LookupError("Product not found")
        eligible = filter_by_budget(products, values.min_price, values.max_price)
        if values.available_only:
            eligible = [product for product in eligible if product.available]
        if [product.id for product in eligible] != [item["id"] for item in result["items"]]:
            raise ToolGroundingError("Budget result violates current prices")
        if result["excluded_product_ids"] != [product.id for product in products if product not in eligible]:
            raise ToolGroundingError("Excluded product references were altered")
    if name == "get_customer_profile":
        expected = get_customer_profile(session, values.customer_id, values.channel).model_dump(mode="json")
        if result != expected:
            raise ToolGroundingError("Profile differs from actual customer history")
    if name == "get_customer_history":
        statement = select(CustomerInteraction).where(CustomerInteraction.customer_id == values.customer_id)
        if values.channel is not None:
            statement = statement.where(CustomerInteraction.channel == values.channel)
        rows = session.scalars(statement.order_by(CustomerInteraction.occurred_at.desc(), CustomerInteraction.id).offset(values.offset).limit(values.limit)).all()
        if result["items"] != [InteractionOutput.model_validate(row).model_dump(mode="json") for row in rows]:
            raise ToolGroundingError("History does not match actual interaction records")
    if name in {"rank_recommendations", "search_similar_products", "save_recommendation"}:
        response = RecommendationResponse.model_validate(result)
        request = values.request if hasattr(values, "request") else RecommendationRequest(mode="similar", **values.model_dump())
        products = list(session.scalars(select(Product).order_by(Product.id)))
        profile = get_customer_profile(session, request.customer_id, request.channel) if request.customer_id else None
        context, _ = resolve_context(request, products, profile)
        anchor = session.get(Product, request.product_id) if request.product_id else None
        if anchor and context.category is None:
            context.category, context.category_source = anchor.category, "source_product"
        if response.context != context or response.profile != profile or response.query != request.query or response.customer_id != request.customer_id or response.channel != request.channel or response.mode != request.mode:
            raise ToolGroundingError("Recommendation context differs from request or current profile")
        signals = {"text_relevance": bool(context.text_query or anchor), "customer_preference": True,
                   "category_match": bool(context.category or anchor or (profile and profile.category_affinities)),
                   "brand_match": bool(context.brand or anchor or (profile and profile.brand_affinities)),
                   "budget_compatibility": context.min_price is not None or context.max_price is not None, "availability": True}
        weights = {key: weight for key, weight in request.weights.model_dump().items() if signals[key] and weight > 0}
        total = sum(weights.values())
        if not total or response.active_weights != {key: weight / total for key, weight in weights.items()}:
            raise ToolGroundingError("Recommendation weights differ from request")
        if len(response.items) > request.limit:
            raise ToolGroundingError("Recommendation limit exceeded")
        expected_message = "Deterministic TF-IDF recommendations; no LLM was called." if response.items else "No products match the requested constraints. No filters were relaxed."
        if response.message != expected_message:
            raise ToolGroundingError("Recommendation message was fabricated")
        seen = set()
        for rank, item in enumerate(response.items, start=1):
            if item.product.id in seen or item.rank != rank:
                raise ToolGroundingError("Duplicate/inconsistent ranks")
            seen.add(item.product.id)
            if getattr(values, "product_ids", None) is not None and item.product.id not in values.product_ids:
                raise ToolGroundingError("Candidate scope violation")
            if context.category and item.product.category.casefold() != context.category.casefold() or context.brand and item.product.brand.casefold() != context.brand.casefold():
                raise ToolGroundingError("Category or brand constraint violation")
            if item.product.id == request.product_id or request.exclude_purchased and profile and item.product.id in profile.purchased_product_ids:
                raise ToolGroundingError("Source/purchased product exclusion violation")
            if response.context.available_only and not item.product.available:
                raise ToolGroundingError("Availability constraint violation")
            if response.context.strict_budget and not filter_by_budget([item.product], response.context.min_price, response.context.max_price, response.context.min_exclusive, response.context.max_exclusive):
                raise ToolGroundingError("Budget constraint violation")
            if any(not math.isfinite(score) or not 0 <= score <= 1 for score in item.components.values()):
                raise ToolGroundingError("Invalid score components")
            if set(item.components) != set(type(request.weights).model_fields):
                raise ToolGroundingError("Missing score components")
            if abs(sum(item.components[key] * weight for key, weight in response.active_weights.items()) - item.relevance_score) > 1e-7:
                raise ToolGroundingError("Score arithmetic violation")
            if item.explanation != explain(item.product, item.components, context, profile, response.preference_basis, bool(context.text_query or anchor)):
                raise ToolGroundingError("Explanation was fabricated")
    if name == "retrieve_product_documents":
        response = RagResponse.model_validate(result)
        documents = {}
        if response.items:
            with store.locked():
                state = store.load()
                if state is None:
                    raise ToolGroundingError("No indexed evidence")
                documents = {document.id: document for document in store.documents(state)}
        current = {product.id: ProductOutput.model_validate(product) for product in session.scalars(select(Product))}
        validate_grounding(response.items, current, documents)
        if response.llm_used or response.llm_attempted or response.references != [item.product.id for item in response.items] or response.answer != render_grounded_answer(response.items, "deterministic_fallback"):
            raise ToolGroundingError("RAG tool response is not deterministic grounded evidence")
    if name == "get_recommendation_history":
        for entry in result["items"]:
            row = session.get(Recommendation, entry["id"])
            expected = [{"product_id": item.product_id, "rank": item.rank, "relevance_score": item.score,
                         "price_snapshot": str(item.price_snapshot), "explanation": item.explanation}
                        for item in sorted(row.items, key=lambda item: item.rank)] if row else None
            if expected is None or entry["items"] != expected:
                raise ToolGroundingError("Saved recommendation evidence was altered")
