"""RAG API routes. No implicit ingestion or LLM calls on application startup."""

from fastapi import APIRouter, Depends, HTTPException, Request

from retailrag.catalog_api import get_session
from retailrag.rag_schemas import RagIngestRequest, RagResponse, RagSearchRequest

router = APIRouter(prefix="/rag", tags=["RAG"])


def get_store(request: Request):
    return request.app.state.rag_store


@router.get("/status")
def status(session=Depends(get_session), store=Depends(get_store)):
    try:
        return store.status(session)
    except Exception:
        raise HTTPException(503, "RAG index is unavailable; check its directory, permissions, and manifest") from None


@router.post("/ingest")
def ingest(request: RagIngestRequest, session=Depends(get_session), store=Depends(get_store)):
    try:
        return store.ingest(session, request.product_ids, force=request.force)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from None
    except Exception:
        raise HTTPException(503, "RAG ingestion failed; the previously published index was preserved") from None


@router.delete("/products/{product_id}")
def delete_product(product_id: str, store=Depends(get_store)):
    try:
        return store.delete_product(product_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from None
    except Exception:
        raise HTTPException(503, "RAG index deletion failed; check the index directory") from None


@router.post("/search", response_model=RagResponse)
def search(request: RagSearchRequest, session=Depends(get_session), store=Depends(get_store)):
    from retailrag.rag import search_products
    try:
        return search_products(session, store, request)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from None
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    except Exception:
        raise HTTPException(503, "RAG search is unavailable; check index status and re-ingest if necessary") from None
