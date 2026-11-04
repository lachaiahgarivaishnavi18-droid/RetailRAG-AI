"""Public ID/request-based retail tools sharing the workflow tool executor."""

from contextlib import contextmanager

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from retailrag.catalog_api import ProductOutput, history as customer_history, products as catalog_search
from retailrag.models import Customer, Product, Recommendation, RecommendationSnapshot
from retailrag.preferences import get_customer_profile
from retailrag.rag import search_products as rag_search
from retailrag.rag_schemas import RagResponse, RagSearchRequest
from retailrag.recommendation_schemas import CustomerProfile, RecommendationRequest, RecommendationResponse
from retailrag.recommendations import filter_by_availability, filter_by_budget, generate_recommendations
from retailrag.tool_registry import ToolRegistry
from retailrag.tool_schemas import (
    AvailabilityResult, BudgetInput, BudgetResult, CustomerHistoryInput, CustomerHistoryResult,
    ProductIdInput, ProductIdsInput, ProductResult, ProfileInput, RankingInput,
    RecommendationHistoryInput, RecommendationHistoryResult, SaveInput, SearchInput, SearchResult, SimilarInput,
)


class RetailTools(ToolRegistry):
    def __init__(self, engine, store, session=None):
        super().__init__()
        self.engine, self.store, self.session = engine, store, session
        self.register("search_products", "Search the actual catalog with literal keyword and strict metadata/price filters", SearchInput, SearchResult, self.search,
                      example={"query": "wireless", "max_price": "3000", "available_only": True})
        self.register("get_product_details", "Read current product facts by database ID", ProductIdInput, ProductResult, self.product_details, example={"product_id": "P001"})
        self.register("get_customer_profile", "Infer customer preferences from actual cross-channel history", ProfileInput, CustomerProfile, self.profile, example={"customer_id": "C001", "channel": "mobile"})
        self.register("get_customer_history", "Read paginated customer events from the database", CustomerHistoryInput, CustomerHistoryResult, self.history, example={"customer_id": "C001", "limit": 5})
        self.register("search_similar_products", "Preview source-category TF-IDF recommendations without saving history", SimilarInput, RecommendationResponse, self.similar, example={"product_id": "P001", "max_price": "3000"})
        self.register("retrieve_product_documents", "Retrieve actual Chroma evidence with grounded deterministic response; never calls an LLM", RagSearchRequest, RagResponse, self.documents, example={"query": "wireless headphones under INR 3000"})
        self.register("filter_by_budget", "Filter supplied product IDs using current database prices, never caller-supplied prices", BudgetInput, BudgetResult, self.budget, example={"product_ids": ["P001", "P002", "P003"], "max_price": "3000"})
        self.register("check_product_availability", "Read actual stock and availability for selected IDs", ProductIdsInput, AvailabilityResult, self.availability, example={"product_ids": ["P001", "P004"]})
        preview = {"request": {"query": "wireless headphones under INR 3000", "customer_id": "C001", "channel": "mobile"}}
        self.register("rank_recommendations", "Preview server-computed recommendation scores; optional candidate IDs are filtered before ranking/limit", RankingInput, RecommendationResponse, self.rank, example=preview)
        self.register("save_recommendation", "Generate and atomically save a grounded recommendation from a request; requires an idempotency key", SaveInput, RecommendationResponse, self.save, effect="write",
                      example={**preview, "idempotency_key": "choose-a-unique-key"})
        self.register("get_recommendation_history", "Read persisted historical items and price snapshots without regenerating results", RecommendationHistoryInput, RecommendationHistoryResult, self.recommendation_history, example={"customer_id": "C001", "limit": 5})

    @contextmanager
    def database(self):
        if self.session is not None:
            yield self.session
        else:
            with Session(self.engine) as session:
                yield session

    def selected_products(self, session, ids):
        records = {row.id: row for row in session.scalars(select(Product).where(Product.id.in_(set(ids))))}
        if set(ids) - records.keys():
            raise LookupError("One or more products were not found")
        return [records[key] for key in dict.fromkeys(ids)]

    def search(self, values):
        with self.database() as session:
            return catalog_search(q=values.query, category=values.category, brand=values.brand,
                                  min_price=values.min_price, max_price=values.max_price,
                                  available=True if values.available_only else None, sort=values.sort,
                                  limit=values.limit, offset=values.offset, session=session)

    def product_details(self, values):
        with self.database() as session:
            return {"product": ProductOutput.model_validate(self.selected_products(session, [values.product_id])[0])}

    def profile(self, values):
        with self.database() as session:
            return get_customer_profile(session, values.customer_id, values.channel)

    def history(self, values):
        with self.database() as session:
            if session.get(Customer, values.customer_id) is None:
                raise LookupError("Customer not found")
            return customer_history(customer_id=values.customer_id, channel=values.channel,
                                    limit=values.limit, offset=values.offset, session=session)

    def similar(self, values):
        with self.database() as session:
            return generate_recommendations(session, RecommendationRequest(mode="similar", **values.model_dump()), persist=False)

    def documents(self, values):
        with self.database() as session:
            return rag_search(session, self.store, values, allow_llm=False)

    def budget(self, values):
        with self.database() as session:
            products = self.selected_products(session, values.product_ids)
            eligible = filter_by_availability(filter_by_budget(products, values.min_price, values.max_price), values.available_only)
            matched = {product.id for product in eligible}
            return {"items": [ProductOutput.model_validate(product) for product in eligible],
                    "excluded_product_ids": [product.id for product in products if product.id not in matched]}

    def availability(self, values):
        with self.database() as session:
            products = self.selected_products(session, values.product_ids)
            return {"items": [{"product_id": product.id, "available": product.available, "stock_quantity": product.stock_quantity} for product in products],
                    "unavailable_product_ids": [product.id for product in products if not product.available]}

    def rank(self, values):
        with self.database() as session:
            if values.product_ids is not None:
                self.selected_products(session, values.product_ids)
            return generate_recommendations(session, values.request, persist=False,
                                            candidate_ids=set(values.product_ids) if values.product_ids is not None else None)

    def save(self, values):
        if self.session is None:
            raise ValueError("Saving requires the audited tool service transaction")
        if values.product_ids is not None:
            self.selected_products(self.session, values.product_ids)
        return generate_recommendations(self.session, values.request, persist=True, commit=False,
                                        candidate_ids=set(values.product_ids) if values.product_ids is not None else None)

    def recommendation_history(self, values):
        with self.database() as session:
            statement = select(Recommendation)
            if values.customer_id is not None:
                statement = statement.where(Recommendation.customer_id == values.customer_id)
            if values.channel is not None:
                statement = statement.where(Recommendation.channel == values.channel)
            total = session.scalar(select(func.count()).select_from(statement.subquery()))
            rows = session.scalars(statement.options(selectinload(Recommendation.items)).order_by(Recommendation.id.desc()).offset(values.offset).limit(values.limit)).all()
            items = [{"id": row.id, "customer_id": row.customer_id, "query": row.query, "mode": row.mode,
                      "channel": row.channel, "created_at": row.created_at,
                      "complete_snapshot_available": session.get(RecommendationSnapshot, row.id) is not None,
                      "items": [{"product_id": item.product_id, "rank": item.rank, "relevance_score": item.score,
                                 "price_snapshot": item.price_snapshot, "explanation": item.explanation}
                                for item in sorted(row.items, key=lambda item: item.rank)]} for row in rows]
            return {"total": total, "limit": values.limit, "offset": values.offset, "items": items}
