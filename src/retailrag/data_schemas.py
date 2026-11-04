"""Input contracts shared by CSV ingestion and interaction recording."""

import re
import unicodedata
from datetime import datetime, timezone
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator

Channel = Literal["ecommerce", "mobile", "store"]
EventType = Literal["view", "purchase", "wishlist", "cart"]
Identifier = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")]
Money = Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=2, allow_inf_nan=False)]


def clean_text(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).split())


def normalize_search_text(value: str) -> str:
    return " ".join(re.sub(r"[^\w\s]", " ", clean_text(value).casefold()).split())


class InputRow(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    @field_validator("*", mode="before")
    @classmethod
    def normalize_strings(cls, value):
        return clean_text(value) if isinstance(value, str) else value


class ProductInput(InputRow):
    id: Identifier
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=10000)
    category: str = Field(min_length=1, max_length=100)
    brand: str = Field(min_length=1, max_length=100)
    price: Money
    currency: Literal["INR"] = "INR"
    rating: float = Field(default=0, ge=0, le=5, allow_inf_nan=False)
    stock_quantity: int = Field(ge=0, le=2_147_483_647)
    features: list[str] = Field(default_factory=list)
    attributes: dict[str, str] = Field(default_factory=dict)
    image_url: HttpUrl | None = None

    @field_validator("features")
    @classmethod
    def clean_features(cls, values):
        return list(dict.fromkeys(clean_text(v) for v in values if clean_text(v)))

    @field_validator("attributes")
    @classmethod
    def clean_attributes(cls, values):
        return {clean_text(k): clean_text(v) for k, v in values.items() if clean_text(k)}

    def record(self) -> dict:
        values = self.model_dump()
        values["image_url"] = str(self.image_url) if self.image_url else None
        values["search_text"] = normalize_search_text(" ".join([
            self.name, self.description, self.category, self.brand,
            *self.features, *self.attributes.keys(), *self.attributes.values(),
            f"{self.currency} {self.price:.2f}",
        ]))
        return values


class CustomerInput(InputRow):
    id: Identifier
    name: str = Field(min_length=1, max_length=200)
    preferred_categories: list[str] = Field(default_factory=list)
    preferred_brands: list[str] = Field(default_factory=list)
    budget_min: Money = Decimal("0")
    budget_max: Money

    @field_validator("preferred_categories", "preferred_brands")
    @classmethod
    def clean_preferences(cls, values):
        return list(dict.fromkeys(clean_text(v) for v in values if clean_text(v)))

    @model_validator(mode="after")
    def budget_order(self):
        if self.budget_max < self.budget_min:
            raise ValueError("budget_max must be at least budget_min")
        return self


class InteractionInput(InputRow):
    id: Identifier
    customer_id: Identifier
    product_id: Identifier
    event_type: EventType
    channel: Channel
    quantity: int = Field(default=1, gt=0, le=2_147_483_647)
    occurred_at: datetime

    @field_validator("occurred_at")
    @classmethod
    def utc_timestamp(cls, value):
        if value.tzinfo is None:
            raise ValueError("occurred_at must include a timezone")
        return value.astimezone(timezone.utc)
