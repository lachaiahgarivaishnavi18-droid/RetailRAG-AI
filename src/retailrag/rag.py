"""Retrieve from Chroma, validate evidence against SQLite, rank, and respond."""

import hashlib

import httpx
import numpy as np
from sqlalchemy import select

from retailrag.catalog_api import ProductOutput
from retailrag.models import Product
from retailrag.preferences import get_customer_profile
from retailrag.rag_documents import fingerprint
from retailrag.rag_generation import render_grounded_answer, select_with_openai
from retailrag.rag_schemas import RagResponse, RetrievedProduct
from retailrag.recommendation_context import resolve_context
from retailrag.recommendation_schemas import RecommendationRequest
from retailrag.recommendations import affinity, budget_compatibility, filter_by_budget


def metadata_filter(request, context):
    conditions = []
    for field, value in (("category_key", context.category.casefold() if context.category else None),
                         ("brand_key", context.brand.casefold() if context.brand else None), ("source", request.source)):
        if value is not None:
            conditions.append({field: {"$eq": value}})
    if request.available_only:
        conditions.append({"available": {"$eq": True}})
    if context.min_price is not None:
        conditions.append({"price_cents": {"$gt" if context.min_exclusive else "$gte": int(context.min_price * 100)}})
    if context.max_price is not None:
        conditions.append({"price_cents": {"$lt" if context.max_exclusive else "$lte": int(context.max_price * 100)}})
    if request.product_ids:
        conditions.append({"product_id": {"$in": sorted(set(request.product_ids))}})
    return {"$and": conditions} if len(conditions) > 1 else conditions[0] if conditions else None


def validate_grounding(items, current, expected_documents):
    seen = set()
    for item in items:
        product_id = item.product.id
        if product_id in seen or product_id not in current:
            raise ValueError("Duplicate or unknown grounded product")
        seen.add(product_id)
        if item.product.model_dump() != current[product_id].model_dump():
            raise ValueError("Grounded product facts differ from current catalog")
        expected = expected_documents.get(item.document_id)
        if expected is None or item.document != expected.page_content or item.metadata != expected.metadata:
            raise ValueError("Grounded document differs from indexed evidence")
        if fingerprint(item.product) != item.metadata["product_fingerprint"]:
            raise ValueError("Stale grounded product")


def search_products(session, store, request, *, allow_llm=True):
    products = list(session.scalars(select(Product).order_by(Product.id)))
    current = {p.id: ProductOutput.model_validate(p) for p in products}
    profile = get_customer_profile(session, request.customer_id, request.channel) if request.customer_id else None
    context, warnings = resolve_context(RecommendationRequest(
        query=request.query, customer_id=request.customer_id, channel=request.channel, category=request.category,
        brand=request.brand, min_price=request.min_price, max_price=request.max_price, available_only=request.available_only,
    ), products, profile)
    filters = metadata_filter(request, context)
    by_product, expected_documents = {}, {}
    with store.locked():
        state = store.load()
        generation_id = state["generation"] if state else None
        if state is None:
            warnings.append("The vector index has not been ingested. Run /rag/ingest first.")
        elif state["products"]:
            expected_documents = {doc.id: doc for doc in store.documents(state)}
            indexed = state["products"]
            stale = {key for key, value in indexed.items() if key not in current or fingerprint(current[key]) != fingerprint(ProductOutput.model_validate(value))}
            if stale or current.keys() - indexed.keys():
                warnings.append("The index differs from the current catalog. Changed/deleted product evidence is excluded; re-ingest to synchronize it.")
            vectorstore, embeddings = store.vectorstore(state)
            text = context.text_query
            if not text:
                # A budget-only request retrieves with its selected category/brand, or
                # the generic catalog query. It still uses Chroma and metadata filters.
                text = " ".join(part for part in [context.category, context.brand, "shopping"] if part)
                if not np.any(embeddings.embed_query(text)):
                    text = " ".join(sorted({p.category for p in products}))
            query_vector = embeddings.embed_query(text)
            if not np.any(query_vector):
                warnings.append("The local embedding vocabulary did not match the query; no unrelated products were substituted.")
            else:
                candidate_limit = min(state["chunk_count"], max(100, request.limit * 20))
                if state["chunk_count"] > candidate_limit:
                    warnings.append("Retrieval inspected a bounded candidate set; fewer unique products may be returned when many chunks belong to one product.")
                hits = vectorstore.similarity_search_with_score(text, k=candidate_limit, filter=filters)
                for document, distance in hits:
                    metadata = document.metadata
                    product_id = metadata.get("product_id")
                    if product_id not in current or product_id in stale:
                        continue
                    product = current[product_id]
                    document_id = f"{product_id}:{metadata.get('chunk')}:{metadata.get('document_hash', '')[:12]}"
                    expected = expected_documents.get(document_id)
                    if expected is None or document.page_content != expected.page_content or metadata != expected.metadata or hashlib.sha256(document.page_content.encode()).hexdigest() != metadata.get("document_hash"):
                        warnings.append("A retrieved document failed grounding validation and was excluded.")
                        continue
                    # Check live facts again instead of trusting metadata alone.
                    if request.available_only and not product.available:
                        continue
                    if not filter_by_budget([product], context.min_price, context.max_price, context.min_exclusive, context.max_exclusive):
                        continue
                    if context.category and product.category.casefold() != context.category.casefold():
                        continue
                    if context.brand and product.brand.casefold() != context.brand.casefold():
                        continue
                    if request.source and product.source != request.source:
                        continue
                    if request.product_ids and product_id not in request.product_ids:
                        continue
                    similarity = float(np.clip(1 - float(distance), 0, 1))
                    if similarity <= 0 or similarity < request.min_similarity:
                        continue
                    preference = (affinity(profile.category_affinities, product.category) + affinity(profile.brand_affinities, product.brand)) / 2 if profile else 0
                    budget_score = budget_compatibility(product.price, context.min_price, context.max_price)
                    score = 0.75 * similarity + 0.15 * preference + 0.10 * budget_score if profile else similarity
                    item = RetrievedProduct(rank=0, product=product, similarity_score=round(similarity, 8), relevance_score=round(score, 8),
                                            document_id=document_id, document=document.page_content, metadata=metadata,
                                            explanation=f"Retrieved product document {document_id}; cosine similarity {similarity:.4f}." +
                                            (f" Cross-channel category/brand affinity {preference:.4f}." if profile else ""))
                    if product_id not in by_product or item.similarity_score > by_product[product_id].similarity_score:
                        by_product[product_id] = item
    items = sorted(by_product.values(), key=lambda item: (-item.relevance_score, -item.similarity_score, -item.product.rating, item.product.price, item.product.id))[:request.limit]
    validate_grounding(items, current, expected_documents)
    attempted, used = False, False
    llm_status = "disabled"
    generation = "deterministic_fallback"
    if allow_llm and store.settings.demo_mode != "true" and store.settings.rag_generation_mode in {"auto", "openai"}:
        key = store.settings.openai_api_key
        if key is None or not key.get_secret_value().strip():
            llm_status = "missing_credentials"
            warnings.append("Demo mode: local grounded answers are active; no external AI credentials are required.")
        elif not items:
            llm_status = "no_evidence"
        else:
            attempted = True
            try:
                selected = select_with_openai(store.settings, request.query, items, request.limit)
                validate_grounding(selected, current, expected_documents)
                items = selected
                used, llm_status, generation = True, "used", "llm_assisted"
            except (httpx.HTTPError, ValueError, KeyError, TypeError):
                llm_status = "failed_or_invalid"
                warnings.append("LLM selection failed validation or was unavailable; deterministic grounded fallback was used.")
    for rank, item in enumerate(items, start=1):
        item.rank = rank
    return RagResponse(query=request.query, generation=generation, llm_attempted=attempted, llm_used=used, llm_status=llm_status,
                       index_generation=generation_id, context=context, profile=profile, metadata_filter=filters,
                       warnings=list(dict.fromkeys(warnings)), answer=render_grounded_answer(items, generation),
                       references=[item.product.id for item in items], items=items)
