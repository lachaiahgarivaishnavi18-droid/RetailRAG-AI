from decimal import Decimal

from sqlalchemy import event, func, select
from sqlalchemy.orm import Session

from retailrag.models import CustomerInteraction, OmnichannelSimulation, Product, Recommendation, RecommendationSnapshot


def journey():
    return {"customer_id": "C008", "query": "wireless headphones under INR 3000", "idempotency_key": "journey-test-key-001",
            "events": [{"product_id": "P001", "event_type": "view", "channel": "ecommerce"},
                       {"product_id": "P005", "event_type": "wishlist", "channel": "mobile"},
                       {"product_id": "P013", "event_type": "purchase", "channel": "store", "quantity": 2}]}


def test_phase7_analytics_derive_actual_catalog_and_interaction_counts(client):
    overview = client.get("/analytics/overview").json()
    assert overview["totals"]["products"] == 24
    assert overview["totals"]["customers"] == 8
    assert overview["totals"]["interactions"] == 56 and overview["totals"]["recommendations"] == 0
    assert overview["inventory"] == {"available": 21, "unavailable": 3}
    assert sum(row["interactions"] for row in overview["channel_activity"]) == 56
    assert overview["provenance"] == [{"source": "synthetic_demo", "count": 56}]
    channels = client.get("/analytics/channels").json()
    assert len(channels["channels"]) == 3 and channels["cross_channel_customers"] == 7
    assert sum(row["purchase_events"] for row in channels["channels"]) == 14
    assert sum(row["units_in_purchase_events"] for row in channels["channels"]) == 21
    recommendations = client.get("/analytics/recommendations").json()
    assert recommendations["total_runs"] == 0 and recommendations["average_score"] == 0
    assert recommendations["active_customers"] == 7 and "not measured" in recommendations["measurement_notes"]


def test_phase7_simulation_shares_customer_history_across_three_channels_and_is_idempotent(client):
    response = client.post("/omnichannel/simulations", json=journey())
    assert response.status_code == 201, response.text
    result = response.json()
    assert len(result["events"]) == 3 and result["profile_before"]["cold_start"]
    assert {row["source"] for row in result["events"]} == {"synthetic_omnichannel"}
    assert set(result["profiles_after"]) == {"ecommerce", "mobile", "store"}
    assert all(profile["interaction_count"] == 3 and profile["customer_id"] == "C008" for profile in result["profiles_after"].values())
    assert result["profiles_after"]["mobile"]["category_affinities"] != result["profiles_after"]["store"]["category_affinities"]
    assert len({rec["id"] for rec in result["recommendations"].values()}) == 3
    assert all(rec["channel"] == channel and rec["customer_id"] == "C008" for channel, rec in result["recommendations"].items())
    assert all(Decimal(item["product"]["price"]) < 3000 and item["product"]["available"] for rec in result["recommendations"].values() for item in rec["items"])
    replay = client.post("/omnichannel/simulations", json=journey())
    assert replay.status_code == 200 and replay.json()["replayed"]
    assert replay.json()["simulation_id"] == result["simulation_id"]
    assert client.get("/omnichannel/simulations").json()["total"] == 1
    assert client.get(f"/omnichannel/simulations/{result['simulation_id']}").json() == result
    assert client.get("/customers/C008/history").json()["total"] == 3
    assert client.get("/recommendations").json()["total"] == 3
    context = client.get("/omnichannel/customers/C008/context").json()
    assert all(profile["interaction_count"] == 3 for profile in context["profiles"].values())
    overview = client.get("/analytics/overview").json()
    assert overview["totals"]["interactions"] == 59 and overview["totals"]["recommendations"] == 3
    assert client.get("/analytics/channels").json()["cross_channel_customers"] == 8
    assert client.get("/analytics/recommendations").json()["total_runs"] == 3
    assert client.post("/omnichannel/simulations", json={**journey(), "query": "different query"}).status_code == 409
    assert client.get("/products/P013").json()["stock_quantity"] == 60


def test_phase7_date_filters_empty_analytics_and_missing_records(client):
    for endpoint in ("overview", "recommendations", "channels"):
        assert client.get(f"/analytics/{endpoint}", params={"date_from": "2026-11-05", "date_to": "2026-10-01"}).status_code == 422
        assert client.get(f"/analytics/{endpoint}", params={"date_from": "not-date"}).status_code == 422
    future = client.get("/analytics/overview", params={"date_from": "2099-01-01"}).json()
    assert future["totals"]["products"] == 24 and future["totals"]["interactions"] == 0
    assert future["popular_products"] == []
    october = client.get("/analytics/overview", params={"date_from": "2026-10-01", "date_to": "2026-10-31"}).json()
    assert october["totals"]["interactions"] == 56
    assert client.get("/omnichannel/simulations/missing").status_code == 404
    assert client.get("/omnichannel/customers/missing/context").status_code == 404


def test_phase7_invalid_references_and_shapes_do_not_write_events(client):
    for values, status in [({**journey(), "customer_id": "MISSING"}, 404),
                           ({**journey(), "events": [{"product_id": "MISSING", "event_type": "view", "channel": "mobile"}]}, 404),
                           ({**journey(), "events": []}, 422), ({**journey(), "events": [{"product_id": "P001", "event_type": "view", "channel": "real_store"}]}, 422),
                           ({**journey(), "query": "headphones without SoundNest"}, 422)]:
        assert client.post("/omnichannel/simulations", json=values).status_code == status
    assert client.get("/omnichannel/simulations").json()["total"] == 0
    assert client.get("/database/status").json()["counts"]["customer_interactions"] == 56
    assert client.get("/recommendations").json()["total"] == 0


def test_phase7_recommendation_failure_rolls_back_entire_journey(client):
    def fail(*args):
        raise RuntimeError("injected simulation snapshot failure")
    event.listen(RecommendationSnapshot, "before_insert", fail)
    try:
        response = client.post("/omnichannel/simulations", json=journey())
    finally:
        event.remove(RecommendationSnapshot, "before_insert", fail)
    assert response.status_code == 503
    with Session(client.app.state.engine) as session:
        assert session.scalar(select(func.count()).select_from(CustomerInteraction)) == 56
        assert session.scalar(select(func.count()).select_from(Recommendation)) == 0
        assert session.scalar(select(func.count()).select_from(OmnichannelSimulation)) == 0
