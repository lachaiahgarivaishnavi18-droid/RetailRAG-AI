"""Validated recommendation requests, profiles, and explainable results."""

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from retailrag.catalog_api import ProductOutput
from retailrag.data_schemas import Channel, Identifier, InputRow, Money

RecommendationMode = Literal["personalized", "similar", "budget", "category", "brand", "new_customer", "context_aware"]


class RankingWeights(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text_relevance: float = Field(default=0.40, ge=0, le=1, allow_inf_nan=False)
    customer_preference: float = Field(default=0.20, ge=0, le=1, allow_inf_nan=False)
    category_match: float = Field(default=0.15, ge=0, le=1, allow_inf_nan=False)
    brand_match: float = Field(default=0.10, ge=0, le=1, allow_inf_nan=False)
    budget_compatibility: float = Field(default=0.10, ge=0, le=1, allow_inf_nan=False)
    availability: float = Field(default=0.05, ge=0, le=1, allow_inf_nan=False)

    @model_validator(mode="after")
    def nonzero_total(self):
        if sum(self.model_dump().values()) <= 0:
            raise ValueError("At least one ranking weight must be positive")
        return self


class RecommendationRequest(InputRow):
    mode: RecommendationMode = "context_aware"
    customer_id: Identifier | None = None
    product_id: Identifier | None = None
    query: str = Field(default="", max_length=2000)
    category: str | None = Field(default=None, min_length=1, max_length=100)
    brand: str | None = Field(default=None, min_length=1, max_length=100)
    min_price: Money | None = None
    max_price: Money | None = None
    strict_budget: bool = True
    available_only: bool = True
    exclude_purchased: bool = False
    channel: Channel = "ecommerce"
    limit: int = Field(default=5, ge=1, le=50)
    weights: RankingWeights = Field(default_factory=RankingWeights)

    @model_validator(mode="after")
    def required_context(self):
        if self.mode == "personalized" and self.customer_id is None:
            raise ValueError("personalized mode requires customer_id")
        if self.mode == "similar" and self.product_id is None:
            raise ValueError("similar mode requires product_id")
        if self.mode != "similar" and self.product_id is not None:
            raise ValueError("product_id is only used in similar mode")
        if self.mode == "category" and self.category is None:
            raise ValueError("category mode requires category")
        if self.mode == "brand" and self.brand is None:
            raise ValueError("brand mode requires brand")
        if self.mode == "budget" and self.min_price is None and self.max_price is None and not self.query:
            raise ValueError("budget mode requires a price bound or a query containing a budget")
        if self.mode == "context_aware" and not self.query:
            raise ValueError("context_aware mode requires query")
        if self.mode == "new_customer" and self.customer_id is not None:
            raise ValueError("new_customer mode is anonymous; use personalized mode for an existing customer")
        if self.min_price is not None and self.max_price is not None and self.min_price > self.max_price:
            raise ValueError("min_price must be no greater than max_price")
        return self


class CustomerProfile(BaseModel):
    customer_id: str
    name: str
    channel: Channel | None
    cold_start: bool
    declared_categories: list[str]
    declared_brands: list[str]
    category_affinities: dict[str, float]
    brand_affinities: dict[str, float]
    product_affinities: dict[str, float]
    budget_min: Decimal
    budget_max: Decimal
    observed_purchase_median_price: Decimal | None
    observed_price_basis: Literal["current_catalog"] = "current_catalog"
    event_counts: dict[str, int]
    channel_counts: dict[str, int]
    viewed_product_ids: list[str]
    purchased_product_ids: list[str]
    wishlist_product_ids: list[str]
    interaction_count: int
    source: str


class ResolvedContext(BaseModel):
    category: str | None
    brand: str | None
    category_source: Literal["explicit", "query", "source_product"] | None = None
    brand_source: Literal["explicit", "query"] | None = None
    min_price: Decimal | None
    max_price: Decimal | None
    min_exclusive: bool = False
    max_exclusive: bool = False
    budget_sources: dict[str, str]
    strict_budget: bool
    available_only: bool
    exclude_purchased: bool
    text_query: str


class RecommendationResultItem(BaseModel):
    rank: int
    product: ProductOutput
    similarity_score: float = Field(ge=0, le=1)
    relevance_score: float = Field(ge=0, le=1)
    components: dict[str, float]
    explanation: str


class RecommendationResponse(BaseModel):
    id: int | None = None
    created_at: datetime | None = None
    mode: RecommendationMode
    query: str
    customer_id: str | None
    channel: Channel
    engine: Literal["deterministic_tfidf"] = "deterministic_tfidf"
    llm_used: Literal[False] = False
    message: str
    warnings: list[str]
    context: ResolvedContext
    profile: CustomerProfile | None
    preference_basis: str
    active_weights: dict[str, float]
    catalog_size: int
    candidate_count: int
    items: list[RecommendationResultItem]
