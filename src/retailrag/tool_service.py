"""Durable public tool invocation with atomic, idempotent recommendation writes."""

import json
import uuid
from decimal import Decimal

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from retailrag.models import ToolInvocation, utc_now
from retailrag.retail_tools import RetailTools
from retailrag.tool_registry import redact, result_digest
from retailrag.tool_validation import ToolGroundingError, validate_tool_result
from retailrag.workflow_tools import safe_error


def normalize_arguments(value):
    if isinstance(value, dict):
        result = {key: normalize_arguments(item) for key, item in value.items()}
        for key in ("min_price", "max_price"):
            if result.get(key) is not None:
                result[key] = f"{Decimal(str(result[key])):.2f}"
        if isinstance(result.get("product_ids"), list):
            result["product_ids"] = sorted(set(result["product_ids"]))
        return result
    if isinstance(value, list):
        return [normalize_arguments(item) for item in value]
    return value


def invocation_payload(row, *, replayed=False):
    return {"call_id": row.id, "tool": row.tool_name, "effect": row.effect, "status": row.status,
            "arguments": row.arguments, "started_at": row.started_at.isoformat(),
            "finished_at": row.finished_at.isoformat() if row.finished_at else None,
            "recommendation_id": row.recommendation_id, "result": row.result, "audit": row.audit,
            "error_code": row.error_code, "error": row.error, "replayed": replayed}


def error_status(code):
    return {"not_found": 404, "unknown_tool": 404, "validation_failed": 422, "grounding_failed": 422,
            "idempotency_conflict": 409, "in_progress": 409}.get(code, 503)


class ToolService:
    def __init__(self, engine, store):
        self.engine, self.store = engine, store

    def discovery(self):
        registry = RetailTools(self.engine, self.store)
        return {"total": len(registry.specs), "items": [registry.describe(name) for name in registry.specs]}

    def read(self, call_id):
        with Session(self.engine) as session:
            row = session.get(ToolInvocation, call_id)
            if row is None:
                raise LookupError("Tool invocation not found")
            return invocation_payload(row)

    def existing_key(self, key, digest):
        with Session(self.engine) as session:
            row = session.scalar(select(ToolInvocation).where(ToolInvocation.idempotency_key == key))
            if row is None:
                return None
            payload = invocation_payload(row, replayed=True)
            if row.request_sha256 != digest or row.tool_name != "save_recommendation":
                payload.update(result=None, replayed=False, error_code="idempotency_conflict", error="This idempotency key already belongs to a different request")
                return payload, 409
            if row.status == "running":
                payload.update(error_code="in_progress", error="The original invocation is still running; inspect its call ID before retrying")
                return payload, 409
            return payload, 200 if row.status == "completed" else error_status(row.error_code)

    def execute(self, name, arguments):
        # Reject non-JSON/nonfinite/oversized arguments before they can enter an audit.
        try:
            if len(name) > 100 or not isinstance(arguments, dict):
                raise ValueError("Invalid tool invocation")
            encoded = json.dumps(arguments, ensure_ascii=False, allow_nan=False)
            if len(encoded.encode()) > 65536:
                raise ValueError("Tool arguments exceed 64 KiB")
        except (ValueError, TypeError):
            return {"status": "failed", "error_code": "validation_failed", "error": "Arguments must be a finite JSON object no larger than 64 KiB"}, 422
        registry = RetailTools(self.engine, self.store)
        spec = registry.specs.get(name)
        values, validation_error = None, None
        if spec:
            try:
                values = spec["input"].model_validate(arguments)
                canonical = normalize_arguments(values.model_dump(mode="json"))
            except ValidationError as exc:
                validation_error = exc
                canonical = redact(arguments)
        else:
            canonical = redact(arguments)
        key = canonical.get("idempotency_key") if name == "save_recommendation" and values is not None else None
        digest = result_digest({key: value for key, value in canonical.items() if key != "idempotency_key"})
        if key:
            existing = self.existing_key(key, digest)
            if existing is not None:
                return existing
        call_id = uuid.uuid4().hex
        try:
            with Session(self.engine) as session, session.begin():
                session.add(ToolInvocation(id=call_id, tool_name=name, effect=spec["effect"] if spec else "unknown",
                                           status="running", arguments=redact(canonical), request_sha256=digest,
                                           idempotency_key=key))
        except IntegrityError:
            if key:
                existing = self.existing_key(key, digest)
                if existing is not None:
                    return existing
            raise
        if spec is None or validation_error is not None:
            code = "unknown_tool" if spec is None else "validation_failed"
            with Session(self.engine) as session, session.begin():
                row = session.get(ToolInvocation, call_id)
                row.status, row.finished_at, row.error_code = "failed", utc_now(), code
                row.error = "Tool is not in the public allowlist" if spec is None else "Arguments failed the published input schema"
            return self.read(call_id), error_status(code)
        try:
            with Session(self.engine) as session, session.begin():
                # A write tool and its completed audit/result commit together.
                registry.session = session
                result = registry.call(name, canonical)
                parsed = spec["input"].model_validate(canonical)
                validate_tool_result(session, self.store, name, parsed, result)
                row = session.get(ToolInvocation, call_id)
                row.status, row.finished_at, row.result = "completed", utc_now(), result
                row.audit = registry.calls[-1]
                if spec["effect"] == "write":
                    row.recommendation_id = result["id"]
            return self.read(call_id), 201 if spec["effect"] == "write" else 200
        except Exception as exc:
            code = "grounding_failed" if isinstance(exc, ToolGroundingError) else "validation_failed" if isinstance(exc, (ValidationError, ValueError)) else "not_found" if isinstance(exc, LookupError) else "operation_failed"
            with Session(self.engine) as session, session.begin():
                row = session.get(ToolInvocation, call_id)
                row.status, row.finished_at, row.error_code, row.error = "failed", utc_now(), code, safe_error(exc)
                row.result, row.recommendation_id = None, None
                if registry.calls:
                    row.audit = {**registry.calls[-1], "status": "failed", "output_sha256": None,
                                 "output_summary": None, "error": safe_error(exc)}
            return self.read(call_id), error_status(code)
