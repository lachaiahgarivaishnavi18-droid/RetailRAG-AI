"""Independent final checks repeated within the recommendation-save transaction."""

import math

from sqlalchemy import select

from retailrag.catalog_api import ProductOutput
from retailrag.models import Product
from retailrag.preferences import get_customer_profile
from retailrag.rag_documents import fingerprint, product_documents
from retailrag.recommendation_context import resolve_context
from retailrag.recommendations import explain, filter_by_budget


def explanation(item, context, profile, preference_basis):
    text = explain(item.product, item.components, context, profile, preference_basis, bool(context.text_query or item.similarity_score))
    if item.retrieval_source == "chroma":
        text = text.replace("TF-IDF cosine similarity", "Chroma LSA cosine similarity")
    return text + f" Evidence: {item.document_id}."


def validate_workflow_items(session, store, request, context, profile, items, weights, preference_basis):
    from retailrag.workflow_tools import active_ranking_weights
    products = list(session.scalars(select(Product).order_by(Product.id)).all())
    current = {p.id: ProductOutput.model_validate(p) for p in products}
    fresh_profile = get_customer_profile(session, request.customer_id, request.channel) if request.customer_id else None
    if (profile.model_dump(mode="json") if profile else None) != (fresh_profile.model_dump(mode="json") if fresh_profile else None):
        raise ValueError("Customer profile changed during the workflow")
    expected_context, _ = resolve_context(request.recommendation_request(), products, fresh_profile)
    anchor = session.get(Product, request.product_id) if request.product_id else None
    if request.product_id and anchor is None:
        raise LookupError("Source product disappeared")
    if anchor and expected_context.category is None:
        expected_context.category, expected_context.category_source = anchor.category, "source_product"
    if context.model_dump(mode="json") != expected_context.model_dump(mode="json"):
        raise ValueError("Effective context differs from current request/customer constraints")
    if len(items) > request.limit or len({item.product.id for item in items}) != len(items):
        raise ValueError("Recommendation count or uniqueness check failed")
    if items:
        expected_weights = active_ranking_weights(request, context, profile, items, anchor)
        if weights != expected_weights:
            raise ValueError("Ranking weights differ from the request")
    expected_documents = {}
    if any(item.retrieval_source == "chroma" for item in items):
        with store.locked():
            state = store.load()
            if state is None:
                raise ValueError("Vector evidence is no longer available")
            expected_documents = {doc.id: doc for doc in store.documents(state)}
    previous_score = 2.0
    for rank, item in enumerate(items, start=1):
        product = current.get(item.product.id)
        if product is None or fingerprint(product) != fingerprint(item.product):
            raise ValueError("Product facts changed or were fabricated")
        if item.rank != rank or item.relevance_score > previous_score + 1e-8:
            raise ValueError("Ranks/scores are inconsistent")
        previous_score = item.relevance_score
        if request.available_only and not product.available:
            raise ValueError("Unavailable product violates request")
        if context.category and product.category.casefold() != context.category.casefold():
            raise ValueError("Category filter violation")
        if context.brand and product.brand.casefold() != context.brand.casefold():
            raise ValueError("Brand filter violation")
        if request.strict_budget and not filter_by_budget([product], context.min_price, context.max_price, context.min_exclusive, context.max_exclusive):
            raise ValueError("Budget filter violation")
        if product.id == request.product_id or (request.exclude_purchased and profile and product.id in profile.purchased_product_ids):
            raise ValueError("Excluded source/purchased product was recommended")
        if item.retrieval_source == "content":
            expected = product_documents(product)[0]
        else:
            expected = expected_documents.get(item.document_id)
        if expected is None or expected.id != item.document_id or expected.page_content != item.document or expected.metadata != item.metadata:
            raise ValueError("Evidence document is not grounded")
        if set(item.components) != set(type(request.weights).model_fields):
            raise ValueError("Missing ranking components")
        if any(not math.isfinite(score) or not 0 <= score <= 1 for score in item.components.values()):
            raise ValueError("Invalid ranking component")
        if abs(item.similarity_score - item.components["text_relevance"]) > 1e-8:
            raise ValueError("Similarity component differs from retrieved score")
        if abs(sum(item.components[key] * weight for key, weight in weights.items()) - item.relevance_score) > 1e-7:
            raise ValueError("Ranking score does not match its components")
        if item.explanation != explanation(item, context, profile, preference_basis):
            raise ValueError("Explanation differs from grounded facts")
