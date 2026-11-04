"""Run with python -m retailrag.data_cli; never seeds implicitly on startup."""

import argparse
import json
from pathlib import Path

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from retailrag.config import get_settings
from retailrag.database import build_engine, initialize_database
from retailrag.ingestion import DataImportError, database_summary, import_directory


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="RetailRAG database setup and atomic CSV ingestion")
    parser.add_argument("command", choices=["init", "import", "demo", "status"])
    parser.add_argument("--directory", type=Path, help="Directory containing products.csv, customers.csv, interactions.csv")
    parser.add_argument("--source", default="user_supplied", help="Provenance label for custom CSV imports")
    args = parser.parse_args(argv)
    if args.command == "import" and args.directory is None:
        parser.error("import requires --directory")
    engine = None
    try:
        engine = build_engine(get_settings().database_url)
        initialize_database(engine)
        if args.command in ("demo", "import"):
            directory = Path("data/demo") if args.command == "demo" else args.directory
            result = import_directory(engine, directory, "synthetic_demo" if args.command == "demo" else args.source)
        elif args.command == "status":
            with Session(engine) as session:
                result = database_summary(session)
        else:
            result = {"status": "ok", "message": "Missing tables created; existing data preserved"}
        print(json.dumps(result, indent=2))
        return 0
    except (DataImportError, SQLAlchemyError, ImportError, OSError) as exc:
        message = str(exc) if isinstance(exc, DataImportError) else "Database operation failed; check the configured connection and schema"
        print(json.dumps({"status": "error", "message": message}, indent=2))
        return 1
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
