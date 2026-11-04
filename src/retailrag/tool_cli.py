"""Discover/execute audited tools and export real tool examples."""

import argparse
import json
import uuid
from pathlib import Path

from retailrag.config import get_settings
from retailrag.database import build_engine, initialize_database
from retailrag.rag_store import RagStore
from retailrag.tool_service import ToolService


def main(argv=None):
    parser = argparse.ArgumentParser(description="RetailRAG validated tool discovery and execution")
    parser.add_argument("command", choices=["list", "describe", "execute", "inspect", "examples"])
    parser.add_argument("--name")
    parser.add_argument("--call-id")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--arguments", default=None, help="JSON object of tool inputs")
    group.add_argument("--arguments-file", type=Path, help="UTF-8 JSON object of tool inputs")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    if args.command in {"describe", "execute"} and not args.name:
        parser.error("This command requires --name")
    if args.command == "inspect" and not args.call_id:
        parser.error("inspect requires --call-id")
    engine = None
    try:
        settings = get_settings()
        engine = build_engine(settings.database_url)
        initialize_database(engine)
        service = ToolService(engine, RagStore(settings))
        status_code = 200
        if args.command == "list":
            result = service.discovery()
        elif args.command == "describe":
            result = next(item for item in service.discovery()["items"] if item["name"] == args.name)
        elif args.command == "inspect":
            result = service.read(args.call_id)
        elif args.command == "execute":
            text = args.arguments_file.read_text(encoding="utf-8-sig") if args.arguments_file else args.arguments or "{}"
            result, status_code = service.execute(args.name, json.loads(text))
        else:
            catalog = service.discovery()
            executions = []
            saved_arguments = None
            for item in catalog["items"]:
                arguments = json.loads(json.dumps(item["example_arguments"]))
                if item["name"] == "save_recommendation":
                    arguments["idempotency_key"] = "example_" + uuid.uuid4().hex
                    saved_arguments = arguments
                invocation, code = service.execute(item["name"], arguments)
                executions.append({"http_status": code, "execution": invocation})
            replayed, code = service.execute("save_recommendation", saved_arguments)
            executions.append({"http_status": code, "execution": replayed})
            result = {"note": "Actual audited tools against the configured synthetic demo dataset. One recommendation is saved; its retry reuses the original invocation.",
                      "tool_count": catalog["total"], "examples": executions}
            status_code = 200 if all(item["execution"].get("status") == "completed" for item in executions) else 500
            if args.output is None:
                args.output = Path("data/phase6_examples.json")
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            print(json.dumps({"output": str(args.output.resolve()), "status": "completed" if status_code < 400 else "failed"}))
        else:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0 if status_code < 400 else 1
    except Exception:
        print(json.dumps({"status": "failed", "error": "Tool operation failed; inspect its input schema, arguments, configuration, and invocation history"}))
        return 1
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
