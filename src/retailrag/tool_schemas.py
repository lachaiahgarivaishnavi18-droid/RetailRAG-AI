"""Public tools accept identifiers/requests, never client-supplied product facts."""

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import Field, model_validator

from retailrag.catalog_api import InteractionOutput, ProductOutput
from retailrag.data_schemas import Channel, Identifier, InputRow, Money
from retailrag.recommendation_schemas import RecommendationRequest
from retailrag.workflow_schemas import ToolModel


class ProductIdInput(InputRow):
    product_id: Identifier


class ProductIdsInput(InputRow):
    product_ids: list[Identifier] = Field(min_length=1, max_length=500)


class ProfileInput(InputRow):
    customer_id: Identifier
    channel: Channel | None = None


class CustomerHistoryInput(ProfileInput):
    limit: int = Field(default=25, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class SearchInput(InputRow):
    query: str = Field(default="", max_length=200)
    category: str | None = Field(default=None, min_length=1, max_length=100)
    brand: str | None = Field(default=None, min_length=1, max_length=100)
    min_price: Money | None = None
    max_price: Money | None = None
    available_only: bool = True
    sort: Literal["name", "price_asc", "price_desc", "rating"] = "name"
    limit: int = Field(default=25, ge=1, le=100)
    offset: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def price_order(self):
        if self.min_price is not None and self.max_price is not None and self.min_price > self.max_price:
            raise ValueError("Minimum price must not exceed maximum price")
        return self


class SimilarInput(ProductIdInput):
    min_price: Money | None = None
    max_price: Money | None = None
    available_only: bool = True
    limit: int = Field(default=5, ge=1, le=50)


class BudgetInput(ProductIdsInput):
    min_price: Money | None = None
    max_price: Money | None = None
    available_only: bool = False

    @model_validator(mode="after")
    def required_budget(self):
        if self.min_price is None and self.max_price is None:
            raise ValueError("At least one budget bound is required")
        if self.min_price is not None and self.max_price is not None and self.min_price > self.max_price:
            raise ValueError("Minimum price must not exceed maximum price")
        return self


class RankingInput(ToolModel):
    request: RecommendationRequest
    product_ids: list[Identifier] | None = Field(default=None, min_length=1, max_length=500)


class SaveInput(RankingInput):
    idempotency_key: str = Field(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")


class RecommendationHistoryInput(InputRow):
    customer_id: Identifier | None = None
    channel: Channel | None = None
    limit: int = Field(default=25, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class ProductResult(ToolModel):
    product: ProductOutput


class SearchResult(ToolModel):
    total: int = Field(ge=0)
    limit: int
    offset: int
    items: list[ProductOutput]


class CustomerHistoryResult(ToolModel):
    total: int = Field(ge=0)
    limit: int
    offset: int
    items: list[InteractionOutput]


class BudgetResult(ToolModel):
    items: list[ProductOutput]
    excluded_product_ids: list[str]


class AvailabilityItem(ToolModel):
    product_id: str
    available: bool
    stock_quantity: int = Field(ge=0)


class AvailabilityResult(ToolModel):
    items: list[AvailabilityItem]
    unavailable_product_ids: list[str]


class SavedItem(ToolModel):
    product_id: str
    rank: int = Field(gt=0)
    relevance_score: float = Field(ge=0, le=1)
    price_snapshot: Decimal = Field(ge=0)
    explanation: str


class HistoryItem(ToolModel):
    id: int
    customer_id: str | None
    query: str
    mode: str
    channel: Channel
    created_at: datetime
    items: list[SavedItem]
    complete_snapshot_available: bool


class RecommendationHistoryResult(ToolModel):
    total: int = Field(ge=0)
    limit: int
    offset: int
    price_basis: Literal["saved_recommendation_snapshot"] = "saved_recommendation_snapshot"
    items: list[HistoryItem]


class ExecuteInput(ToolModel):
    arguments: dict = Field(default_factory=dict, max_length=100)
