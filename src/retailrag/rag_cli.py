"""Local vector index management and reproducible RAG example export."""

import argparse
import json
from pathlib import Path

from sqlalchemy.orm import Session

from retailrag.config import get_settings
from retailrag.database import build_engine, initialize_database
from retailrag.rag import search_products
from retailrag.rag_schemas import RagSearchRequest
from retailrag.rag_store import RagStore


def main(argv=None):
    parser = argparse.ArgumentParser(description="RetailRAG persistent Chroma index")
    parser.add_argument("command", choices=["ingest", "status", "delete", "search", "examples"])
    parser.add_argument("--product-id", help="Partial ingest or index-only deletion")
    parser.add_argument("--query", help="Search request")
    parser.add_argument("--force", action="store_true", help="Rebuild vectors, including recovery from an unreadable manifest for full ingestion")
    parser.add_argument("--output", type=Path, default=Path("data/phase4_examples.json"))
    args = parser.parse_args(argv)
    if args.command == "delete" and not args.product_id:
        parser.error("delete requires --product-id")
    if args.command == "search" and not args.query:
        parser.error("search requires --query")
    engine = build_engine(get_settings().database_url)
    try:
        initialize_database(engine)
        store = RagStore(get_settings())
        with Session(engine) as session:
            if args.command == "ingest":
                result = store.ingest(session, [args.product_id] if args.product_id else None, force=args.force)
            elif args.command == "status":
                result = store.status(session)
            elif args.command == "delete":
                result = store.delete_product(args.product_id)
            elif args.command == "search":
                result = search_products(session, store, RagSearchRequest(query=args.query)).model_dump(mode="json")
            else:
                requests = [RagSearchRequest(query="wireless headphones under INR 3000"),
                            RagSearchRequest(query="running shoes", category="Footwear", max_price="3500", channel="mobile"),
                            RagSearchRequest(query="SoundNest headphones", brand="SoundNest", max_price="7000"),
                            RagSearchRequest(query="qzxwunmatched")]
                result = {"index_status": store.status(session), "note": "Actual retrieved synthetic demo catalog evidence; no recommendation history is written.",
                          "examples": [search_products(session, store, request).model_dump(mode="json") for request in requests]}
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                result = {"output": str(args.output.resolve()), "examples": len(requests)}
            print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception:
        print(json.dumps({"status": "error", "message": "RAG operation failed; check configuration, catalog IDs, index status, and permissions"}))
        return 1
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
