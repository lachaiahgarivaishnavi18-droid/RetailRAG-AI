from decimal import Decimal
from unittest.mock import patch

from sqlalchemy.orm import Session

from retailrag.models import Product
from retailrag.workflow_tools import WorkflowTools


def test_request_schema_validation_does_not_create_fake_runs(client):
    for values in [
        {}, {"query": " "}, {"query": "headphones", "retrieval_strategy": "fake"},
        {"query": "headphones", "limit": 21}, {"query": "headphones", "max_price": "-1"},
        {"mode": "personalized"}, {"mode": "similar"},
        {"mode": "similar", "product_id": "P001", "retrieval_strategy": "rag"},
        {"query": "headphones", "retrieval_strategy": "rag", "strict_budget": False},
        {"query": "headphones", "invented_tool_results": {"price": 1}},
    ]:
        assert client.post("/agents/run", json=values).status_code == 422
    assert client.get("/agents/status").json()["total"] == 0
    assert client.get("/agents/runs/missing").status_code == 404
    assert client.get("/agents/status", params={"status": "fake"}).status_code == 422
    assert client.get("/agents/status", params={"limit": 101}).status_code == 422


def test_status_history_and_frozen_workflow_evidence(client):
    run = client.post("/agents/run", json={"query": "wireless headphones under INR 3000", "retrieval_strategy": "content"}).json()
    failed = client.post("/agents/run", json={"query": "headphones", "customer_id": "MISSING", "retrieval_strategy": "content"}).json()
    status = client.get("/agents/status").json()
    assert status["total"] == 2 and status["counts"] == {"completed": 1, "failed": 1}
    assert status["items"][0]["run_id"] == failed["run_id"]
    assert client.get("/agents/status", params={"status": "completed"}).json()["total"] == 1
    assert client.get("/agents/status", params={"offset": 2}).json()["items"] == []
    with Session(client.app.state.engine) as session:
        session.get(Product, "P001").price = Decimal("9999")
        session.commit()
    assert client.get(f"/agents/runs/{run['run_id']}").json() == run
    assert client.get(f"/recommendations/{run['recommendation_id']}").json() == run["output"]
    assert client.get("/products/P001").json()["price"] == "9999.00"


def test_tool_input_output_validation_and_allowlist(client):
    tools = WorkflowTools(client.app.state.engine, client.app.state.rag_store)
    try:
        tools.call("invented_tool", {})
        assert False, "Unknown tool must fail"
    except ValueError:
        pass
    try:
        tools.call("get_customer_profile", {"customer_id": "C001", "injected_field": 1})
        assert False, "Unknown input must fail"
    except ValueError:
        pass
    assert tools.calls[-1]["status"] == "failed"
    assert tools.calls[-1]["output_sha256"] is None
    with patch.object(WorkflowTools, "catalog_context", return_value={"products": "fabricated", "interactions": 0}):
        invalid = WorkflowTools(client.app.state.engine, client.app.state.rag_store)
        try:
            invalid.call("get_catalog_context", {})
            assert False, "Invalid output must fail"
        except ValueError:
            pass
    assert invalid.calls[-1]["status"] == "failed"
    assert invalid.calls[-1]["error"] == "Tool input or output failed schema validation"


def test_save_transaction_rechecks_facts_after_validation_agent(client):
    original = WorkflowTools.save
    def change_price_then_save(self, values):
        with Session(self.engine) as session:
            session.get(Product, "P001").price = Decimal("9999")
            session.commit()
        return original(self, values)
    with patch.object(WorkflowTools, "save", change_price_then_save):
        run = client.post("/agents/run", json={"query": "wireless headphones under INR 3000", "retrieval_strategy": "content"}).json()
    assert run["status"] == "failed" and run["recommendation_id"] is None
    assert next(step for step in run["steps"] if step["agent"] == "validation")["status"] == "completed"
    assert run["steps"][-1]["status"] == "failed"
    assert client.get("/recommendations").json()["total"] == 0


def test_custom_weights_soft_budget_and_purchase_exclusion(client):
    weights = {"text_relevance": 0, "customer_preference": 0, "category_match": 0, "brand_match": 0, "budget_compatibility": 0, "availability": 1}
    run = client.post("/agents/run", json={"mode": "brand", "brand": "WaveCraft", "available_only": False, "weights": weights}).json()
    assert run["status"] == "completed", run
    assert run["output"]["active_weights"] == {"availability": 1}
    assert all(item["relevance_score"] == float(item["product"]["available"]) for item in run["output"]["items"])
    assert any(not item["product"]["available"] for item in run["output"]["items"])
    soft = client.post("/agents/run", json={"mode": "budget", "max_price": "1", "strict_budget": False}).json()
    assert soft["status"] == "completed" and soft["output"]["items"]
    assert any("soft" in warning for warning in soft["output"]["warnings"])
    excluded = client.post("/agents/run", json={"query": "wireless headphones under INR 3000", "customer_id": "C001", "exclude_purchased": True, "retrieval_strategy": "content"}).json()
    assert excluded["status"] == "completed"
    assert "P001" not in excluded["output"]["references"]
