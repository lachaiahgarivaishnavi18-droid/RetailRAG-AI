"""Validated LangChain tools used by actual workflow nodes.

Tool results come from local services/database queries. Only validated JSON-safe
outputs are accepted; execution audits keep arguments, summaries, and digests.
"""

import numpy as np
from pydantic import Field, ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from retailrag.catalog_api import ProductOutput
from retailrag.content_index import ContentIndex
from retailrag.data_schemas import Channel, Identifier
from retailrag.models import CustomerInteraction, Product
from retailrag.preferences import get_customer_profile
from retailrag.rag import search_products as rag_search
from retailrag.rag_documents import fingerprint, product_documents
from retailrag.rag_schemas import RagSearchRequest
from retailrag.recommendation_context import resolve_context
from retailrag.recommendation_schemas import CustomerProfile, ResolvedContext
from retailrag.recommendations import affinity, budget_compatibility, filter_by_availability, filter_by_budget, popularity_scores, rank_recommendations
from retailrag.workflow_schemas import ToolCall, ToolModel, WorkflowItem, WorkflowOutput, WorkflowRequest
from retailrag.tool_registry import ToolRegistry


class RequestInput(ToolModel):
    request: WorkflowRequest


class ProfileInput(ToolModel):
    customer_id: Identifier
    channel: Channel | None = None


class ContextInput(RequestInput):
    profile: CustomerProfile | None = None


class RetrievalInput(ContextInput):
    context: ResolvedContext


class ScoringInput(RetrievalInput):
    items: list[WorkflowItem] = Field(max_length=500)


class ValidationInput(ScoringInput):
    active_weights: dict[str, float]
    preference_basis: str


class ItemsInput(ToolModel):
    items: list[WorkflowItem] = Field(max_length=500)


class ContextOutput(ToolModel):
    context: ResolvedContext
    warnings: list[str]


class ItemsOutput(ToolModel):
    items: list[WorkflowItem]
    warnings: list[str] = Field(default_factory=list)
    index_generation: str | None = None


class ScoresOutput(ItemsOutput):
    active_weights: dict[str, float]
    preference_basis: str


class AvailabilityOutput(ToolModel):
    items: list[WorkflowItem]
    rejected_product_ids: list[str]


class CatalogOutput(ToolModel):
    products: int
    interactions: int


class IndexOutput(ToolModel):
    status: str
    indexed_products: int
    indexed_chunks: int
    generation: str | None


class ValidationOutput(ToolModel):
    valid: bool
    checked_products: int
    references: list[str]


class SaveInput(ToolModel):
    run_id: Identifier
    request: WorkflowRequest
    output: WorkflowOutput


class SaveOutput(ToolModel):
    output: WorkflowOutput


def safe_error(exc):
    if isinstance(exc, ValidationError):
        return "Tool input or output failed schema validation"
    if isinstance(exc, LookupError):
        return "Requested customer, product, or indexed evidence was not found"
    if isinstance(exc, ValueError):
        return "Request or evidence validation failed; check query, filters, and grounding"
    return f"Operation failed ({type(exc).__name__}); no unverified result was accepted"


def active_ranking_weights(request, context, profile, items, anchor):
    signals = {"text_relevance": bool(context.text_query or anchor or any(item.retrieval_source == "chroma" for item in items)),
               "customer_preference": True, "category_match": bool(context.category or (profile and profile.category_affinities)),
               "brand_match": bool(context.brand or anchor or (profile and profile.brand_affinities)),
               "budget_compatibility": context.min_price is not None or context.max_price is not None, "availability": True}
    weights = {key: weight for key, weight in request.weights.model_dump().items() if signals[key] and weight > 0}
    total = sum(weights.values())
    if not total:
        raise ValueError("No positive ranking weight applies to this context")
    return {key: weight / total for key, weight in weights.items()}


class WorkflowTools(ToolRegistry):
    def __init__(self, engine, store):
        super().__init__()
        self.engine, self.store = engine, store
        self.register("get_catalog_context", "Read real catalog and interaction counts", ToolModel, CatalogOutput, self.catalog_context)
        self.register("get_rag_status", "Read actual persistent vector-index readiness", ToolModel, IndexOutput, self.index_status)
        self.register("understand_query", "Resolve budget, category and brand constraints using catalog labels", ContextInput, ContextOutput, self.context)
        self.register("get_customer_profile", "Analyze customer history across all shopping channels", ProfileInput, CustomerProfile, self.customer_profile)
        self.register("search_products", "Retrieve eligible content-based candidates with actual product evidence", RetrievalInput, ItemsOutput, self.content_retrieval)
        self.register("retrieve_product_documents", "Retrieve validated Chroma documents without calling an LLM", RetrievalInput, ItemsOutput, self.vector_retrieval)
        self.register("score_recommendation_candidates", "Compute six evidence-backed ranking components", ScoringInput, ScoresOutput, self.score_candidates)
        self.register("rank_recommendations", "Sort scored candidates deterministically", ItemsInput, ItemsOutput, self.rank_items)
        self.register("check_product_availability", "Recheck current database facts and requested stock constraints", ScoringInput, AvailabilityOutput, self.availability)
        self.register("explain_recommendations", "Render explanations from actual scores, product facts, and evidence IDs", ValidationInput, ItemsOutput, self.explain)
        self.register("validate_recommendations", "Validate references, filters, scores, and source-document grounding", ValidationInput, ValidationOutput, self.validate)
        self.register("save_recommendation", "Atomically validate and save the workflow recommendation and evidence snapshot", SaveInput, SaveOutput, self.save, effect="write")
        self.register_catalog_helpers()

    def register_catalog_helpers(self):
        from retailrag.retail_tools import RetailTools
        public = RetailTools(self.engine, self.store)
        for name in ("get_product_details", "get_customer_history", "search_similar_products", "filter_by_budget", "get_recommendation_history"):
            spec = public.specs[name]
            self.register(name, spec["tool"].description, spec["input"], spec["output"],
                          lambda values, name=name: public.call(name, values.model_dump(mode="json")))

    def catalog_context(self, values):
        with Session(self.engine) as session:
            return {"products": session.scalar(select(func.count()).select_from(Product)),
                    "interactions": session.scalar(select(func.count()).select_from(CustomerInteraction))}

    def index_status(self, values):
        with Session(self.engine) as session:
            result = self.store.status(session)
        return {key: result[key] for key in ("status", "indexed_products", "indexed_chunks", "generation")}

    def customer_profile(self, values):
        with Session(self.engine) as session:
            return get_customer_profile(session, values.customer_id, values.channel)

    def context(self, values):
        with Session(self.engine) as session:
            products = list(session.scalars(select(Product).order_by(Product.id)))
            context, warnings = resolve_context(values.request.recommendation_request(), products, values.profile)
            if values.request.product_id:
                source = session.get(Product, values.request.product_id)
                if source is None:
                    raise LookupError("Source product not found")
                if context.category is None:
                    context.category, context.category_source = source.category, "source_product"
            return {"context": context, "warnings": warnings}

    def content_retrieval(self, values):
        request, context = values.request, values.context
        with Session(self.engine) as session:
            products = list(session.scalars(select(Product).order_by(Product.id)))
            index = ContentIndex(products)
            scores = index.query_scores(context.text_query)
            if request.product_id:
                similar = index.similar_scores(request.product_id)
                scores = 0.7 * similar + 0.3 * scores if context.text_query else similar
            eligible = filter_by_availability(products, request.available_only)
            if request.strict_budget:
                eligible = filter_by_budget(eligible, context.min_price, context.max_price, context.min_exclusive, context.max_exclusive)
            items = []
            for product in eligible:
                if context.category and product.category.casefold() != context.category.casefold():
                    continue
                if context.brand and product.brand.casefold() != context.brand.casefold():
                    continue
                if product.id == request.product_id:
                    continue
                if request.exclude_purchased and values.profile and product.id in values.profile.purchased_product_ids:
                    continue
                similarity = float(scores[index.positions[product.id]])
                if (context.text_query or request.product_id) and similarity <= 0:
                    continue
                snapshot = ProductOutput.model_validate(product)
                document = product_documents(snapshot)[0]
                items.append(WorkflowItem(rank=0, product=snapshot, similarity_score=round(similarity, 8), relevance_score=0,
                                          components={}, explanation="", retrieval_source="content", document_id=document.id,
                                          document=document.page_content, metadata=document.metadata))
            return {"items": items}

    def vector_retrieval(self, values):
        with Session(self.engine) as session:
            response = rag_search(session, self.store, RagSearchRequest(
                query=values.request.query, customer_id=values.request.customer_id, channel=values.request.channel,
                category=values.context.category, brand=values.context.brand,
                min_price=values.request.min_price, max_price=values.request.max_price,
                available_only=values.request.available_only, limit=20,
            ), allow_llm=False)
            items = [WorkflowItem(rank=0, product=item.product, similarity_score=item.similarity_score,
                                  relevance_score=0, components={}, explanation="", retrieval_source="chroma",
                                  document_id=item.document_id, document=item.document, metadata=item.metadata)
                     for item in response.items if not values.request.exclude_purchased or not values.profile or item.product.id not in values.profile.purchased_product_ids]
            return {"items": sorted(items, key=lambda item: item.product.id), "warnings": response.warnings, "index_generation": response.index_generation}

    def score_candidates(self, values):
        request, context, profile = values.request, values.context, values.profile
        with Session(self.engine) as session:
            products = list(session.scalars(select(Product).order_by(Product.id)))
            index = ContentIndex(products)
            if profile:
                declared = " ".join([*profile.declared_categories, *profile.declared_brands])
                preferences = index.preference_scores(profile.product_affinities, declared)
                basis = "customer_profile"
                if not preferences.any():
                    preferences, basis = popularity_scores(session, products, request.channel)
            else:
                preferences, basis = popularity_scores(session, products, request.channel)
            anchor = session.get(Product, request.product_id) if request.product_id else None
            weights = active_ranking_weights(request, context, profile, values.items, anchor)
            scored = []
            for item in values.items:
                product = item.product
                if product.id not in index.positions:
                    raise LookupError("Candidate product not found")
                components = {
                    "text_relevance": item.similarity_score,
                    "customer_preference": float(preferences[index.positions[product.id]]),
                    "category_match": float(product.category.casefold() == context.category.casefold()) if context.category else affinity(profile.category_affinities, product.category) if profile else 0,
                    "brand_match": float(product.brand.casefold() == (context.brand or anchor.brand).casefold()) if context.brand or anchor else affinity(profile.brand_affinities, product.brand) if profile else 0,
                    "budget_compatibility": budget_compatibility(product.price, context.min_price, context.max_price), "availability": float(product.available),
                }
                scored.append(item.model_copy(update={"components": {key: round(score, 8) for key, score in components.items()},
                                                      "relevance_score": round(rank_recommendations(components, weights), 8)}))
            return {"items": sorted(scored, key=lambda item: item.product.id), "active_weights": weights, "preference_basis": basis}

    def rank_items(self, values):
        ranked = sorted(values.items, key=lambda item: (-item.relevance_score, -item.similarity_score, -item.product.rating, item.product.price, item.product.id))
        return {"items": [item.model_copy(update={"rank": rank}) for rank, item in enumerate(ranked, start=1)]}

    def availability(self, values):
        accepted, rejected = [], []
        with Session(self.engine) as session:
            for item in values.items:
                current = session.get(Product, item.product.id)
                if current is None or fingerprint(ProductOutput.model_validate(current)) != fingerprint(item.product) or (values.request.available_only and not current.available):
                    rejected.append(item.product.id)
                else:
                    accepted.append(item)
        return {"items": accepted, "rejected_product_ids": rejected}

    def validate(self, values):
        from retailrag.workflow_validation import validate_workflow_items
        with Session(self.engine) as session:
            validate_workflow_items(session, self.store, values.request, values.context, values.profile, values.items,
                                    values.active_weights, values.preference_basis)
        return {"valid": True, "checked_products": len(values.items), "references": [item.product.id for item in values.items]}

    def explain(self, values):
        from retailrag.workflow_validation import explanation
        return {"items": [item.model_copy(update={"explanation": explanation(item, values.context, values.profile, values.preference_basis)}) for item in values.items]}

    def save(self, values):
        from retailrag.workflow_persistence import save_workflow_recommendation
        return {"output": save_workflow_recommendation(self.engine, self.store, values.run_id, values.request, values.output)}
