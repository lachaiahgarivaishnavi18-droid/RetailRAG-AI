import json
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Event
from unittest.mock import patch

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.orm import Session

from retailrag.models import Product, Recommendation, RecommendationItem, RecommendationSnapshot, ToolInvocation
from retailrag.retail_tools import RetailTools
from retailrag.tool_registry import result_digest

TOOL_NAMES = {"search_products", "get_product_details", "get_customer_profile", "get_customer_history", "search_similar_products",
              "retrieve_product_documents", "filter_by_budget", "check_product_availability", "rank_recommendations", "save_recommendation", "get_recommendation_history"}


def execute(client, name, arguments):
    return client.post(f"/tools/{name}/execute", json={"arguments": arguments})


def test_public_tool_catalog_has_all_eleven_strict_id_based_contracts(client):
    catalog = client.get("/tools").json()
    assert catalog["total"] == 11 and {item["name"] for item in catalog["items"]} == TOOL_NAMES
    assert [item["name"] for item in catalog["items"] if item["effect"] == "write"] == ["save_recommendation"]
    for item in catalog["items"]:
        assert item["input_schema"]["additionalProperties"] is False
        assert item["output_schema"]
        assert client.get(f"/tools/{item['name']}").json() == item
    assert client.get("/tools/not_registered").status_code == 404
    assert client.get("/tools/invocations").json()["total"] == 0


@pytest.mark.parametrize("name,args", [
    ("search_products", {"query": "wireless", "max_price": "3000"}),
    ("get_product_details", {"product_id": "P001"}),
    ("get_customer_profile", {"customer_id": "C001", "channel": "mobile"}),
    ("get_customer_history", {"customer_id": "C001", "channel": "mobile"}),
    ("search_similar_products", {"product_id": "P001", "max_price": "3000"}),
    ("filter_by_budget", {"product_ids": ["P001", "P002", "P003"], "max_price": "3000"}),
    ("check_product_availability", {"product_ids": ["P001", "P004"]}),
    ("rank_recommendations", {"request": {"query": "wireless headphones under INR 3000"}}),
    ("get_recommendation_history", {"customer_id": "C001"}),
])
def test_read_tools_execute_and_persist_verifiable_results_without_recommendation_writes(client, name, args):
    response = execute(client, name, args)
    assert response.status_code == 200, response.text
    call = response.json()
    assert call["status"] == "completed" and call["effect"] == "read"
    assert call["recommendation_id"] is None
    assert call["audit"]["status"] == "completed" and call["audit"]["duration_ms"] >= 0
    assert call["audit"]["output_sha256"] == result_digest(call["result"])
    assert client.get(f"/tools/invocations/{call['call_id']}").json() == call
    assert client.get("/recommendations").json()["total"] == 0
    assert client.get("/agents/status").json()["total"] == 0


def test_read_tool_facts_filters_profiles_history_and_similarity(client):
    details = execute(client, "get_product_details", {"product_id": "P001"}).json()["result"]["product"]
    assert details["price"] == "2499.00" and details["available"] is True
    assert execute(client, "get_product_details", {"product_id": "P004"}).json()["result"]["product"]["available"] is False
    search = execute(client, "search_products", {"query": "headphones", "brand": "SoundNest", "max_price": "3000"}).json()["result"]
    assert [item["id"] for item in search["items"]] == ["P001"]
    similar = execute(client, "search_similar_products", {"product_id": "P001", "max_price": "3000"}).json()["result"]
    assert [item["product"]["id"] for item in similar["items"]] == ["P003"]
    history = execute(client, "get_customer_history", {"customer_id": "C001", "channel": "mobile", "limit": 1}).json()["result"]
    assert history["total"] == 3 and len(history["items"]) == 1 and history["items"][0]["channel"] == "mobile"
    profile = execute(client, "get_customer_profile", {"customer_id": "C001"}).json()["result"]
    assert profile["interaction_count"] == 8 and profile["observed_price_basis"] == "current_catalog"


def test_candidate_filter_applies_before_ranking_limit_and_records_provenance(client):
    values = {"request": {"query": "wireless headphones under INR 3000", "limit": 1}, "product_ids": ["P003"]}
    result = execute(client, "rank_recommendations", values).json()["result"]
    assert [item["product"]["id"] for item in result["items"]] == ["P003"]
    saved = execute(client, "save_recommendation", {**values, "idempotency_key": "candidate-test-001"})
    assert saved.status_code == 201, saved.text
    with Session(client.app.state.engine) as session:
        snapshot = session.get(RecommendationSnapshot, saved.json()["recommendation_id"])
        assert snapshot.request["candidate_product_ids"] == ["P003"]


def test_real_chroma_retrieval_tool_returns_grounded_documents_without_llm(client):
    client.post("/rag/ingest", json={})
    with patch("retailrag.rag.select_with_openai", side_effect=AssertionError("no LLM")):
        response = execute(client, "retrieve_product_documents", {"query": "wireless headphones under INR 3000", "brand": "SoundNest"})
    assert response.status_code == 200, response.text
    result = response.json()["result"]
    assert result["references"] == ["P001"] and result["llm_used"] is False
    assert "2499.00" in result["answer"]
    assert result["items"][0]["document_id"] in result["items"][0]["explanation"]


def test_invalid_tools_inputs_ids_and_fabricated_facts_never_execute(client):
    cases = [
        ("get_product_details", {"product_id": "P001", "price": 1}, 422),
        ("check_product_availability", {"product_ids": ["P001"], "available": True}, 422),
        ("filter_by_budget", {"product_ids": ["P001"], "max_price": "1", "prices": {"P001": "0"}}, 422),
        ("filter_by_budget", {"product_ids": ["P001"]}, 422),
        ("search_products", {"min_price": "1000", "max_price": "1"}, 422),
        ("search_products", {"limit": 101}, 422),
        ("get_customer_history", {"customer_id": "C001", "channel": "fake"}, 422),
        ("save_recommendation", {"request": {"query": "headphones"}}, 422),
        ("rank_recommendations", {"request": {"query": "headphones"}, "tool_results": []}, 422),
        ("get_product_details", {"product_id": "MISSING"}, 404),
        ("check_product_availability", {"product_ids": ["P001", "MISSING"]}, 404),
        ("get_customer_profile", {"customer_id": "MISSING"}, 404),
        ("get_customer_history", {"customer_id": "MISSING"}, 404),
        ("not_registered", {}, 404),
    ]
    for name, args, expected in cases:
        response = execute(client, name, args)
        assert response.status_code == expected, response.text
        call = response.json()
        assert call["status"] == "failed" and call["result"] is None
        assert call["recommendation_id"] is None
    assert client.get("/recommendations").json()["total"] == 0
    assert client.get("/tools/invocations", params={"status": "failed"}).json()["total"] == len(cases)


def test_idempotent_save_replays_original_snapshot_and_rejects_reused_key(client):
    args = {"request": {"query": "wireless headphones under INR 3000", "customer_id": "C001", "channel": "mobile"}, "idempotency_key": "stable-save-key-001"}
    first = execute(client, "save_recommendation", args)
    assert first.status_code == 201, first.text
    call = first.json()
    assert call["recommendation_id"] == call["result"]["id"]
    with Session(client.app.state.engine) as session:
        session.get(Product, "P001").price = Decimal("9999")
        session.commit()
    replay = execute(client, "save_recommendation", args)
    assert replay.status_code == 200 and replay.json()["replayed"] is True
    assert replay.json()["call_id"] == call["call_id"]
    assert replay.json()["result"] == call["result"]
    assert client.get("/recommendations").json()["total"] == 1
    assert client.get("/tools/invocations").json()["total"] == 1
    conflict = execute(client, "save_recommendation", {**args, "request": {"mode": "new_customer"}})
    assert conflict.status_code == 409 and conflict.json()["error_code"] == "idempotency_conflict"
    assert conflict.json()["result"] is None and conflict.json()["replayed"] is False
    history = execute(client, "get_recommendation_history", {"customer_id": "C001"}).json()["result"]
    assert history["price_basis"] == "saved_recommendation_snapshot"
    assert history["items"][0]["items"][0]["price_snapshot"] == "2499.00"


def test_canonical_idempotency_ignores_equivalent_money_and_candidate_order(client):
    args = {"request": {"mode": "new_customer", "max_price": "3000"}, "product_ids": ["P001", "P003"], "idempotency_key": "normalize-save-001"}
    first = execute(client, "save_recommendation", args).json()
    replay = execute(client, "save_recommendation", {**args, "request": {"mode": "new_customer", "max_price": "3000.00"}, "product_ids": ["P003", "P001", "P001"]})
    assert replay.status_code == 200 and replay.json()["replayed"] is True
    assert replay.json()["call_id"] == first["call_id"]


def test_fake_but_schema_valid_product_output_is_rejected(client):
    original = RetailTools.product_details
    def fabricate(self, values):
        result = original(self, values)
        result["product"].price = Decimal("1")
        return result
    with patch.object(RetailTools, "product_details", fabricate):
        response = execute(client, "get_product_details", {"product_id": "P001"})
    assert response.status_code == 422, response.text
    call = response.json()
    assert call["error_code"] == "grounding_failed" and call["result"] is None
    assert call["audit"]["status"] == "failed" and call["audit"]["output_sha256"] is None


def test_failed_save_rolls_back_business_rows_but_keeps_audit(client):
    def fail(*args):
        raise RuntimeError("injected snapshot write failure")
    event.listen(RecommendationSnapshot, "before_insert", fail)
    args = {"request": {"query": "headphones"}, "idempotency_key": "failed-save-key-001"}
    try:
        response = execute(client, "save_recommendation", args)
    finally:
        event.remove(RecommendationSnapshot, "before_insert", fail)
    assert response.status_code == 503 and response.json()["status"] == "failed"
    with Session(client.app.state.engine) as session:
        for model in (Recommendation, RecommendationItem, RecommendationSnapshot):
            assert session.scalar(select(func.count()).select_from(model)) == 0
        assert session.scalar(select(func.count()).select_from(ToolInvocation)) == 1
    replay = execute(client, "save_recommendation", args)
    assert replay.status_code == 503 and replay.json()["replayed"] is True
    assert client.get("/recommendations").json()["total"] == 0


def test_in_progress_idempotent_call_is_observable_and_cannot_duplicate_save(client):
    entered, release = Event(), Event()
    original = RetailTools.save
    def blocked(self, values):
        entered.set()
        if not release.wait(10):
            raise RuntimeError("test timeout")
        return original(self, values)
    args = {"request": {"query": "headphones"}, "idempotency_key": "running-save-key-001"}
    with patch.object(RetailTools, "save", blocked), ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(execute, client, "save_recommendation", args)
        try:
            assert entered.wait(10)
            running = client.get("/tools/invocations", params={"status": "running"}).json()
            assert running["total"] == 1
            duplicate = execute(client, "save_recommendation", args)
            assert duplicate.status_code == 409 and duplicate.json()["error_code"] == "in_progress"
        finally:
            release.set()
        assert future.result(timeout=20).status_code == 201
    assert client.get("/recommendations").json()["total"] == 1


def test_sensitive_invalid_fields_are_redacted_and_inspection_is_read_only(client):
    response = execute(client, "get_product_details", {"product_id": "P001", "OPENAI_API_KEY": "sensitive-test-value"})
    assert response.status_code == 422
    assert "sensitive-test-value" not in response.text
    call = response.json()
    assert call["arguments"]["OPENAI_API_KEY"] == "[redacted]"
    assert client.get(f"/tools/invocations/{call['call_id']}").json() == call
    assert client.get("/tools/invocations", params={"tool": "get_product_details", "offset": 1}).json()["items"] == []
    assert client.get("/tools/invocations/missing").status_code == 404
    assert client.get("/tools/invocations", params={"status": "fake"}).status_code == 422
    assert client.get("/tools/invocations").json()["total"] == 1


def test_audit_commit_failure_cannot_leave_a_saved_recommendation(client):
    def fail_completed(mapper, connection, target):
        if target.status == "completed":
            raise RuntimeError("injected audit commit failure")
    event.listen(ToolInvocation, "before_update", fail_completed)
    try:
        response = execute(client, "save_recommendation", {"request": {"query": "headphones"}, "idempotency_key": "audit-failure-key-001"})
    finally:
        event.remove(ToolInvocation, "before_update", fail_completed)
    assert response.status_code == 503 and response.json()["status"] == "failed"
    assert response.json()["recommendation_id"] is None
    with Session(client.app.state.engine) as session:
        assert session.scalar(select(func.count()).select_from(Recommendation)) == 0
        assert session.scalar(select(func.count()).select_from(RecommendationItem)) == 0
        assert session.scalar(select(func.count()).select_from(RecommendationSnapshot)) == 0


def test_internal_workflow_uses_the_new_history_tool_without_public_audit_duplication(client):
    run = client.post("/agents/run", json={"query": "wireless headphones under INR 3000", "customer_id": "C001", "retrieval_strategy": "content"}).json()
    assert run["status"] == "completed"
    context = next(step for step in run["steps"] if step["agent"] == "customer_context")
    assert "get_customer_history" in {call["name"] for call in context["tool_calls"]}
    assert run["checkpoint"]["customer_history"]["total"] == 8
    assert len(run["checkpoint"]["customer_history"]["items"]) == 5
    assert client.get("/tools/invocations").json()["total"] == 0
