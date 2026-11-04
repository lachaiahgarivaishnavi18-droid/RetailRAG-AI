"""Validated, atomic CSV ingestion with explicit provenance and conflict detection."""

import csv
import json
from pathlib import Path

import pandas as pd
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from retailrag.data_schemas import CustomerInput, InteractionInput, ProductInput
from retailrag.models import Customer, CustomerInteraction, DatasetImport, Product


class DataImportError(ValueError):
    pass


TABLES = {
    "products": (ProductInput, Product),
    "customers": (CustomerInput, Customer),
    "interactions": (InteractionInput, CustomerInteraction),
}
JSON_COLUMNS = {"features", "attributes", "preferred_categories", "preferred_brands"}


def read_dataset(path: Path, schema) -> tuple[list[dict], int]:
    """Normalize records; reject invalid data rather than silently repairing facts."""
    try:
        with path.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.reader(stream, strict=True)
            header = next(reader, [])
            for number, row in enumerate(reader, start=2):
                if len(row) != len(header):
                    raise DataImportError(f"{path.name} row {number}: unexpected number of columns")
        required = {name for name, field in schema.model_fields.items() if field.is_required()}
        if len(header) != len(set(header)):
            raise DataImportError(f"{path.name}: duplicate column names")
        if required - set(header) or set(header) - set(schema.model_fields):
            raise DataImportError(f"{path.name}: missing or unknown columns; expected fields: {', '.join(schema.model_fields)}")
        frame = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig", skip_blank_lines=False)
    except (OSError, UnicodeError, csv.Error, pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
        raise DataImportError(f"Cannot read {path.name}: {type(exc).__name__}") from exc

    records = {}
    duplicates = 0
    errors = []
    for number, raw in enumerate(frame.to_dict(orient="records"), start=2):
        try:
            for key in JSON_COLUMNS & raw.keys():
                raw[key] = json.loads(raw[key]) if raw[key].strip() else ([] if key != "attributes" else {})
            if raw.get("image_url") == "":
                raw["image_url"] = None
            row = schema.model_validate(raw)
            values = row.record() if isinstance(row, ProductInput) else row.model_dump()
            if row.id in records:
                if records[row.id] != values:
                    raise ValueError(f"conflicting duplicate ID {row.id}")
                duplicates += 1
            else:
                records[row.id] = values
        except (ValidationError, ValueError, TypeError) as exc:
            # Include locations/messages, without dumping entire customer records.
            detail = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()) if isinstance(exc, ValidationError) else str(exc)
            errors.append(f"{path.name} row {number}: {detail}")
    if errors:
        raise DataImportError("\n".join(errors[:20]) + (f"\n... {len(errors)} invalid rows total" if len(errors) > 20 else ""))
    return list(records.values()), duplicates


def import_directory(engine: Engine, directory: Path, source: str = "user_supplied") -> dict:
    if not source.strip() or len(source) > 100:
        raise DataImportError("source must contain 1–100 characters")
    source = source.strip()
    datasets = {}
    for name, (schema, _) in TABLES.items():
        datasets[name] = read_dataset(directory / f"{name}.csv", schema)

    report = {"source": source, "tables": {}}
    try:
        with Session(engine) as session, session.begin():
            for name, (_, model) in TABLES.items():
                rows, duplicates = datasets[name]
                inserted = skipped = 0
                for values in rows:
                    if model is CustomerInteraction:
                        if session.get(Customer, values["customer_id"]) is None or session.get(Product, values["product_id"]) is None:
                            raise DataImportError(f"interactions: {values['id']} references an unknown customer or product")
                    existing = session.get(model, values["id"])
                    if existing is not None:
                        if existing.source != source or any(getattr(existing, key) != value for key, value in values.items()):
                            raise DataImportError(f"{name}: ID {values['id']} conflicts with an existing record; no records were changed")
                        skipped += 1
                    else:
                        session.add(model(**values, source=source))
                        inserted += 1
                session.flush()
                report["tables"][name] = {"inserted": inserted, "skipped_existing": skipped, "duplicates_removed": duplicates}
            session.add(DatasetImport(source=source, report=report))
    except IntegrityError as exc:
        raise DataImportError("Database integrity check failed; the entire import was rolled back") from exc
    return report


def database_summary(session: Session) -> dict:
    from sqlalchemy import func
    from retailrag.models import AgentExecution, Recommendation, RecommendationItem

    counts = {}
    sources = {}
    for model in (Product, Customer, CustomerInteraction, Recommendation, RecommendationItem, AgentExecution):
        counts[model.__tablename__] = session.scalar(select(func.count()).select_from(model))
        if hasattr(model, "source"):
            sources[model.__tablename__] = dict(session.execute(select(model.source, func.count()).group_by(model.source)).all())
    latest = session.scalar(select(DatasetImport).order_by(DatasetImport.id.desc()).limit(1))
    return {
        "status": "ok", "counts": counts, "sources": sources,
        "last_import": {"source": latest.source, "imported_at": latest.imported_at.isoformat(), "report": latest.report} if latest else None,
    }
