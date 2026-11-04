import pytest
from sqlalchemy import text


def test_status_and_catalog_return_database_facts(client):
    status = client.get("/database/status").json()
    assert status["counts"]["products"] == 24
    assert status["counts"]["customers"] == 8
    assert status["counts"]["customer_interactions"] == 56
    product = client.get("/products/P001").json()
    assert product["price"] == "2499.00"
    assert product["available"] is True
    assert product["source"] == "synthetic_demo"
    assert "search_text" not in product
    assert client.get("/products/P004").json()["available"] is False


def test_search_filters_sort_and_pagination(client):
    result = client.get("/products/search", params={"q": "WIRELESS headphones", "max_price": "3000", "available": True}).json()
    assert [row["id"] for row in result["items"]] == ["P001"]
    assert client.get("/products/search", params={"q": "USB-C"}).json()["total"] == 1
    result = client.get("/products", params={"category": "footwear", "brand": "StrideWay", "sort": "price_asc", "limit": 1}).json()
    assert result["total"] == 2
    assert result["items"][0]["id"] == "P007"
    result = client.get("/products", params={"category": "footwear", "brand": "StrideWay", "sort": "price_asc", "limit": 1, "offset": 1}).json()
    assert result["items"][0]["id"] == "P005"
    assert client.get("/products", params={"available": False}).json()["total"] == 3
    assert client.get("/products", params={"q": "no_such_product"}).json()["items"] == []


@pytest.mark.parametrize("path,params", [
    ("/products", {"limit": 101}), ("/products", {"offset": -1}),
    ("/products", {"sort": "unknown"}), ("/products", {"max_price": -1}),
    ("/products", {"min_price": 500, "max_price": 100}),
    ("/products", {"max_price": "NaN"}), ("/products", {"max_price": "1.234"}),
    ("/customers/C001/history", {"channel": "real"}),
])
def test_invalid_filters(client, path, params):
    assert client.get(path, params=params).status_code == 422


@pytest.mark.parametrize("path", ["/products/missing", "/customers/missing", "/customers/missing/history"])
def test_missing_records(client, path):
    assert client.get(path).status_code == 404


def test_customers_and_cross_channel_history(client):
    assert client.get("/customers").json()["total"] == 8
    assert client.get("/customers/C001").json()["preferred_brands"] == ["SoundNest"]
    result = client.get("/customers/C001/history").json()
    assert result["total"] == 8
    assert {row["channel"] for row in result["items"]} == {"ecommerce", "mobile", "store"}
    assert result["items"][0]["occurred_at"].endswith("Z")
    result = client.get("/customers/C001/history", params={"channel": "mobile", "limit": 1}).json()
    assert result["total"] == 3
    assert len(result["items"]) == 1
    assert result["items"][0]["channel"] == "mobile"
    assert client.get("/customers/C008/history").json()["items"] == []


def test_simulated_interaction_persists_and_rejects_duplicates(client):
    values = {"id": "SIM001", "customer_id": "C008", "product_id": "P001", "event_type": "view",
              "channel": "store", "occurred_at": "2026-11-04T12:00:00+05:30"}
    response = client.post("/interactions", json=values)
    assert response.status_code == 201
    assert response.json()["source"] == "synthetic_simulation"
    assert response.json()["occurred_at"] == "2026-11-04T06:30:00Z"
    assert client.get("/customers/C008/history").json()["items"][0]["id"] == "SIM001"
    assert client.post("/interactions", json=values).status_code == 409
    assert client.get("/database/status").json()["counts"]["customer_interactions"] == 57
    assert client.post("/interactions", json={**values, "id": "BAD", "customer_id": "missing"}).status_code == 404
    assert client.post("/interactions", json={**values, "quantity": 0}).status_code == 422
    assert client.post("/interactions", json={**values, "source": "pretend_real"}).status_code == 422


def test_database_errors_do_not_expose_connection_details(client):
    with client.app.state.engine.begin() as connection:
        connection.execute(text("DROP TABLE dataset_imports"))
    response = client.get("/database/status")
    assert response.status_code == 503
    assert response.json() == {"detail": "Database operation failed; check the connection and schema"}
    assert client.get("/health").status_code == 200
