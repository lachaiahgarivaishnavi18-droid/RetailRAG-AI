"""Validated RAG inputs, retrieved evidence, and grounded answers."""

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from retailrag.catalog_api import ProductOutput
from retailrag.data_schemas import Channel, Identifier, InputRow, Money
from retailrag.recommendation_schemas import CustomerProfile, ResolvedContext


class RagIngestRequest(InputRow):
    product_ids: list[Identifier] | None = Field(default=None, min_length=1, max_length=500)
    force: bool = False


class RagSearchRequest(InputRow):
    query: str = Field(min_length=1, max_length=2000)
    customer_id: Identifier | None = None
    channel: Channel = "ecommerce"
    category: str | None = Field(default=None, min_length=1, max_length=100)
    brand: str | None = Field(default=None, min_length=1, max_length=100)
    source: str | None = Field(default=None, min_length=1, max_length=100)
    product_ids: list[Identifier] | None = Field(default=None, min_length=1, max_length=500)
    min_price: Money | None = None
    max_price: Money | None = None
    available_only: bool = True
    limit: int = Field(default=5, ge=1, le=20)
    min_similarity: float = Field(default=0.05, ge=0, le=1, allow_inf_nan=False)

    @model_validator(mode="after")
    def bounds(self):
        if self.min_price is not None and self.max_price is not None and self.min_price > self.max_price:
            raise ValueError("min_price must be no greater than max_price")
        return self


class RetrievedProduct(BaseModel):
    rank: int
    product: ProductOutput
    similarity_score: float = Field(ge=0, le=1)
    relevance_score: float = Field(ge=0, le=1)
    document_id: str
    document: str
    metadata: dict
    explanation: str


class RagResponse(BaseModel):
    query: str
    engine: Literal["chroma_local_lsa"] = "chroma_local_lsa"
    generation: Literal["deterministic_fallback", "llm_assisted"]
    llm_attempted: bool = False
    llm_used: bool = False
    llm_status: str
    index_generation: str | None
    context: ResolvedContext
    profile: CustomerProfile | None
    metadata_filter: dict | None
    warnings: list[str]
    answer: str
    references: list[str]
    items: list[RetrievedProduct]
