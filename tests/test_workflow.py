import json
from decimal import Decimal
from threading import Event
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.orm import Session

from retailrag.models import AgentExecution, Product, Recommendation, RecommendationItem, RecommendationSnapshot, WorkflowRun, WorkflowStep
from retailrag.workflow import AGENTS, build_workflow, run_workflow, workflow_definition
from retailrag.workflow_schemas import WorkflowRequest
from retailrag.workflow_tools import WorkflowTools


def counts(client):
    with Session(client.app.state.engine) as session:
        return {model.__tablename__: session.scalar(select(func.count()).select_from(model)) for model in
                (Recommendation, RecommendationItem, RecommendationSnapshot, WorkflowRun, WorkflowStep, AgentExecution)}


def test_actual_compiled_graph_definition_has_ten_nodes_and_conditional_routes(client):
    graph = build_workflow(None)
    assert hasattr(graph, "invoke")
    definition = client.get("/agents/definition").json()
    assert definition["engine"] == "LangGraph" and definition["llm_used"] is False
    assert [node["name"] for node in definition["nodes"]] == list(AGENTS)
    assert any(edge["source"] == "product_retrieval" and edge["target"] == "validation" and edge["conditional"] for edge in definition["edges"])
    assert "supervisor" in definition["mermaid"] and "response" in definition["mermaid"]


def test_content_workflow_executes_all_roles_and_actual_validated_tools(client):
    response = client.post("/agents/run", json={"query": "wireless headphones under INR 3000", "customer_id": "C001", "retrieval_strategy": "content", "channel": "mobile"})
    assert response.status_code == 201, response.text
    run = response.json()
    assert run["status"] == "completed", run
    assert [step["agent"] for step in run["steps"]] == list(AGENTS)
    assert all(step["status"] == "completed" and step["finished_at"] for step in run["steps"])
    calls = [call for step in run["steps"] for call in step["tool_calls"]]
    assert calls and all(call["status"] == "completed" for call in calls)
    assert all(call["output_sha256"] and call["duration_ms"] >= 0 for call in calls)
    assert {"search_products", "get_customer_profile", "score_recommendation_candidates", "rank_recommendations", "check_product_availability", "validate_recommendations", "save_recommendation"} <= {call["name"] for call in calls}
    output = run["output"]
    assert output["references"][0] == "P001"
    assert output["engine"] == "langgraph_workflow" and not output["llm_used"]
    assert output["validation"]["valid"] is True
    assert output["profile"]["interaction_count"] == 8
    assert all(item["product"]["available"] and Decimal(item["product"]["price"]) < 3000 for item in output["items"])
    assert client.get(f"/recommendations/{run['recommendation_id']}").json() == output
    assert client.get(f"/agents/runs/{run['run_id']}").json() == run
    assert run["checkpoint"]["executed_agents"] == list(AGENTS)
    assert counts(client)["agent_executions"] == 10
    with Session(client.app.state.engine) as session:
        assert all(row.recommendation_id == run["recommendation_id"] for row in session.scalars(select(AgentExecution)))


def test_chroma_branch_uses_real_evidence_and_never_calls_optional_llm(client):
    assert client.post("/rag/ingest", json={}).status_code == 200
    with patch("retailrag.rag.select_with_openai", side_effect=AssertionError("must not call LLM")):
        client.app.state.rag_store.settings = client.app.state.rag_store.settings.model_copy(update={"rag_generation_mode": "openai"})
        run = client.post("/agents/run", json={"query": "wireless headphones under INR 3000", "customer_id": "C001"}).json()
    assert run["status"] == "completed", run
    assert run["checkpoint"]["plan"]["selected_strategy"] == "rag"
    assert run["output"]["retrieval_source"] == "rag"
    assert run["output"]["index_generation"]
    assert all(item["retrieval_source"] == "chroma" and item["document_id"] in item["explanation"] for item in run["output"]["items"])
    assert "Chroma LSA cosine" in run["output"]["items"][0]["explanation"]
    assert "retrieve_product_documents" in {call["name"] for step in run["steps"] for call in step["tool_calls"]}


def test_auto_fallback_and_explicit_rag_failure_have_truthful_routes(client):
    run = client.post("/agents/run", json={"query": "wireless headphones"}).json()
    assert run["status"] == "completed" and run["output"]["retrieval_source"] == "content"
    assert any("fallback" in warning for warning in run["output"]["warnings"])
    assert client.get("/rag/status").json()["status"] == "not_ingested"
    failed = client.post("/agents/run", json={"query": "wireless headphones", "retrieval_strategy": "rag"}).json()
    assert failed["status"] == "failed" and failed["recommendation_id"] is None
    assert [(step["agent"], step["status"]) for step in failed["steps"]] == [("supervisor", "failed"), ("response", "completed")]
    assert failed["output"]["items"] == [] and not failed["output"]["validation"]["valid"]
    assert counts(client)["recommendations"] == 1


def test_vector_tool_failure_is_audited_and_auto_fallback_preserves_filters(client):
    client.post("/rag/ingest", json={})
    with patch.object(WorkflowTools, "vector_retrieval", side_effect=RuntimeError("sensitive-service-details")):
        run = client.post("/agents/run", json={"query": "wireless headphones under INR 3000", "brand": "SoundNest"}).json()
        failed = client.post("/agents/run", json={"query": "wireless headphones", "retrieval_strategy": "rag"}).json()
    assert run["status"] == "completed" and run["output"]["references"] == ["P001"]
    step = next(step for step in run["steps"] if step["agent"] == "product_retrieval")
    assert [(call["name"], call["status"]) for call in step["tool_calls"]] == [("retrieve_product_documents", "failed"), ("search_products", "completed")]
    assert failed["status"] == "failed" and failed["recommendation_id"] is None
    assert "sensitive-service-details" not in json.dumps([run, failed])


def test_empty_results_branch_skips_unexecuted_agents_and_saves_empty_run(client):
    run = client.post("/agents/run", json={"query": "qzxwunmatched", "retrieval_strategy": "content"}).json()
    assert run["status"] == "completed"
    assert [step["agent"] for step in run["steps"]] == ["supervisor", "query_understanding", "customer_context", "product_retrieval", "validation", "response"]
    assert run["output"]["items"] == [] and run["output"]["references"] == []
    assert run["recommendation_id"] is not None
    assert run["output"]["validation"]["checked_products"] == 0
    assert counts(client)["recommendation_items"] == 0


@pytest.mark.parametrize("values", [
    {"mode": "personalized", "customer_id": "C001"},
    {"mode": "similar", "product_id": "P001", "max_price": "3000"},
    {"mode": "budget", "max_price": "1000"}, {"mode": "category", "category": "Footwear"},
    {"mode": "brand", "brand": "SoundNest"}, {"mode": "new_customer"},
    {"query": "running shoes under INR 3500", "customer_id": "C002"},
])
def test_supported_recommendation_modes(client, values):
    run = client.post("/agents/run", json={**values, "retrieval_strategy": "content"}).json()
    assert run["status"] == "completed", run
    assert run["output"]["items"]
    assert run["output"]["validation"]["valid"]
    if values.get("mode") == "similar":
        assert run["output"]["references"] == ["P003"]


@pytest.mark.parametrize("values", [
    {"query": "headphones", "customer_id": "MISSING", "retrieval_strategy": "content"},
    {"mode": "similar", "product_id": "MISSING"},
    {"query": "headphones without SoundNest", "retrieval_strategy": "content"},
])
def test_domain_failures_are_persisted_without_recommendations(client, values):
    response = client.post("/agents/run", json=values)
    assert response.status_code == 201
    run = response.json()
    assert run["status"] == "failed" and run["error"]
    assert run["output"]["items"] == [] and run["recommendation_id"] is None
    assert any(step["status"] == "failed" for step in run["steps"])
    assert counts(client)["recommendations"] == 0


def test_live_availability_recheck_drops_changed_stock_before_response(client):
    original = WorkflowTools.availability
    def change_stock(self, values):
        with Session(self.engine) as session:
            session.get(Product, "P001").stock_quantity = 0
            session.commit()
        return original(self, values)
    with patch.object(WorkflowTools, "availability", change_stock):
        run = client.post("/agents/run", json={"query": "wireless headphones under INR 3000", "retrieval_strategy": "content"}).json()
    assert run["status"] == "completed", run
    assert "P001" not in run["output"]["references"]
    assert run["output"]["references"] == ["P003"]
    assert any("recheck excluded" in warning for warning in run["output"]["warnings"])


def test_fabricated_explanation_is_rejected_by_validation_agent(client):
    original = WorkflowTools.explain
    def fabricate(self, values):
        result = original(self, values)
        result["items"][0].explanation = "Invented price INR 1.00"
        return result
    with patch.object(WorkflowTools, "explain", fabricate):
        run = client.post("/agents/run", json={"query": "headphones", "retrieval_strategy": "content"}).json()
    assert run["status"] == "failed" and run["recommendation_id"] is None
    assert next(step for step in run["steps"] if step["agent"] == "validation")["status"] == "failed"
    assert "Invented price" not in run["output"]["answer"]
    assert counts(client)["recommendations"] == 0


def test_failed_snapshot_save_rolls_back_recommendation_items_and_links(client):
    def fail(*args):
        raise RuntimeError("injected persistence failure")
    event.listen(RecommendationSnapshot, "before_insert", fail)
    try:
        run = client.post("/agents/run", json={"query": "headphones", "retrieval_strategy": "content"}).json()
    finally:
        event.remove(RecommendationSnapshot, "before_insert", fail)
    assert run["status"] == "failed" and run["recommendation_id"] is None
    assert run["steps"][-1]["agent"] == "response" and run["steps"][-1]["status"] == "failed"
    result = counts(client)
    assert result["recommendations"] == result["recommendation_items"] == result["recommendation_snapshots"] == 0
    with Session(client.app.state.engine) as session:
        assert all(execution.recommendation_id is None for execution in session.scalars(select(AgentExecution)))


def test_running_status_is_real_and_visible_during_blocked_tool_execution(client):
    entered, release = Event(), Event()
    original = WorkflowTools.content_retrieval
    def blocked(self, values):
        entered.set()
        if not release.wait(10):
            raise RuntimeError("test synchronization timed out")
        return original(self, values)
    with patch.object(WorkflowTools, "content_retrieval", blocked), ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(client.post, "/agents/run", json={"query": "headphones", "retrieval_strategy": "content"})
        try:
            assert entered.wait(10)
            status = client.get("/agents/status", params={"status": "running"}).json()
            assert status["total"] == 1
            current = client.get(f"/agents/runs/{status['items'][0]['run_id']}").json()
            assert current["status"] == "running" and current["steps"][-1]["agent"] == "product_retrieval"
            assert current["steps"][-1]["status"] == "running"
            assert current["steps"][-1]["finished_at"] is None
        finally:
            release.set()
        assert future.result(timeout=15).json()["status"] == "completed"
