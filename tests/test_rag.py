import json
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import httpx
import numpy as np
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from retailrag.catalog_api import ProductOutput
from retailrag.config import Settings
from retailrag.models import Product, Recommendation
from retailrag.rag import search_products, validate_grounding
from retailrag.rag_documents import product_documents
from retailrag.rag_embeddings import LocalLSAEmbeddings
from retailrag.rag_generation import select_with_openai
from retailrag.rag_schemas import RagSearchRequest
from retailrag.rag_store import RagStore


@pytest.fixture
def indexed(seeded_engine, tmp_path):
    settings = Settings(_env_file=None, rag_directory=tmp_path / "vectors", rag_generation_mode="deterministic")
    store = RagStore(settings)
    with Session(seeded_engine) as session:
        store.ingest(session)
    return seeded_engine, store


def retrieve(indexed, **values):
    engine, store = indexed
    with Session(engine) as session:
        return search_products(session, store, RagSearchRequest(**values))


def test_embeddings_are_normalized_and_round_trip_without_pickle():
    documents = ["wireless bluetooth headphones audio", "wired headphones music audio", "cotton casual shirt apparel", "running shoes mesh footwear"]
    embeddings = LocalLSAEmbeddings().fit(documents)
    original = embeddings.embed_documents(documents)
    restored = LocalLSAEmbeddings(json.loads(json.dumps(embeddings.state())))
    assert np.asarray(original) == pytest.approx(np.asarray(restored.embed_documents(documents)))
    assert np.linalg.norm(original, axis=1) == pytest.approx(np.ones(4))
    assert not np.any(restored.embed_query("qzxwunmatched"))
    assert np.all(np.isfinite(restored.embed_query("headphones")))
    assert len(original[0]) < len(embeddings.state()["vocabulary"])


def test_documents_preserve_facts_and_chunk_long_descriptions(seeded_engine):
    with Session(seeded_engine) as session:
        product = ProductOutput.model_validate(session.get(Product, "P001"))
    product.description = "breathable trail endurance running shoes " * 100
    docs = product_documents(product, chunk_size=300)
    assert len(docs) > 5
    assert len({doc.id for doc in docs}) == len(docs)
    for doc in docs:
        assert "Price: INR 2499.00" in doc.page_content
        assert "Availability: in stock" in doc.page_content
        assert doc.metadata["price_cents"] == 249900
        assert doc.metadata["product_id"] == "P001"
    assert any("Bluetooth" in doc.page_content for doc in docs)


def test_persistent_index_idempotence_and_reopening(indexed):
    engine, store = indexed
    with Session(engine) as session:
        first = store.status(session)
        assert first["status"] == "ready" and first["indexed_chunks"] == 24
        repeated = store.ingest(session)
        assert repeated["unchanged"] == 24 and repeated["added"] == 0
        assert repeated["generation"] == first["generation"]
        reopened = RagStore(store.settings)
        assert reopened.status(session)["generation"] == first["generation"]
        result = search_products(session, reopened, RagSearchRequest(query="wireless headphones under INR 3000"))
        assert result.items[0].product.id == "P001"
        assert result.items[0].product.price == Decimal("2499")
        assert result.generation == "deterministic_fallback" and not result.llm_used
        assert not result.llm_attempted
        assert result.references == [item.product.id for item in result.items]
        assert "[P001]" in result.answer and "2499.00" in result.answer
        assert session.scalar(select(func.count()).select_from(Recommendation)) == 0


def test_native_metadata_filters_and_product_deduplication(indexed):
    result = retrieve(indexed, query="SoundNest headphones", brand="soundnest", category="ELECTRONICS", min_price="2499", max_price="2499", source="synthetic_demo")
    assert result.references == ["P001"]
    assert result.metadata_filter["$and"]
    for item in result.items:
        assert item.product.available and item.metadata["price_cents"] == 249900
        assert item.product.brand == "SoundNest"
    assert retrieve(indexed, query="headphones", product_ids=["P001"]).references == ["P001"]
    assert retrieve(indexed, query="headphones", source="missing").items == []
    assert retrieve(indexed, query="headphones", max_price="1").items == []
    assert retrieve(indexed, query="headphones under 2499").items == []
    assert retrieve(indexed, query="headphones up to 2499").references == ["P001"]
    out_of_stock = retrieve(indexed, query="wired headphones", available_only=False, product_ids=["P004"])
    assert out_of_stock.references == ["P004"] and not out_of_stock.items[0].product.available


def test_empty_unknown_queries_and_customer_context(indexed):
    assert retrieve(indexed, query="qzxwunmatched").items == []
    assert retrieve(indexed, query="the and").items == []
    response = retrieve(indexed, query="wireless headphones", customer_id="C001", channel="mobile")
    assert response.profile.interaction_count == 8 and response.profile.channel == "mobile"
    assert all(item.product.price <= 3000 for item in response.items)
    assert all("affinity" in item.explanation for item in response.items)
    budget_only = retrieve(indexed, query="under INR 1000")
    assert budget_only.items and all(item.product.price < 1000 for item in budget_only.items)


def test_stale_records_are_excluded_until_partial_update(indexed):
    engine, store = indexed
    with Session(engine) as session:
        product = session.get(Product, "P001")
        product.price = Decimal("2799")
        product.stock_quantity = 0
        session.commit()
        assert store.status(session)["stale_product_ids"] == ["P001"]
        result = search_products(session, store, RagSearchRequest(query="wireless headphones", available_only=False))
        assert "P001" not in result.references
        assert any("differs" in warning for warning in result.warnings)
        updated = store.ingest(session, ["P001"])
        assert updated["updated"] == 1 and updated["unchanged"] == 23
        result = search_products(session, store, RagSearchRequest(query="wireless headphones", available_only=False, product_ids=["P001"]))
        assert result.items[0].product.price == Decimal("2799")
        assert not result.items[0].product.available
        assert "INR 2799.00" in result.answer
        assert store.status(session)["status"] == "ready"


def test_index_delete_preserves_catalog_and_full_sync_restores_it(indexed):
    engine, store = indexed
    store.delete_product("P001")
    assert "P001" not in retrieve(indexed, query="wireless headphones").references
    with Session(engine) as session:
        assert session.get(Product, "P001") is not None
        assert store.status(session)["missing_product_ids"] == ["P001"]
        report = store.ingest(session)
        assert report["added"] == 1 and report["products"] == 24
        assert len(store._client().list_collections()) == 1
    assert "P001" in retrieve(indexed, query="wireless headphones").references


def test_last_product_delete_reopens_store_and_removes_vectors(seeded_engine, tmp_path):
    settings = Settings(_env_file=None, rag_directory=tmp_path / "single_product_index")
    store = RagStore(settings)
    with Session(seeded_engine) as session:
        store.ingest(session, ["P001"])
    reopened = RagStore(settings)
    assert reopened.client is None
    assert reopened.delete_product("P001")["products"] == 0
    assert len(reopened._client().list_collections()) == 0
    with Session(seeded_engine) as session:
        assert reopened.status(session)["indexed_chunks"] == 0


def test_deleted_catalog_record_is_pruned_on_full_sync(indexed):
    engine, store = indexed
    with Session(engine) as session:
        original = session.get(Product, "P001")
        extra = Product(id="P099", **{column.name: getattr(original, column.name) for column in Product.__table__.columns if column.name != "id"})
        session.add(extra)
        session.commit()
        store.ingest(session, ["P099"])
        session.delete(extra)
        session.commit()
        assert store.status(session)["deleted_catalog_product_ids"] == ["P099"]
        assert "P099" not in search_products(session, store, RagSearchRequest(query="headphones", product_ids=["P099"])).references
        report = store.ingest(session)
        assert report["deleted"] == 1 and report["products"] == 24


def test_failed_vector_write_preserves_previous_published_index(indexed):
    from langchain_chroma import Chroma
    engine, store = indexed
    with Session(engine) as session:
        original = store.load()["generation"]
        session.get(Product, "P001").price = Decimal("2599")
        session.commit()
        with patch.object(Chroma, "add_documents", side_effect=RuntimeError("injected write failure")):
            with pytest.raises(RuntimeError, match="injected"):
                store.ingest(session)
        assert store.load()["generation"] == original
        assert store.status(session)["indexed_chunks"] == 24
        assert len(store._client().list_collections()) == 1


def test_corrupt_retrieved_document_is_never_displayed(indexed):
    engine, store = indexed
    with store.locked():
        state = store.load()
        collection = store._client().get_collection(state["collection"], embedding_function=None)
        document = next(doc for doc in store.documents(state) if doc.metadata["product_id"] == "P001")
        vectors = collection.get(ids=[document.id], include=["embeddings"])["embeddings"].tolist()
        collection.update(ids=[document.id], documents=["Invented price INR 1.00"], embeddings=vectors)
    response = retrieve(indexed, query="wireless headphones")
    assert "P001" not in response.references
    assert "Invented price" not in response.answer
    assert any("grounding" in warning for warning in response.warnings)
    with Session(engine) as session:
        store.ingest(session, force=True)
    assert "P001" in retrieve(indexed, query="wireless headphones").references


def test_final_grounding_validator_rejects_price_and_document_tampering(indexed):
    engine, store = indexed
    response = retrieve(indexed, query="wireless headphones")
    with Session(engine) as session:
        current = {p.id: ProductOutput.model_validate(p) for p in session.scalars(select(Product))}
    docs = {doc.id: doc for doc in store.documents(store.load())}
    validate_grounding(response.items, current, docs)
    altered = response.items[0].model_copy(deep=True)
    altered.product.price = Decimal("1")
    with pytest.raises(ValueError, match="facts differ"):
        validate_grounding([altered], current, docs)
    altered = response.items[0].model_copy(deep=True)
    altered.document = "invented"
    with pytest.raises(ValueError, match="document differs"):
        validate_grounding([altered], current, docs)


def test_forced_demo_never_calls_openai_even_with_key(indexed):
    from pydantic import SecretStr
    _, store = indexed
    store.settings = store.settings.model_copy(update={"rag_generation_mode": "auto", "demo_mode": "true", "openai_api_key": SecretStr("test-only")})
    with patch("retailrag.rag.select_with_openai", side_effect=AssertionError("External AI forbidden")):
        response = retrieve(indexed, query="wireless headphones")
    assert response.items and not response.llm_attempted and not response.llm_used


def test_missing_key_and_llm_transport_or_invalid_selection_fall_back(indexed):
    _, store = indexed
    store.settings = store.settings.model_copy(update={"rag_generation_mode": "openai", "openai_api_key": None})
    with patch("retailrag.rag.select_with_openai") as select_mock:
        missing = retrieve(indexed, query="wireless headphones")
        select_mock.assert_not_called()
    assert missing.llm_status == "missing_credentials" and not missing.llm_attempted
    from pydantic import SecretStr
    store.settings = store.settings.model_copy(update={"openai_api_key": SecretStr("test-only-never-sent")})
    for failure in [httpx.ConnectError("offline"), ValueError("ungrounded")]:
        with patch("retailrag.rag.select_with_openai", side_effect=failure):
            response = retrieve(indexed, query="wireless headphones")
        assert response.references == missing.references
        assert response.llm_attempted and not response.llm_used
        assert response.generation == "deterministic_fallback"


def test_optional_llm_valid_selection_only_reorders_grounded_records(indexed):
    _, store = indexed
    from pydantic import SecretStr
    store.settings = store.settings.model_copy(update={"rag_generation_mode": "openai", "openai_api_key": SecretStr("test-only")})
    def reverse(settings, query, items, limit):
        return list(reversed(items))
    with patch("retailrag.rag.select_with_openai", side_effect=reverse):
        response = retrieve(indexed, query="wireless headphones", max_price="3000")
    assert response.llm_used and response.llm_attempted and response.llm_status == "used"
    assert response.generation == "llm_assisted"
    assert response.references == ["P003", "P001"]
    assert response.items[0].rank == 1 and response.items[0].product.price == Decimal("1799")


def test_openai_request_contract_and_invalid_id_rejection(indexed):
    from pydantic import SecretStr
    response = retrieve(indexed, query="wireless headphones", max_price="3000")
    settings = indexed[1].settings.model_copy(update={"openai_api_key": SecretStr("fake-test-key")})
    body = {"status": "completed", "output": [{"type": "message", "content": [{"type": "output_text", "text": json.dumps({"product_ids": ["P003"]})}]}]}
    http_response = httpx.Response(200, json=body, request=httpx.Request("POST", "https://api.openai.com/v1/responses"))
    with patch("retailrag.rag_generation.httpx.post", return_value=http_response) as post:
        selected = select_with_openai(settings, "headphones", response.items, 5)
    assert selected[0].product.id == "P003"
    payload = post.call_args.kwargs["json"]
    assert payload["store"] is False
    assert payload["text"]["format"]["schema"]["properties"]["product_ids"]["items"]["enum"] == ["P001", "P003"]
    body["output"][0]["content"][0]["text"] = json.dumps({"product_ids": ["INVENTED"]})
    invalid = httpx.Response(200, json=body, request=httpx.Request("POST", "https://api.openai.com/v1/responses"))
    with patch("retailrag.rag_generation.httpx.post", return_value=invalid), pytest.raises(ValueError, match="Ungrounded"):
        select_with_openai(settings, "headphones", response.items, 5)
    for value in [[], {"product_ids": ["P001", "P001"]}, {"product_ids": ["P001"], "invented_price": 1}]:
        body["output"][0]["content"][0]["text"] = json.dumps(value)
        invalid = httpx.Response(200, json=body, request=httpx.Request("POST", "https://api.openai.com/v1/responses"))
        with patch("retailrag.rag_generation.httpx.post", return_value=invalid), pytest.raises(ValueError):
            select_with_openai(settings, "headphones", response.items, 5)
