from unittest.mock import patch

from fastapi.testclient import TestClient
from pydantic import SecretStr

from retailrag.api import create_app
from retailrag.config import Settings
from retailrag.local import available_port, prepare
from retailrag.database import build_engine
from retailrag.models import Product, Customer, DatasetImport
from sqlalchemy import select, func
from sqlalchemy.orm import Session


def test_ai_mode_resolves_without_mandatory_credentials():
    settings = Settings(_env_file=None, openai_api_key=None)
    assert not settings.use_real_ai
    assert settings.database_url.startswith("sqlite:")
    assert settings.model_copy(update={"openai_api_key": SecretStr("test-only")}).use_real_ai
    assert not settings.model_copy(update={"openai_api_key": SecretStr("test-only"), "demo_mode": "true"}).use_real_ai


def test_document_upload_sample_chat_and_restart(tmp_path):
    settings = Settings(_env_file=None, database_url="sqlite:///:memory:",
                        document_database=tmp_path / "docs.db", demo_mode="true")
    with patch("httpx.post", side_effect=AssertionError("External calls forbidden")):
        with TestClient(create_app(settings)) as client:
            assert client.get("/documents").json() == {"items": []}
            assert client.post("/documents/sample").status_code == 200
            sample = client.post("/documents/search", json={"query": "How long is the return policy?"}).json()
            assert "30 days" in sample["answer"] and sample["references"]
            data = {"filename": "notes.txt", "content": "The special cobalt backpack weighs 450 grams."}
            assert client.post("/documents/upload", json=data).status_code == 200
            assert client.post("/documents/upload", json=data).status_code == 200
            assert len(client.get("/documents").json()["items"]) == 2
            found = client.post("/documents/search", json={"query": "cobalt backpack"}).json()
            assert "450 grams" in found["answer"]
            assert client.post("/documents/upload", json={"filename": "x.pdf", "content": "binary"}).status_code == 422
            assert not client.post("/documents/search", json={"query": "zzxxyyqq"}).json()["references"]
        with TestClient(create_app(settings)) as reopened:
            assert len(reopened.get("/documents").json()["items"]) == 2


def test_launcher_port_is_available():
    assert 1024 <= available_port(18000) < 18100


def test_empty_local_start_seeds_once_and_preserves_existing_data(tmp_path):
    settings = Settings(_env_file=None, database_url=f"sqlite:///{tmp_path / 'demo.db'}",
                        rag_directory=tmp_path / 'chroma', demo_mode=True)
    prepare(settings)
    prepare(settings)
    engine = build_engine(settings.database_url)
    try:
        with Session(engine) as session:
            assert session.scalar(select(func.count()).select_from(Product)) == 24
            assert session.scalar(select(func.count()).select_from(Customer)) == 8
            assert session.scalar(select(func.count()).select_from(DatasetImport)) == 1
    finally:
        engine.dispose()
