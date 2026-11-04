"""Atomic, persistent Chroma generations with an accompanying safe JSON LSA state."""

import json
import os
import re
import uuid
from datetime import datetime, timezone

from filelock import FileLock
from sqlalchemy import select

from retailrag.catalog_api import ProductOutput
from retailrag.rag_documents import fingerprint, product_documents
from retailrag.rag_embeddings import LocalLSAEmbeddings


class RagIndexError(RuntimeError):
    pass


class RagStore:
    def __init__(self, settings):
        self.settings = settings
        self.directory = settings.rag_directory.resolve()
        self.manifest = self.directory / f"{settings.rag_collection}.json"
        self.client = None
        self._cached = None

    def locked(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        return FileLock(str(self.directory / f"{self.settings.rag_collection}.lock"), timeout=30)

    def _client(self):
        if self.client is None:
            import chromadb
            from chromadb.config import Settings
            self.client = chromadb.PersistentClient(path=str(self.directory / "vectors"), settings=Settings(anonymized_telemetry=False))
        return self.client

    def load(self):
        if not self.manifest.exists():
            return None
        try:
            state = json.loads(self.manifest.read_text(encoding="utf-8"))
            generation = state["generation"]
            if state["version"] != 1 or not re.fullmatch(r"[a-f0-9]{32}", generation):
                raise ValueError("Invalid generation")
            expected = f"{self.settings.rag_collection}_{generation}" if state["products"] else None
            if state["collection"] != expected:
                raise ValueError("Invalid collection")
            for key, value in state["products"].items():
                if ProductOutput.model_validate(value).id != key:
                    raise ValueError("Invalid product snapshot")
            return state
        except (ValueError, KeyError, TypeError, AttributeError, OSError) as exc:
            raise RagIndexError("RAG index manifest is unreadable or incompatible; restore it or configure a fresh index directory") from exc

    def documents(self, state):
        return [doc for key in sorted(state["products"]) for doc in product_documents(
            ProductOutput.model_validate(state["products"][key]), state["chunk_size"])]

    def vectorstore(self, state):
        if self._cached is None or self._cached[0] != state["generation"]:
            try:
                from langchain_chroma import Chroma
                embeddings = LocalLSAEmbeddings(state["embeddings"])
                store = Chroma(collection_name=state["collection"], embedding_function=embeddings,
                               client=self._client(), create_collection_if_not_exists=False)
            except Exception as exc:
                raise RagIndexError("Cannot open the published vector collection or its embedding state") from exc
            self._cached = (state["generation"], store, embeddings)
        return self._cached[1], self._cached[2]

    def _publish(self, products, old):
        from langchain_chroma import Chroma
        generation = uuid.uuid4().hex
        collection = f"{self.settings.rag_collection}_{generation}" if products else None
        state = {"version": 1, "generation": generation, "collection": collection,
                 "products": products, "chunk_size": self.settings.rag_chunk_size,
                 "updated_at": datetime.now(timezone.utc).isoformat(), "embeddings": None, "chunk_count": 0}
        temporary = self.manifest.with_suffix(f".{generation}.tmp")
        created = False
        try:
            docs = self.documents(state)
            if docs:
                embeddings = LocalLSAEmbeddings().fit([doc.page_content for doc in docs])
                store = Chroma(collection_name=collection, embedding_function=embeddings, client=self._client(),
                               collection_metadata={"hnsw:space": "cosine"})
                created = True
                # Chroma upserts real persisted embeddings through the LangChain adapter.
                for offset in range(0, len(docs), 100):
                    batch = docs[offset:offset + 100]
                    store.add_documents(batch, ids=[doc.id for doc in batch])
                if self._client().get_collection(collection, embedding_function=None).count() != len(docs):
                    raise RagIndexError("Index write verification failed")
                state["embeddings"], state["chunk_count"] = embeddings.state(), len(docs)
            with temporary.open("w", encoding="utf-8") as stream:
                json.dump(state, stream, ensure_ascii=False, allow_nan=False)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.manifest)
        except Exception:
            if temporary.exists():
                temporary.unlink()
            if created:
                self._client().delete_collection(collection)
            raise
        self._cached = None
        cleanup_warnings = []
        # All our reads/writes take the same process-safe lock, so retired generations
        # can be removed after publication without invalidating an active reader.
        if self.client is not None or (old and old.get("collection")):
            try:
                for candidate in self._client().list_collections():
                    name = candidate.name if hasattr(candidate, "name") else str(candidate)
                    prefix = self.settings.rag_collection + "_"
                    if name.startswith(prefix) and re.fullmatch(r"[a-f0-9]{32}", name[len(prefix):]) and name != collection:
                        self.client.delete_collection(name)
            except Exception:
                cleanup_warnings.append("A retired vector generation could not be removed; the new active index is ready.")
        return state, cleanup_warnings

    def ingest(self, session, product_ids=None, *, force=False):
        from retailrag.models import Product
        current = {p.id: ProductOutput.model_validate(p).model_dump(mode="json") for p in session.scalars(select(Product).order_by(Product.id))}
        if product_ids is not None and set(product_ids) - current.keys():
            raise LookupError("One or more requested products do not exist")
        with self.locked():
            try:
                old = self.load()
            except RagIndexError:
                if not force or product_ids is not None:
                    raise
                old = None
            previous = old["products"] if old else {}
            target = current.copy() if product_ids is None else {key: value for key, value in previous.items() if key in current}
            if product_ids is not None:
                target.update({key: current[key] for key in product_ids})
            added = len(target.keys() - previous.keys())
            deleted = len(previous.keys() - target.keys())
            updated = sum(previous[key] != target[key] for key in target.keys() & previous.keys())
            unchanged = len(target) - added - updated
            if old and not force and not (added or deleted or updated) and old["chunk_size"] == self.settings.rag_chunk_size:
                # Confirm the persisted collection exists even for an idempotent ingest.
                if old["collection"]:
                    self.vectorstore(old)
                    if self._client().get_collection(old["collection"], embedding_function=None).count() != old["chunk_count"]:
                        raise RagIndexError("Index count differs from its manifest; configure a fresh index directory")
                state, warnings = old, []
            else:
                state, warnings = self._publish(target, old)
            return {"status": "ready" if target else "empty", "generation": state["generation"],
                    "products": len(target), "chunks": state["chunk_count"], "added": added, "updated": updated,
                    "deleted": deleted, "unchanged": unchanged, "warnings": warnings}

    def delete_product(self, product_id):
        with self.locked():
            old = self.load()
            if old is None or product_id not in old["products"]:
                raise LookupError("Product is not present in the vector index")
            products = {key: value for key, value in old["products"].items() if key != product_id}
            state, warnings = self._publish(products, old)
            return {"deleted_product_id": product_id, "products": len(products), "chunks": state["chunk_count"],
                    "generation": state["generation"], "warnings": warnings}

    def status(self, session):
        from retailrag.models import Product
        current = {p.id: ProductOutput.model_validate(p) for p in session.scalars(select(Product))}
        with self.locked():
            state = self.load()
            indexed = state["products"] if state else {}
            missing = sorted(current.keys() - indexed.keys())
            removed = sorted(indexed.keys() - current.keys())
            stale = sorted(key for key in current.keys() & indexed.keys() if fingerprint(current[key]) != fingerprint(ProductOutput.model_validate(indexed[key])))
            actual_chunks = 0
            if state and state["collection"]:
                self.vectorstore(state)
                actual_chunks = self._client().get_collection(state["collection"], embedding_function=None).count()
                if actual_chunks != state["chunk_count"]:
                    raise RagIndexError("Vector index count does not match its manifest; re-ingest into a fresh directory")
            return {"status": "not_ingested" if state is None else "stale" if missing or removed or stale else "ready" if indexed else "empty",
                    "embedding": LocalLSAEmbeddings.version, "generation": state["generation"] if state else None,
                    "catalog_products": len(current), "indexed_products": len(indexed), "indexed_chunks": actual_chunks,
                    "updated_at": state["updated_at"] if state else None, "missing_product_ids": missing,
                    "deleted_catalog_product_ids": removed, "stale_product_ids": stale,
                    "generation_mode": self.settings.rag_generation_mode,
                    "llm_configured": bool(self.settings.openai_api_key and self.settings.openai_api_key.get_secret_value().strip())}
