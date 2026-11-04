"""Generate real, persisted recommendation examples from the configured catalog."""

import argparse
import json
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from retailrag.config import get_settings
from retailrag.database import build_engine, initialize_database
from retailrag.models import Product
from retailrag.recommendation_schemas import RecommendationRequest
from retailrag.recommendations import generate_recommendations


EXAMPLE_REQUESTS = [
    {"mode": "personalized", "customer_id": "C001"},
    {"mode": "similar", "product_id": "P001", "max_price": "3000"},
    {"mode": "budget", "max_price": "1000"},
    {"mode": "category", "category": "Footwear", "max_price": "3500"},
    {"mode": "brand", "brand": "SoundNest", "max_price": "7000"},
    {"mode": "new_customer", "max_price": "2000"},
    {"mode": "context_aware", "customer_id": "C002", "query": "running shoes under INR 3500", "channel": "mobile"},
]


def main(argv=None):
    parser = argparse.ArgumentParser(description="Generate Phase 3 examples using the existing demo records; saves seven recommendations")
    parser.add_argument("--output", type=Path, default=Path("data/phase3_examples.json"))
    args = parser.parse_args(argv)
    engine = build_engine(get_settings().database_url)
    try:
        initialize_database(engine)
        with Session(engine) as session:
            if session.get(Product, "P001") is None:
                parser.error("Examples require the bundled demo IDs. Run python -m retailrag.data_cli demo first.")
            examples = []
            for values in EXAMPLE_REQUESTS:
                request = RecommendationRequest(**values, limit=3)
                response = generate_recommendations(session, request)
                examples.append({
                    "request": request.model_dump(mode="json"), "recommendation_id": response.id,
                    "created_at": response.created_at.isoformat(), "engine": response.engine, "llm_used": response.llm_used,
                    "context": response.context.model_dump(mode="json"),
                    "items": [{"product_id": item.product.id, "name": item.product.name, "price_inr": str(item.product.price),
                               "available": item.product.available, "source": item.product.source, "similarity_score": item.similarity_score,
                               "relevance_score": item.relevance_score, "explanation": item.explanation} for item in response.items],
                })
            output = {"note": "Actual deterministic results from the configured catalog. Bundled demo products and interactions are synthetic.",
                      "catalog_size": session.scalar(select(func.count()).select_from(Product)), "examples": examples}
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            print(json.dumps({"saved_recommendation_ids": [row["recommendation_id"] for row in examples], "output": str(args.output.resolve())}))
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
