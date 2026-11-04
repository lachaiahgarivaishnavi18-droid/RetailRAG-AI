from decimal import Decimal

import pytest
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from retailrag.database import build_engine, initialize_database
from retailrag.models import AgentExecution, CustomerInteraction, Product, Recommendation, RecommendationItem, utc_now


def test_database_survives_reinitialization_and_reconnection(seeded_engine):
    database_url = str(seeded_engine.url)
    initialize_database(seeded_engine)
    seeded_engine.dispose()
    second = build_engine(database_url)
    try:
        with Session(second) as session:
            assert session.get(Product, "P001").price == Decimal("2499.00")
        assert set(inspect(second).get_table_names()) == {
            "products", "customers", "customer_interactions", "recommendations",
            "recommendation_items", "agent_executions", "dataset_imports", "recommendation_snapshots", "workflow_runs", "workflow_steps", "tool_invocations", "omnichannel_simulations",
        }
        assert "ix_interactions_customer_time" in {i["name"] for i in inspect(second).get_indexes("customer_interactions")}
    finally:
        second.dispose()


def test_foreign_keys_are_enabled_and_enforced(engine):
    with engine.connect() as connection:
        assert connection.scalar(text("PRAGMA foreign_keys")) == 1
    with Session(engine) as session:
        session.add(CustomerInteraction(id="BAD", customer_id="MISSING", product_id="MISSING", event_type="view",
                                        channel="mobile", quantity=1, occurred_at=utc_now(), source="test"))
        with pytest.raises(IntegrityError):
            session.commit()


def test_database_check_constraints(seeded_engine):
    with Session(seeded_engine) as session:
        session.get(Product, "P001").stock_quantity = -1
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
        assert session.get(Product, "P001").stock_quantity == 35


def test_reserved_recommendation_relationships_and_unique_items(seeded_engine):
    with Session(seeded_engine) as session:
        rec = Recommendation(customer_id="C001", query="test fixture only", channel="mobile", mode="test")
        rec.items.append(RecommendationItem(product_id="P001", rank=1, score=0.8, price_snapshot=Decimal("2499"), explanation="test fixture"))
        rec.executions.append(AgentExecution(agent_name="test_fixture", status="completed", tool_calls=[], output_summary="schema test"))
        session.add(rec)
        session.commit()
        assert rec.customer.id == "C001"
        assert rec.items[0].product.id == "P001"
        assert rec.executions[0].recommendation.id == rec.id
        rec.items.append(RecommendationItem(product_id="P001", rank=2, score=0.5, price_snapshot=Decimal("2499"), explanation="duplicate"))
        with pytest.raises(IntegrityError):
            session.commit()
