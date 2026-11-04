from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from retailrag.api import create_app
from retailrag.config import Settings
from retailrag.models import Product


def test_rag_endpoint_lifecycle_and_filtering(client):
    initial = client.get("/rag/status").json()
    assert initial["status"] == "not_ingested" and initial["catalog_products"] == 24
    empty = client.post("/rag/search", json={"query": "headphones"})
    assert empty.status_code == 200 and empty.json()["items"] == []
    assert any("not been ingested" in message for message in empty.json()["warnings"])
    ingested = client.post("/rag/ingest", json={})
    assert ingested.status_code == 200, ingested.text
    assert ingested.json()["products"] == 24 and ingested.json()["chunks"] == 24
    generation = ingested.json()["generation"]
    repeated = client.post("/rag/ingest", json={}).json()
    assert repeated["generation"] == generation and repeated["unchanged"] == 24
    response = client.post("/rag/search", json={"query": "wireless headphones under INR 3000", "brand": "SoundNest", "customer_id": "C001", "channel": "mobile"})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["references"] == ["P001"]
    assert result["items"][0]["product"]["price"] == "2499.00"
    assert result["items"][0]["metadata"]["price_cents"] == 249900
    assert result["profile"]["interaction_count"] == 8
    assert result["generation"] == "deterministic_fallback" and not result["llm_used"]
    assert client.get("/recommendations").json()["total"] == 0
    assert client.post("/rag/ingest", json={"product_ids": ["MISSING"]}).status_code == 404
    assert client.get("/rag/status").json()["generation"] == generation
    assert client.delete("/rag/products/P001").status_code == 200
    assert client.delete("/rag/products/P001").status_code == 404
    assert client.get("/products/P001").status_code == 200
    assert "P001" not in client.post("/rag/search", json={"query": "wireless headphones"}).json()["references"]
    assert client.post("/rag/ingest", json={"product_ids": ["P001"]}).json()["added"] == 1
    assert client.get("/rag/status").json()["status"] == "ready"


def test_rag_invalid_inputs_are_rejected_without_index_writes(client):
    for values in [
        {"query": " "}, {"query": "headphones", "limit": 21},
        {"query": "headphones", "min_price": "3000", "max_price": "1000"},
        {"query": "headphones", "max_price": "-1"},
        {"query": "headphones", "min_similarity": 1.1},
        {"query": "headphones", "product_ids": []},
        {"query": "headphones", "channel": "real_integration"},
        {"query": "headphones", "fabricated_evidence": "in stock"},
        {"query": "headphones without SoundNest"}, {"query": "headphones under USD 20"},
    ]:
        assert client.post("/rag/search", json=values).status_code == 422
    assert client.post("/rag/search", json={"query": "headphones", "customer_id": "MISSING"}).status_code == 404
    assert client.post("/rag/ingest", json={"product_ids": []}).status_code == 422
    assert client.post("/rag/ingest", json={"drop_catalog": True}).status_code == 422
    assert client.get("/rag/status").json()["status"] == "not_ingested"


def test_empty_catalog_ingestion_and_delete_last_indexed_product(client):
    # Partial ingestion permits a one-product index without deleting catalog records.
    result = client.post("/rag/ingest", json={"product_ids": ["P001"]})
    assert result.status_code == 200 and result.json()["products"] == 1
    assert client.delete("/rag/products/P001").json()["products"] == 0
    assert client.get("/rag/status").json()["indexed_chunks"] == 0
    assert client.post("/rag/search", json={"query": "headphones"}).json()["items"] == []
    assert client.get("/products").json()["total"] == 24


def test_long_document_chunks_are_deduplicated_to_product_results(client):
    with Session(client.app.state.engine) as session:
        session.get(Product, "P001").description = "wireless headphones bluetooth listening " * 150
        session.commit()
    report = client.post("/rag/ingest", json={}).json()
    assert report["chunks"] > 24
    response = client.post("/rag/search", json={"query": "wireless headphones", "product_ids": ["P001"]}).json()
    assert response["references"] == ["P001"]
    assert len(response["items"]) == 1


def test_corrupt_manifest_and_unwritable_index_do_not_break_existing_api(client, tmp_path):
    store = client.app.state.rag_store
    client.get("/rag/status")
    store.manifest.write_text("not valid json", encoding="utf-8")
    assert client.get("/rag/status").status_code == 503
    assert client.post("/rag/search", json={"query": "headphones"}).status_code == 503
    assert client.post("/rag/ingest", json={}).status_code == 503
    assert client.get("/health").status_code == 200
    assert client.get("/products").json()["total"] == 24
    recovered = client.post("/rag/ingest", json={"force": True})
    assert recovered.status_code == 200 and recovered.json()["products"] == 24
    assert client.get("/rag/status").json()["status"] == "ready"
    store.manifest.write_text('{"products": []}', encoding="utf-8")
    assert client.post("/rag/ingest", json={"force": True}).status_code == 200
    path = tmp_path / "file-not-directory"
    path.write_text("existing file", encoding="utf-8")
    settings = Settings(_env_file=None, database_url=str(client.app.state.engine.url), rag_directory=path)
    with TestClient(create_app(settings)) as other:
        assert other.get("/health").status_code == 200
        assert other.get("/rag/status").status_code == 503
        assert other.get("/products").json()["total"] == 24
