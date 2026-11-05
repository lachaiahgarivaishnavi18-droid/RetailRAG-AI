"""Validated environment configuration shared by both entry points."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, HttpUrl, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="RETAILRAG_", env_file=".env", extra="ignore", populate_by_name=True
    )

    app_name: str = "RetailRAG AI"
    environment: Literal["development", "test", "production"] = "development"
    api_base_url: HttpUrl = "http://127.0.0.1:8000"
    database_url: str = "sqlite:///./data/retailrag.db"
    rag_directory: Path = Path("data/chroma")
    document_database: Path = Path("data/local_documents.db")
    rag_collection: str = Field(default="retailrag_products", pattern=r"^[a-z][a-z0-9_]{2,60}$")
    rag_chunk_size: int = Field(default=1000, ge=300, le=5000)
    rag_generation_mode: Literal["auto", "deterministic", "openai"] = "auto"
    demo_mode: Literal["auto", "true", "false"] = Field(default="auto", validation_alias=AliasChoices("DEMO_MODE", "RETAILRAG_DEMO_MODE"))
    rag_openai_model: str = Field(default="gpt-4.1-mini", min_length=1)
    rag_llm_timeout: float = Field(default=15, gt=0, le=60)
    openai_api_key: SecretStr | None = Field(default=None, validation_alias="OPENAI_API_KEY")

    @field_validator("demo_mode", mode="before")
    @classmethod
    def normalize_demo_mode(cls, value):
        return str(value).lower()

    @property
    def use_real_ai(self) -> bool:
        return self.demo_mode != "true" and self.rag_generation_mode != "deterministic" and bool(
            self.openai_api_key and self.openai_api_key.get_secret_value().strip())


@lru_cache
def get_settings() -> Settings:
    return Settings()
