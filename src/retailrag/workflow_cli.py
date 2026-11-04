"""Run/inspect real workflows and export reproducible demo execution examples."""

import argparse
import json
from pathlib import Path

from sqlalchemy.orm import Session

from retailrag.config import get_settings
from retailrag.database import build_engine, initialize_database
from retailrag.rag_store import RagStore
from retailrag.workflow import run_workflow, workflow_definition
from retailrag.workflow_persistence import read_workflow_run
from retailrag.workflow_schemas import WorkflowRequest


def main(argv=None):
    parser = argparse.ArgumentParser(description="RetailRAG LangGraph workflow execution")
    parser.add_argument("command", choices=["run", "inspect", "definition", "examples"])
    parser.add_argument("--query", default="")
    parser.add_argument("--customer-id")
    parser.add_argument("--product-id")
    parser.add_argument("--run-id")
    parser.add_argument("--mode", default="context_aware", choices=["context_aware", "personalized", "similar", "budget", "category", "brand", "new_customer"])
    parser.add_argument("--strategy", choices=["auto", "rag", "content"], default="auto")
    parser.add_argument("--category")
    parser.add_argument("--brand")
    parser.add_argument("--max-price")
    parser.add_argument("--channel", choices=["ecommerce", "mobile", "store"], default="ecommerce")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    if args.command == "inspect" and not args.run_id:
        parser.error("inspect requires --run-id")
    engine = None
    try:
        if args.command == "definition":
            result = workflow_definition()
        else:
            settings = get_settings()
            engine = build_engine(settings.database_url)
            initialize_database(engine)
            store = RagStore(settings)
            if args.command == "inspect":
                with Session(engine) as session:
                    result = read_workflow_run(session, args.run_id)
            elif args.command == "run":
                values = {"mode": args.mode, "query": args.query, "retrieval_strategy": args.strategy, "channel": args.channel}
                for key in ("customer_id", "product_id", "category", "brand", "max_price"):
                    if getattr(args, key) is not None:
                        values[key] = getattr(args, key)
                result = run_workflow(engine, store, WorkflowRequest(**values))
            else:
                cases = [{"query": "wireless headphones under INR 3000", "customer_id": "C001", "channel": "mobile"},
                         {"mode": "personalized", "customer_id": "C002", "retrieval_strategy": "content"},
                         {"query": "qzxwunmatched", "retrieval_strategy": "content"}]
                runs = [run_workflow(engine, store, WorkflowRequest(**values, limit=3)) for values in cases]
                result = {"note": "Actual deterministic LangGraph executions against the configured synthetic demo catalog; no LLM is called.",
                          "definition": workflow_definition(), "examples": []}
                for run in runs:
                    steps = [{**step, "tool_calls": [{key: call.get(key) for key in ("name", "status", "duration_ms", "output_summary", "output_sha256", "error")} for call in step["tool_calls"]]} for step in run["steps"]]
                    result["examples"].append({key: run[key] for key in ("run_id", "status", "request", "started_at", "finished_at", "recommendation_id", "output", "error") } | {"steps": steps})
                if args.output is None:
                    args.output = Path("data/phase5_examples.json")
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(json.dumps({"output": str(args.output.resolve()), "status": result.get("status", "exported")}))
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        if args.command == "examples":
            return 0 if all(run["status"] == "completed" for run in runs) else 1
        return 1 if result.get("status") == "failed" else 0
    except Exception:
        print(json.dumps({"status": "error", "message": "Workflow operation failed; check request, database configuration, and persisted run status"}))
        return 1
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
