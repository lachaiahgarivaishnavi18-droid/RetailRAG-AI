from decimal import Decimal

import numpy as np
import pytest
from pydantic import ValidationError
from sqlalchemy import event, func, select
from sqlalchemy.orm import Session

from retailrag.content_index import ContentIndex, product_document
from retailrag.models import CustomerInteraction, Product, Recommendation, RecommendationItem, RecommendationSnapshot, utc_now
from retailrag.preferences import get_customer_profile
from retailrag.recommendation_schemas import RankingWeights, RecommendationRequest
from retailrag.recommendations import budget_compatibility, filter_by_availability, filter_by_budget, generate_recommendations, rank_recommendations


def preview(engine, **kwargs):
    with Session(engine) as session:
        return generate_recommendations(session, RecommendationRequest(**kwargs), persist=False)


def test_tfidf_cosine_and_product_documents(seeded_engine):
    with Session(seeded_engine) as session:
        products = list(session.scalars(select(Product).order_by(Product.id)))
        index = ContentIndex(products)
        scores = index.query_scores("wireless headphones")
        assert index.matrix.shape[0] == 24
        assert index.matrix.shape[1] > 24
        assert scores[0] > scores[index.positions["P014"]]
        assert index.similar_scores("P001")[0] == pytest.approx(1)
        assert np.all((scores >= 0) & (scores <= 1))
        assert not index.query_scores("qzxwunmatched").any()
        document = product_document(products[0])
        assert all(word in document for word in ["wireless", "headphones", "electronics", "soundnest", "2499", "bluetooth", "navy"])


def test_empty_catalog_and_empty_vocabulary_are_safe(engine):
    index = ContentIndex([])
    assert index.query_scores("anything").size == 0
    product = Product(id="X", name="the", description="and", category="a", brand="an", price=Decimal("0"),
                      rating=0, stock_quantity=1, features=[], attributes={}, source="test")
    # Price adds a real numeric feature; stopword-only queries still safely score zero.
    assert not ContentIndex([product]).query_scores("the and").any()
    result = preview(engine, mode="new_customer")
    assert result.items == [] and result.catalog_size == 0
    assert any("empty" in warning for warning in result.warnings)


def test_customer_profile_summarizes_real_behavior_and_declared_budget(seeded_engine):
    with Session(seeded_engine) as session:
        profile = get_customer_profile(session, "C001")
        assert profile.interaction_count == 8
        assert profile.event_counts == {"view": 3, "wishlist": 2, "cart": 1, "purchase": 2}
        assert profile.channel_counts == {"ecommerce": 3, "mobile": 3, "store": 2}
        assert profile.purchased_product_ids == ["P001", "P004"]
        assert profile.wishlist_product_ids == ["P003"]
        assert profile.viewed_product_ids == ["P001", "P002"]
        assert profile.category_affinities["Electronics"] > profile.category_affinities["Footwear"]
        assert profile.budget_max == Decimal("3000")
        assert profile.observed_purchase_median_price == Decimal("1899")
        assert profile.observed_price_basis == "current_catalog"
        assert get_customer_profile(session, "C008").cold_start
        with pytest.raises(LookupError):
            get_customer_profile(session, "MISSING")


def test_channel_affinity_uses_all_history_and_reflects_new_events(seeded_engine):
    with Session(seeded_engine) as session:
        before = get_customer_profile(session, "C001", "mobile")
        assert before.interaction_count == 8
        assert len(before.channel_counts) == 3
        assert before.product_affinities != get_customer_profile(session, "C001", "store").product_affinities
        session.add(CustomerInteraction(id="NEW", customer_id="C001", product_id="P024", event_type="purchase", channel="mobile", quantity=10, occurred_at=utc_now(), source="test"))
        session.commit()
        after = get_customer_profile(session, "C001", "mobile")
        assert after.product_affinities["P024"] == 1
        assert after.category_affinities["Accessories"] == 1
        assert after.interaction_count == 9


@pytest.mark.parametrize("values", [
    {"mode": "personalized", "customer_id": "C001"},
    {"mode": "similar", "product_id": "P001"},
    {"mode": "budget", "max_price": "1000"},
    {"mode": "category", "category": "Footwear"},
    {"mode": "brand", "brand": "SoundNest"},
    {"mode": "new_customer"},
    {"mode": "context_aware", "customer_id": "C002", "query": "running shoes under INR 3500", "channel": "mobile"},
])
def test_all_seven_recommendation_modes_are_grounded_and_deterministic(seeded_engine, values):
    result = preview(seeded_engine, **values)
    repeated = preview(seeded_engine, **values)
    assert result.items
    assert result.model_dump() == repeated.model_dump()
    assert result.engine == "deterministic_tfidf" and result.llm_used is False
    assert result.id is None
    assert sum(result.active_weights.values()) == pytest.approx(1)
    assert [i.rank for i in result.items] == list(range(1, len(result.items) + 1))
    assert [i.relevance_score for i in result.items] == sorted([i.relevance_score for i in result.items], reverse=True)
    with Session(seeded_engine) as session:
        for item in result.items:
            actual = session.get(Product, item.product.id)
            assert item.product.price == actual.price
            assert item.product.available == actual.available
            assert item.product.attributes == actual.attributes
            assert str(actual.price) in item.explanation
            assert all(0 <= score <= 1 for score in item.components.values())
            expected = sum(item.components[k] * w for k, w in result.active_weights.items())
            assert item.relevance_score == pytest.approx(expected, abs=1e-7)
        assert session.scalar(select(func.count()).select_from(Recommendation)) == 0


def test_similar_products_exclude_anchor_and_favor_related_products(seeded_engine):
    result = preview(seeded_engine, mode="similar", product_id="P001", limit=3)
    assert "P001" not in {i.product.id for i in result.items}
    assert result.items[0].product.category == "Electronics"
    assert result.items[0].similarity_score > 0
    assert result.context.category == "Electronics"
    assert result.context.category_source == "source_product"
    assert all(item.product.category == "Electronics" for item in result.items)
    limited = preview(seeded_engine, mode="similar", product_id="P001", max_price="3000", limit=5)
    assert [item.product.id for item in limited.items] == ["P003"]


def test_personal_preferences_and_purchase_exclusion(seeded_engine):
    result = preview(seeded_engine, mode="personalized", customer_id="C001", exclude_purchased=True)
    assert result.preference_basis == "customer_profile"
    assert result.items[0].product.category in ["Electronics", "Footwear"]
    assert not {i.product.id for i in result.items} & {"P001", "P004"}
    assert all(i.product.price <= Decimal("3000") for i in result.items)


def test_cold_start_and_no_interaction_rating_fallback(seeded_engine):
    result = preview(seeded_engine, mode="personalized", customer_id="C008")
    assert result.profile.cold_start and result.preference_basis == "catalog_popularity_and_rating"
    assert any("no interaction history" in warning for warning in result.warnings)
    with Session(seeded_engine) as session:
        products = list(session.scalars(select(Product).order_by(Product.id)))
    # The separate database has products but no customers/interactions.
    from retailrag.database import build_engine, initialize_database
    standalone = build_engine("sqlite:///:memory:")
    initialize_database(standalone)
    try:
        with Session(standalone) as session:
            session.merge(products[0])
            session.merge(products[1])
            session.commit()
            response = generate_recommendations(session, RecommendationRequest(mode="new_customer"), persist=False)
            assert response.preference_basis == "catalog_rating"
            assert response.items[0].product.rating >= response.items[1].product.rating
    finally:
        standalone.dispose()


def test_budget_and_availability_helpers_and_strict_filters(seeded_engine):
    with Session(seeded_engine) as session:
        products = list(session.scalars(select(Product)))
        assert all(p.price <= 1000 for p in filter_by_budget(products, maximum=Decimal("1000")))
        assert len(filter_by_availability(products)) == 21
        assert len(filter_by_availability(products, False)) == 24
    assert budget_compatibility(Decimal("2000"), None, Decimal("1000")) == 0.5
    assert budget_compatibility(Decimal("500"), Decimal("1000"), None) == 0.5
    assert budget_compatibility(Decimal("0"), None, Decimal("0")) == 1
    strict = preview(seeded_engine, mode="budget", min_price="2499", max_price="2499", category="Electronics")
    assert [item.product.id for item in strict.items] == ["P001"]
    no_match = preview(seeded_engine, mode="budget", max_price="1")
    assert no_match.items == [] and no_match.candidate_count == 0
    soft = preview(seeded_engine, mode="budget", max_price="1", strict_budget=False)
    assert soft.items and any("soft" in warning for warning in soft.warnings)
    unavailable = preview(seeded_engine, mode="brand", brand="WaveCraft", available_only=False, limit=50)
    assert any(not i.product.available for i in unavailable.items)
    assert all(i.product.available for i in preview(seeded_engine, mode="brand", brand="WaveCraft").items)


def test_query_budget_rules_and_explicit_overrides(seeded_engine):
    result = preview(seeded_engine, query="headphones under ₹2,499")
    assert result.items == []  # P001 equals the exclusive ceiling; P004 is out of stock.
    inclusive = preview(seeded_engine, query="headphones up to INR 2499")
    assert [i.product.id for i in inclusive.items] == ["P001"]
    assert inclusive.context.max_price == Decimal("2499")
    result = preview(seeded_engine, query="SoundNest headphones under 3k", max_price="7000")
    assert result.context.brand == "SoundNest"
    assert result.context.max_price == Decimal("7000")
    assert result.context.budget_sources["max_price"] == "explicit"
    assert not result.context.max_exclusive
    assert {i.product.id for i in result.items} == {"P001", "P002"}
    between = preview(seeded_engine, query="between 500 and 1000")
    assert between.items and all(500 <= i.product.price <= 1000 for i in between.items)
    assert between.context.text_query == ""
    combined = preview(seeded_engine, query="headphones under 7000 INR and below 3000 INR")
    assert combined.context.max_price == Decimal("3000")
    assert combined.context.text_query == "headphones and"
    assert all(item.product.price < Decimal("3000") for item in combined.items)


def test_oov_and_impossible_filters_are_not_relaxed(seeded_engine):
    assert preview(seeded_engine, query="qzxwunmatched").items == []
    assert preview(seeded_engine, query="the and").items == []
    assert preview(seeded_engine, mode="category", category="MissingCategory").items == []
    assert preview(seeded_engine, mode="brand", brand="SoundNest", category="Home").items == []


def test_custom_weights_change_ranking_and_normalize_active_signals(seeded_engine):
    weights = {key: 0 for key in RankingWeights.model_fields}
    weights["text_relevance"] = 1
    result = preview(seeded_engine, query="wireless headphones", weights=weights)
    assert result.active_weights == {"text_relevance": 1}
    assert all(i.relevance_score == i.similarity_score for i in result.items)
    weights["text_relevance"], weights["availability"] = 0, 1
    stock = preview(seeded_engine, mode="new_customer", available_only=False, limit=50, weights=weights)
    assert all(i.relevance_score == float(i.product.available) for i in stock.items)
    assert rank_recommendations({"availability": 1, "text_relevance": 0.2}, {"availability": 0.25, "text_relevance": 0.75}) == pytest.approx(0.4)


def test_fresh_catalog_vectors_and_stock_on_every_request(seeded_engine):
    before = preview(seeded_engine, query="wireless headphones")
    assert "P001" in {i.product.id for i in before.items}
    with Session(seeded_engine) as session:
        session.get(Product, "P001").stock_quantity = 0
        session.get(Product, "P002").name = "Quantumwidget Headphones"
        session.commit()
    assert "P001" not in {i.product.id for i in preview(seeded_engine, query="wireless headphones").items}
    assert preview(seeded_engine, query="quantumwidget").items[0].product.id == "P002"


def test_atomic_persistence_rolls_back_on_snapshot_error(seeded_engine):
    def fail(*args):
        raise RuntimeError("injected snapshot failure")
    event.listen(RecommendationSnapshot, "before_insert", fail)
    try:
        with Session(seeded_engine) as session:
            with pytest.raises(RuntimeError, match="injected"):
                generate_recommendations(session, RecommendationRequest(mode="new_customer"))
            for model in [Recommendation, RecommendationItem, RecommendationSnapshot]:
                assert session.scalar(select(func.count()).select_from(model)) == 0
    finally:
        event.remove(RecommendationSnapshot, "before_insert", fail)


@pytest.mark.parametrize("values", [
    {"mode": "personalized"}, {"mode": "similar"}, {"mode": "budget"},
    {"mode": "category"}, {"mode": "brand"}, {"mode": "context_aware", "query": "   "},
    {"mode": "new_customer", "customer_id": "C001"}, {"mode": "new_customer", "product_id": "P001"},
    {"mode": "budget", "max_price": "NaN"}, {"mode": "budget", "min_price": "-1"},
    {"mode": "budget", "min_price": "2", "max_price": "1"},
    {"mode": "new_customer", "limit": 51}, {"mode": "new_customer", "weights": {"text_relevance": float("inf")}},
])
def test_invalid_requests_fail_validation(values):
    with pytest.raises(ValidationError):
        RecommendationRequest(**values)


def test_zero_weights_and_inactive_weights_are_rejected(seeded_engine):
    zeros = {key: 0 for key in RankingWeights.model_fields}
    with pytest.raises(ValidationError):
        RankingWeights(**zeros)
    with pytest.raises(ValueError, match="supplied context"):
        preview(seeded_engine, mode="new_customer", weights={**zeros, "text_relevance": 1})
