"""FastAPI entry point with managed database lifecycle."""

from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from retailrag import __version__
from retailrag.catalog_api import router
from retailrag.config import Settings, get_settings
from retailrag.database import build_engine, initialize_database
from retailrag.recommendation_api import router as recommendation_router
from retailrag.rag_api import router as rag_router
from retailrag.rag_store import RagStore
from retailrag.workflow_api import router as workflow_router
from retailrag.tool_api import router as tool_router
from retailrag.omnichannel import router as omnichannel_router
from retailrag.analytics import router as analytics_router
from retailrag.documents import router as documents_router


class HealthResponse(BaseModel):
    status: Literal["ok"]
    application: str
    version: str
    environment: str
    phase: int


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings if settings is not None else get_settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        engine = build_engine(config.database_url)
        try:
            initialize_database(engine)
            application.state.engine = engine
            application.state.rag_store = RagStore(config)
            yield
        finally:
            engine.dispose()

    application = FastAPI(
        title=config.app_name,
        version=__version__,
        description="Retail catalog, TF-IDF recommendations, persistent Chroma RAG, and auditable deterministic LangGraph workflows. Standalone RAG can use explicitly configured optional LLM selection.",
        lifespan=lifespan,
    )
    application.state.config = config
    application.include_router(documents_router)
    application.include_router(router)
    application.include_router(recommendation_router)
    application.include_router(rag_router)
    application.include_router(workflow_router)
    application.include_router(tool_router)
    application.include_router(omnichannel_router)
    application.include_router(analytics_router)

    @application.get("/settings", tags=["Configuration"])
    def public_settings():
        from sqlalchemy.engine import make_url
        return {"demo_mode": not config.use_real_ai, "document_engine": "local_tfidf", "app_name": config.app_name, "environment": config.environment,
                "database_backend": make_url(config.database_url).get_backend_name(),
                "rag_directory": str(config.rag_directory), "rag_collection": config.rag_collection,
                "rag_generation_mode": config.rag_generation_mode, "rag_embedding": "local_lsa_v1",
                "rag_openai_model": config.rag_openai_model, "rag_chunk_size": config.rag_chunk_size,
                "llm_credentials_configured": bool(config.openai_api_key and config.openai_api_key.get_secret_value().strip()),
                "workflow_generation": "deterministic_agents", "tool_llm_calls_enabled": False,
                "stock_scope": "catalog", "channels": ["ecommerce", "mobile", "store"]}

    @application.get("/ready", tags=["Health"])
    def readiness():
        from sqlalchemy import text
        try:
            with application.state.engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            return {"status": "ready", "database": "ok", "rag_initialization": "explicit_ingestion_required", "credentials_required": False}
        except SQLAlchemyError:
            return JSONResponse(status_code=503, content={"status": "unavailable", "database": "unavailable"})

    @application.exception_handler(SQLAlchemyError)
    async def database_error(request, exc):
        return JSONResponse(status_code=503, content={"detail": "Database operation failed; check the connection and schema"})

    @application.get("/health", response_model=HealthResponse, tags=["Health"])
    def health() -> HealthResponse:
        return HealthResponse(
            status="ok", application=config.app_name, version=__version__,
            environment=config.environment, phase=14,
        )

    return application


app = create_app()
