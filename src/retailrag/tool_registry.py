"""Shared LangChain tool registration, validation, and truthful invocation audits."""

import hashlib
import json
from datetime import datetime, timezone
from time import perf_counter

from langchain_core.tools import StructuredTool

from retailrag.workflow_schemas import ToolCall

SENSITIVE_KEYS = {"api_key", "openai_api_key", "password", "secret", "authorization", "access_token", "refresh_token"}


def redact(value):
    if isinstance(value, dict):
        return {key: "[redacted]" if key.casefold() in SENSITIVE_KEYS else redact(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def result_digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def summarize_result(value):
    summary = {"keys": sorted(value)}
    if isinstance(value.get("items"), list):
        summary["item_count"] = len(value["items"])
        summary["product_ids"] = [item.get("product", {}).get("id", item.get("product_id", item.get("id"))) for item in value["items"]
                                  if isinstance(item, dict) and ("product" in item or "product_id" in item or "stock_quantity" in item)]
    for key in ("status", "valid", "checked_products", "products", "interactions", "customer_id", "interaction_count", "indexed_products", "indexed_chunks", "total"):
        if key in value and not isinstance(value[key], (list, dict)):
            summary[key] = value[key]
    return summary


class ToolRegistry:
    def __init__(self):
        self.calls, self.specs = [], {}

    def register(self, name, description, input_schema, output_schema, operation, *, effect="read", example=None):
        if name in self.specs:
            raise ValueError("Duplicate tool registration")
        def execute(**arguments):
            values = input_schema.model_validate(arguments)
            return output_schema.model_validate(operation(values)).model_dump(mode="json")
        tool = StructuredTool.from_function(func=execute, name=name, description=description, args_schema=input_schema)
        self.specs[name] = {"tool": tool, "input": input_schema, "output": output_schema, "effect": effect, "example": example or {}}

    def describe(self, name):
        spec = self.specs[name]
        return {"name": name, "description": spec["tool"].description, "effect": spec["effect"],
                "input_schema": spec["input"].model_json_schema(), "output_schema": spec["output"].model_json_schema(),
                "example_arguments": spec["example"]}

    def call(self, name, arguments):
        if name not in self.specs:
            raise ValueError("Unknown workflow tool")
        from retailrag.workflow_tools import safe_error
        spec = self.specs[name]
        started, timer = datetime.now(timezone.utc), perf_counter()
        entry = {"name": name, "arguments": redact(arguments), "started_at": started}
        try:
            result = spec["tool"].invoke(arguments)
            validated = spec["output"].model_validate(result).model_dump(mode="json")
            entry.update(status="completed", output_summary=summarize_result(validated), output_sha256=result_digest(validated))
            return validated
        except Exception as exc:
            entry.update(status="failed", error=safe_error(exc))
            raise
        finally:
            entry.update(finished_at=datetime.now(timezone.utc), duration_ms=round((perf_counter() - timer) * 1000, 3))
            self.calls.append(ToolCall.model_validate(entry).model_dump(mode="json"))
