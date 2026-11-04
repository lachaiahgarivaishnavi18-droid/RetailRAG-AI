from fastapi.testclient import TestClient

from retailrag.api import create_app
from retailrag.config import Settings


def sample():
    return {"id": "USER001", "name": "Sample Local Headphones", "description": "Wired local catalog headphones",
            "category": "Electronics", "brand": "Local Demo", "price": "1234.50", "stock_quantity": 4,
            "rating": 4.2, "features": ["wired"], "attributes": {"connector": "USB-C"}}


def test_phase8_catalog_create_update_search_and_safe_delete(client):
    created = client.post("/products", json=sample())
    assert created.status_code == 201 and created.json()["source"] == "user_catalog"
    assert client.post("/products", json=sample()).status_code == 409
    assert client.get("/products/search", params={"q": "local headphones"}).json()["total"] == 1
    changed = {**sample(), "price": "999.00", "stock_quantity": 0, "name": "Updated Local Headphones"}
    updated = client.put("/products/USER001", json=changed)
    assert updated.status_code == 200 and updated.json()["price"] == "999.00" and not updated.json()["available"]
    assert client.put("/products/USER001", json={**changed, "id": "WRONG"}).status_code == 422
    assert client.delete("/products/P001").status_code == 409
    assert client.delete("/products/USER001").status_code == 204
    assert client.get("/products/USER001").status_code == 404
    assert client.put("/products/USER001", json=changed).status_code == 404
    assert client.post("/products", json={**sample(), "price": "-1"}).status_code == 422


def test_phase8_catalog_edit_marks_vectors_stale_and_preserves_saved_prices(client):
    client.post("/rag/ingest", json={})
    rec = client.post("/recommendations", json={"query": "wireless headphones under INR 3000"}).json()
    original = client.get("/products/P001").json()
    editable = {key: value for key, value in original.items() if key not in {"available", "source"}}
    editable["price"] = "2999.00"
    assert client.put("/products/P001", json=editable).status_code == 200
    assert "P001" in client.get("/rag/status").json()["stale_product_ids"]
    assert client.get(f"/recommendations/{rec['id']}").json() == rec
    assert client.post("/rag/ingest", json={"product_ids": ["P001"]}).status_code == 200
    assert client.get("/rag/status").json()["status"] == "ready"


def test_phase8_all_required_endpoints_documented_and_configuration_redacts_credentials(client):
    paths = client.get("/openapi.json").json()["paths"]
    required = ["/health", "/products", "/products/search", "/products/{product_id}", "/customers", "/customers/{customer_id}",
                "/customers/{customer_id}/history", "/recommendations", "/recommendations/{recommendation_id}",
                "/rag/search", "/rag/ingest", "/rag/status", "/agents/run", "/agents/status",
                "/analytics/overview", "/analytics/recommendations", "/analytics/channels"]
    assert all(path in paths for path in required)
    assert client.get("/ready").json()["database"] == "ok"
    settings = Settings(_env_file=None, database_url="sqlite:///:memory:", OPENAI_API_KEY="secret-not-for-output")
    with TestClient(create_app(settings)) as other:
        response = other.get("/settings")
        assert response.json()["llm_credentials_configured"] is True
        assert "secret-not-for-output" not in response.text
