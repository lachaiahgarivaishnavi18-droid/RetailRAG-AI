"""Relational retail schema and additive workflow audit records."""

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Index, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class UTCDateTime(TypeDecorator):
    """Restore UTC timezone information removed by SQLite's datetime storage."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("Timestamp must include a timezone")
        return value.astimezone(timezone.utc)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


class Base(DeclarativeBase):
    pass


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint("price >= 0", name="product_price_nonnegative"),
        CheckConstraint("rating >= 0 AND rating <= 5", name="product_rating_range"),
        CheckConstraint("stock_quantity >= 0", name="product_stock_nonnegative"),
        CheckConstraint("currency = 'INR'", name="product_currency_inr"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(100), index=True)
    brand: Mapped[str] = mapped_column(String(100), index=True)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), index=True)
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    rating: Mapped[float] = mapped_column(default=0.0)
    stock_quantity: Mapped[int]
    features: Mapped[list[str]] = mapped_column(JSON, default=list)
    attributes: Mapped[dict] = mapped_column(JSON, default=dict)
    image_url: Mapped[str | None] = mapped_column(Text)
    search_text: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(100))
    interactions: Mapped[list["CustomerInteraction"]] = relationship(back_populates="product")

    @property
    def available(self) -> bool:
        return self.stock_quantity > 0


class Customer(Base):
    __tablename__ = "customers"
    __table_args__ = (
        CheckConstraint("budget_min >= 0 AND budget_max >= budget_min", name="customer_budget_range"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    preferred_categories: Mapped[list[str]] = mapped_column(JSON, default=list)
    preferred_brands: Mapped[list[str]] = mapped_column(JSON, default=list)
    budget_min: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    budget_max: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    source: Mapped[str] = mapped_column(String(100))
    interactions: Mapped[list["CustomerInteraction"]] = relationship(back_populates="customer")
    recommendations: Mapped[list["Recommendation"]] = relationship(back_populates="customer")


class CustomerInteraction(Base):
    __tablename__ = "customer_interactions"
    __table_args__ = (
        CheckConstraint("channel IN ('ecommerce','mobile','store')", name="interaction_channel"),
        CheckConstraint("event_type IN ('view','purchase','wishlist','cart')", name="interaction_event"),
        CheckConstraint("quantity > 0", name="interaction_quantity"),
        Index("ix_interactions_customer_time", "customer_id", "occurred_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"), index=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(20))
    channel: Mapped[str] = mapped_column(String(20), index=True)
    quantity: Mapped[int] = mapped_column(default=1)
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime())
    source: Mapped[str] = mapped_column(String(100))
    customer: Mapped[Customer] = relationship(back_populates="interactions")
    product: Mapped[Product] = relationship(back_populates="interactions")


class Recommendation(Base):
    __tablename__ = "recommendations"
    __table_args__ = (CheckConstraint("channel IN ('ecommerce','mobile','store')", name="recommendation_channel"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[str | None] = mapped_column(ForeignKey("customers.id"), index=True)
    query: Mapped[str] = mapped_column(Text)
    channel: Mapped[str] = mapped_column(String(20))
    mode: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, index=True)
    customer: Mapped[Customer | None] = relationship(back_populates="recommendations")
    items: Mapped[list["RecommendationItem"]] = relationship(back_populates="recommendation", cascade="all, delete-orphan")
    executions: Mapped[list["AgentExecution"]] = relationship(back_populates="recommendation")


class RecommendationItem(Base):
    __tablename__ = "recommendation_items"
    __table_args__ = (
        UniqueConstraint("recommendation_id", "product_id"),
        UniqueConstraint("recommendation_id", "rank"),
        CheckConstraint("rank > 0 AND score >= 0 AND score <= 1", name="item_rank_score"),
        CheckConstraint("price_snapshot >= 0", name="item_price_nonnegative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    recommendation_id: Mapped[int] = mapped_column(ForeignKey("recommendations.id"), index=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"), index=True)
    rank: Mapped[int]
    score: Mapped[float]
    price_snapshot: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    explanation: Mapped[str] = mapped_column(Text)
    recommendation: Mapped[Recommendation] = relationship(back_populates="items")
    product: Mapped[Product] = relationship()


class AgentExecution(Base):
    __tablename__ = "agent_executions"
    __table_args__ = (CheckConstraint("status IN ('running','completed','failed')", name="agent_execution_status"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    recommendation_id: Mapped[int | None] = mapped_column(ForeignKey("recommendations.id"), index=True)
    agent_name: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20))
    started_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    tool_calls: Mapped[list[dict]] = mapped_column(JSON, default=list)
    output_summary: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    recommendation: Mapped[Recommendation | None] = relationship(back_populates="executions")


class DatasetImport(Base):
    __tablename__ = "dataset_imports"

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(100))
    imported_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
    report: Mapped[dict] = mapped_column(JSON)


class RecommendationSnapshot(Base):
    """Additive table preserves full Phase 3 evidence without altering Phase 2 tables."""

    __tablename__ = "recommendation_snapshots"

    recommendation_id: Mapped[int] = mapped_column(ForeignKey("recommendations.id"), primary_key=True)
    request: Mapped[dict] = mapped_column(JSON)
    payload: Mapped[dict] = mapped_column(JSON)


class WorkflowRun(Base):
    __tablename__ = "workflow_runs"
    __table_args__ = (CheckConstraint("status IN ('running','completed','failed')", name="workflow_run_status"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    status: Mapped[str] = mapped_column(String(20), index=True)
    request: Mapped[dict] = mapped_column(JSON)
    state: Mapped[dict] = mapped_column(JSON, default=dict)
    output: Mapped[dict | None] = mapped_column(JSON)
    recommendation_id: Mapped[int | None] = mapped_column(ForeignKey("recommendations.id"), index=True)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, index=True)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    error: Mapped[str | None] = mapped_column(Text)


class WorkflowStep(Base):
    """Associate existing AgentExecution rows with a run without altering that table."""

    __tablename__ = "workflow_steps"
    __table_args__ = (UniqueConstraint("run_id", "sequence"), CheckConstraint("sequence > 0", name="workflow_step_sequence"))

    execution_id: Mapped[int] = mapped_column(ForeignKey("agent_executions.id"), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("workflow_runs.id"), index=True)
    sequence: Mapped[int]


class ToolInvocation(Base):
    __tablename__ = "tool_invocations"
    __table_args__ = (
        CheckConstraint("status IN ('running','completed','failed')", name="tool_invocation_status"),
        CheckConstraint("effect IN ('read','write','unknown')", name="tool_invocation_effect"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    tool_name: Mapped[str] = mapped_column(String(100), index=True)
    effect: Mapped[str] = mapped_column(String(8))
    status: Mapped[str] = mapped_column(String(20), index=True)
    arguments: Mapped[dict] = mapped_column(JSON)
    request_sha256: Mapped[str] = mapped_column(String(64))
    result: Mapped[dict | None] = mapped_column(JSON)
    audit: Mapped[dict | None] = mapped_column(JSON)
    error_code: Mapped[str | None] = mapped_column(String(40))
    error: Mapped[str | None] = mapped_column(Text)
    idempotency_key: Mapped[str | None] = mapped_column(String(64), unique=True)
    recommendation_id: Mapped[int | None] = mapped_column(ForeignKey("recommendations.id"), index=True)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, index=True)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime())


class OmnichannelSimulation(Base):
    __tablename__ = "omnichannel_simulations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(64), unique=True)
    request_sha256: Mapped[str] = mapped_column(String(64))
    request: Mapped[dict] = mapped_column(JSON)
    result: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, index=True)
