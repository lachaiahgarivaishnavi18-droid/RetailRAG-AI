from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from retailrag.models import Product, Recommendation, RecommendationItem, RecommendationSnapshot


def test_generation_persistence_history_and_frozen_evidence(client):
    values = {"mode": "context_aware", "customer_id": "C001", "query": "wireless headphones under INR 3000", "channel": "mobile"}
    response = client.post("/recommendations", json=values)
    assert response.status_code == 201, response.text
    result = response.json()
    assert result["id"] > 0 and result["created_at"].endswith("Z")
    assert result["engine"] == "deterministic_tfidf" and result["llm_used"] is False
    assert result["items"][0]["product"]["id"] == "P001"
    assert client.get(f"/recommendations/{result['id']}").json() == result
    with Session(client.app.state.engine) as session:
        product = session.get(Product, "P001")
        product.price, product.stock_quantity = Decimal("9999"), 0
        session.commit()
        assert session.scalar(select(func.count()).select_from(Recommendation)) == 1
        assert session.scalar(select(func.count()).select_from(RecommendationSnapshot)) == 1
        item = session.scalar(select(RecommendationItem).where(RecommendationItem.product_id == "P001"))
        assert item.price_snapshot == Decimal("2499")
    assert client.get(f"/recommendations/{result['id']}").json() == result
    assert client.get("/products/P001").json()["price"] == "9999.00"
    history = client.get("/recommendations", params={"customer_id": "C001", "channel": "mobile", "mode": "context_aware"}).json()
    assert history["total"] == 1 and history["items"][0]["id"] == result["id"]
    assert history["items"][0]["item_count"] == len(result["items"])
    assert client.get("/recommendations", params={"channel": "store"}).json()["total"] == 0
    assert client.get("/recommendations", params={"offset": 1}).json()["items"] == []
    assert client.get("/database/status").json()["counts"]["recommendations"] == 1


def test_empty_recommendations_are_saved_without_fake_items(client):
    response = client.post("/recommendations", json={"mode": "budget", "max_price": "0"})
    assert response.status_code == 201
    result = response.json()
    assert result["items"] == [] and result["id"] > 0
    assert client.get(f"/recommendations/{result['id']}").json() == result
    assert client.get("/recommendations").json()["items"][0]["item_count"] == 0


@pytest.mark.parametrize("values,status", [
    ({"mode": "personalized", "customer_id": "MISSING"}, 404),
    ({"mode": "similar", "product_id": "MISSING"}, 404),
    ({"mode": "similar"}, 422), ({"mode": "category"}, 422),
    ({"mode": "budget", "max_price": -1}, 422),
    ({"mode": "budget", "query": "something"}, 422),
    ({"mode": "context_aware", "query": "headphones without SoundNest"}, 422),
    ({"mode": "context_aware", "query": "headphones under $100"}, 422),
    ({"mode": "context_aware", "query": "between 5000 and 1000"}, 422),
    ({"mode": "context_aware", "query": "under INR 999999999999"}, 422),
    ({"mode": "new_customer", "invented_tool_result": "ok"}, 422),
])
def test_errors_do_not_write_recommendations(client, values, status):
    response = client.post("/recommendations", json=values)
    assert response.status_code == status, response.text
    assert client.get("/recommendations").json()["total"] == 0


def test_customer_preferences_endpoint(client):
    profile = client.get("/customers/C001/preferences", params={"channel": "store"})
    assert profile.status_code == 200
    assert profile.json()["channel"] == "store"
    assert profile.json()["interaction_count"] == 8
    assert profile.json()["observed_price_basis"] == "current_catalog"
    assert client.get("/customers/missing/preferences").status_code == 404
    assert client.get("/customers/C001/preferences", params={"channel": "real"}).status_code == 422
    assert client.get("/recommendations/9999").status_code == 404
    assert client.get("/recommendations/not-an-id").status_code == 422
    assert client.get("/recommendations", params={"limit": 101}).status_code == 422


def test_legacy_recommendation_records_remain_accessible(client):
    with Session(client.app.state.engine) as session:
        record = Recommendation(customer_id="C001", query="legacy", channel="store", mode="legacy")
        record.items = [RecommendationItem(product_id="P001", rank=1, score=0.5, price_snapshot=Decimal("1999"), explanation="older record")]
        session.add(record)
        session.commit()
        record_id = record.id
    response = client.get(f"/recommendations/{record_id}").json()
    assert response["engine"] == "legacy_unknown"
    assert response["llm_used"] is None
    assert response["items"][0]["price_snapshot"] == "1999.00"
    assert "current catalog" in response["message"]


def test_query_detects_labels_and_reports_ambiguous_filters(client):
    result = client.post("/recommendations", json={"query": "SoundNest Electronics under 7000"}).json()
    assert result["context"]["category"] == "Electronics"
    assert result["context"]["brand"] == "SoundNest"
    assert all(item["product"]["brand"] == "SoundNest" for item in result["items"])
    ambiguous = client.post("/recommendations", json={"query": "SoundNest or WaveCraft headphones"}).json()
    assert ambiguous["context"]["brand"] is None
    assert any("Multiple brand" in warning for warning in ambiguous["warnings"])
