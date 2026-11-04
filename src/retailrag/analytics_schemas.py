"""Public analytics contracts with explicit measurement scope."""

from datetime import datetime

from pydantic import BaseModel, Field


class Period(BaseModel):
    date_from: str | None
    date_to: str | None
    timezone: str


class Totals(BaseModel):
    products: int = Field(ge=0)
    customers: int = Field(ge=0)
    interactions: int = Field(ge=0)
    recommendations: int = Field(ge=0)
    agent_executions: int = Field(ge=0)
    tool_invocations: int = Field(ge=0)
    simulations: int = Field(ge=0)


class OverviewAnalytics(BaseModel):
    generated_at: datetime
    period: Period
    totals: Totals
    inventory: dict[str, int]
    popular_products: list[dict]
    popular_categories: list[dict]
    channel_activity: list[dict]
    provenance: list[dict]
    recent_recommendations: list[dict]


class RecommendationAnalytics(BaseModel):
    period: Period
    total_runs: int = Field(ge=0)
    total_items: int = Field(ge=0)
    average_items_per_run: float = Field(ge=0)
    average_score: float = Field(ge=0, le=1)
    daily_trend: list[dict]
    mode_distribution: list[dict]
    category_distribution: list[dict]
    product_performance: list[dict]
    event_mix: list[dict]
    active_customers: int = Field(ge=0)
    category_basis: str
    measurement_notes: str


class ChannelAnalytics(BaseModel):
    period: Period
    channels: list[dict]
    cross_channel_customers: int = Field(ge=0)
    daily_activity: list[dict]
    event_mix: list[dict]
    measurement_notes: str
