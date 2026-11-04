"""Repeatable local acceptance checks using isolated synthetic data and real services.

Run with the dev dependencies installed. Existing application data is never opened.
"""

import argparse
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import inspect, text

from retailrag.api import create_app
from retailrag.config import Settings
from retailrag.database import build_engine, initialize_database
from retailrag.ingestion import import_directory


def verify(directory: Path, demo: Path) -> dict:
    directory = directory.resolve()
    directory.mkdir(parents=True, exist_ok=False)
    settings = Settings(_env_file=None, environment="test",
                        database_url=f"sqlite:///{(directory / 'acceptance.db').as_posix()}",
                        rag_directory=directory / "chroma", rag_generation_mode="deterministic",
                        OPENAI_API_KEY=None)
    engine = build_engine(settings.database_url)
    try:
        initialize_database(engine)
        import_directory(engine, demo, "synthetic_demo")
        tables = inspect(engine).get_table_names()
        with engine.connect() as connection:
            assert connection.scalar(text("PRAGMA foreign_keys")) == 1
            assert not connection.execute(text("PRAGMA foreign_key_check")).all()
    finally:
        engine.dispose()

    def request(client, method, path, **kwargs):
        response = client.request(method, path, **kwargs)
        assert response.is_success, f"{method} {path}: HTTP {response.status_code}: {response.text}"
        return response.json()

    with TestClient(create_app(settings)) as client:
        health = request(client, "GET", "/health")
        readiness = request(client, "GET", "/ready")
        configuration = request(client, "GET", "/settings")
        assert not configuration["llm_credentials_configured"]
        initial = request(client, "GET", "/analytics/overview")
        assert initial["totals"]["products"] == 24 and initial["totals"]["interactions"] == 56
        search = request(client, "GET", "/products/search", params={"q": "headphones", "max_price": 3000})
        assert search["items"]
        personalized = request(client, "POST", "/recommendations", json={"mode": "personalized", "customer_id": "C001"})
        assert personalized["items"] and all(item["explanation"] for item in personalized["items"])
        ingestion = request(client, "POST", "/rag/ingest", json={})
        assert ingestion["products"] == 24
        query = "wireless headphones under INR 3000"
        rag = request(client, "POST", "/rag/search", json={"query": query})
        assert rag["references"] and not rag["llm_used"] and rag["items"][0]["document"]
        workflow = request(client, "POST", "/agents/run", json={"query": query, "customer_id": "C001", "retrieval_strategy": "rag"})
        assert workflow["status"] == "completed" and len(workflow["steps"]) == 10
        assert any(step.get("tool_calls") for step in workflow["steps"])
        tools = request(client, "GET", "/tools")
        assert len(tools["items"]) == 11
        tool = request(client, "POST", "/tools/get_product_details/execute", json={"arguments": {"product_id": "P001"}})
        assert tool["status"] == "completed"
        journey = {"customer_id": "C008", "query": query, "idempotency_key": "final-acceptance-journey",
                   "events": [{"product_id": "P001", "event_type": "view", "channel": "ecommerce"},
                              {"product_id": "P005", "event_type": "wishlist", "channel": "mobile"},
                              {"product_id": "P013", "event_type": "purchase", "channel": "store", "quantity": 2}]}
        simulation = request(client, "POST", "/omnichannel/simulations", json=journey)
        replay = request(client, "POST", "/omnichannel/simulations", json=journey)
        assert replay["replayed"] and replay["simulation_id"] == simulation["simulation_id"]
        assert all(profile["interaction_count"] == 3 for profile in simulation["profiles_after"].values())
        analytics = {name: request(client, "GET", f"/analytics/{name}") for name in ("overview", "recommendations", "channels")}
        assert analytics["overview"]["totals"]["interactions"] == 59
        assert analytics["recommendations"]["total_runs"] == 5
        assert request(client, "GET", "/recommendations")["total"] == 5

    # A second application/engine proves committed history and vector persistence.
    with TestClient(create_app(settings)) as reopened:
        assert request(reopened, "GET", "/recommendations")["total"] == 5
        assert request(reopened, "GET", "/customers/C008/history")["total"] == 3
        assert request(reopened, "GET", "/rag/status")["status"] == "ready"
        assert request(reopened, "POST", "/rag/search", json={"query": query})["references"] == rag["references"]
        assert request(reopened, "POST", "/omnichannel/simulations", json=journey)["replayed"]

    return {"status": "passed", "checked_at": datetime.now(timezone.utc).isoformat(),
            "scope": "isolated synthetic acceptance database; working application database preserved",
            "directory": str(directory), "health": health, "readiness": readiness,
            "database_tables": tables, "foreign_key_check": "passed", "initial": initial,
            "personalized": personalized, "rag_ingestion": ingestion, "rag": rag,
            "workflow": workflow, "tool": tool, "simulation": simulation,
            "simulation_retry": {"replayed": replay["replayed"], "simulation_id": replay["simulation_id"]},
            "analytics": analytics, "persistence_after_restart": "passed", "llm_used": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("data/final_acceptance.json"))
    parser.add_argument("--demo", type=Path, default=Path("data/demo"))
    parser.add_argument("--work-root", type=Path, default=Path(".runtime/acceptance"))
    args = parser.parse_args()
    result = verify(args.work_root / uuid.uuid4().hex, args.demo)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Acceptance passed. Actual results: {args.output.resolve()}")


if __name__ == "__main__":
    main()
