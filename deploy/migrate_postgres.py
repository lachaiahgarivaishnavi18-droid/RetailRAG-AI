"""Copy a read-only SQLite snapshot into a NEW private PostgreSQL schema.

Defaults to inventory only. Credentials come from the ignored .env/environment;
never from command-line arguments. Does not modify the source database.
"""
import argparse
import json
import os
import re
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import MetaData, create_engine, inspect, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.schema import CreateSchema

from retailrag.models import Base


def destination_metadata(schema):
    """Keep all tables and foreign keys inside a private release schema."""
    if not re.fullmatch(r"retailrag_[a-z0-9_]+", schema):
        raise ValueError("Use a new schema named retailrag_<release>.")
    metadata = MetaData()
    for table in Base.metadata.sorted_tables:
        table.to_metadata(metadata, schema=schema,
                          referred_schema_fn=lambda *args: schema)
    return metadata


def copy_rows(source, target, schema):
    """Transactionally create a previously absent schema, then copy and compare."""
    metadata = destination_metadata(schema)
    counts = {}
    with target.begin() as dest:
        # CREATE SCHEMA without IF NOT EXISTS deliberately refuses any retry
        # against existing records. PostgreSQL DDL and inserts roll back together.
        dest.execute(CreateSchema(schema))
        metadata.create_all(dest)
        for original in Base.metadata.sorted_tables:
            table = metadata.tables[f"{schema}.{original.name}"]
            rows = [dict(row) for row in source.execute(select(original)).mappings()]
            for offset in range(0, len(rows), 100):
                dest.execute(table.insert(), rows[offset:offset + 100])
            order = list(original.primary_key.columns)
            source_rows = source.execute(select(original).order_by(*order)).all()
            target_order = [table.c[col.name] for col in order]
            target_rows = dest.execute(select(table).order_by(*target_order)).all()
            if source_rows != target_rows:
                raise ValueError(f"Record verification failed for {original.name}; rolled back.")
            counts[original.name] = len(rows)
            # Explicitly copied integer IDs must not collide with future inserts.
            if len(order) == 1 and order[0].type.python_type is int:
                name = order[0].name
                sequence = dest.scalar(text("SELECT pg_get_serial_sequence(:table, :column)"),
                                       {"table": f"{schema}.{table.name}", "column": name})
                if sequence:
                    maximum = max((row[name] for row in rows), default=0)
                    dest.execute(text("SELECT setval(CAST(:sequence AS regclass), :value, :used)"),
                                 {"sequence": sequence, "value": max(maximum, 1), "used": maximum > 0})
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("data/retailrag.db"))
    parser.add_argument("--schema", default="retailrag_first_import")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    load_dotenv(override=False)
    if not args.source.is_file():
        raise SystemExit("Source SQLite file is missing; nothing created.")
    # SQLite backup API produces a consistent snapshot, including committed WAL.
    with tempfile.TemporaryDirectory(prefix="retailrag-migration-") as folder:
        snapshot = Path(folder) / "snapshot.db"
        uri = args.source.resolve().as_uri() + "?mode=ro"
        with closing(sqlite3.connect(uri, uri=True)) as original, closing(sqlite3.connect(snapshot)) as backup:
            original.backup(backup)
        source_engine = create_engine(f"sqlite:///{snapshot.as_posix()}")
        target = None
        try:
            with source_engine.connect() as source:
                names = set(inspect(source).get_table_names())
                if names != set(Base.metadata.tables):
                    raise ValueError("Source tables differ from application schema; manual review required.")
                if not args.apply:
                    counts = {t.name: len(source.execute(select(t)).all())
                              for t in Base.metadata.sorted_tables}
                    print(json.dumps({"mode": "inventory_only", "tables": counts}, indent=2))
                    return
                value = os.environ.get("RETAILRAG_MIGRATION_DATABASE_URL", "")
                if not value:
                    raise ValueError("Set RETAILRAG_MIGRATION_DATABASE_URL privately in .env.")
                url = make_url(value)
                if url.drivername != "postgresql+psycopg" or url.query.get("sslmode") != "require":
                    raise ValueError("Use postgresql+psycopg with sslmode=require.")
                target = create_engine(url, pool_pre_ping=True)
                counts = copy_rows(source, target, args.schema)
                print(json.dumps({"mode": "copied_and_verified", "schema": args.schema,
                                  "tables": counts}, indent=2))
        finally:
            source_engine.dispose()
            if target is not None:
                target.dispose()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # SQLAlchemy exceptions may contain connection URIs or row data.
        print(f"Migration stopped ({type(exc).__name__}); no credentials or records displayed.")
        raise SystemExit(1) from None
