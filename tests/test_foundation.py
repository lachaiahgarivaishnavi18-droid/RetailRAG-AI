import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from retailrag.api import create_app
from retailrag.config import Settings


def test_health_without_credentials(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    settings = Settings(_env_file=None, environment="test", database_url="sqlite:///:memory:")
    with TestClient(create_app(settings)) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok", "application": "RetailRAG AI", "version": "0.1.0",
        "environment": "test", "phase": 14,
    }


def test_openapi_documents_health():
    with TestClient(create_app(Settings(_env_file=None, database_url="sqlite:///:memory:"))) as client:
        assert "/health" in client.get("/openapi.json").json()["paths"]


def test_environment_configuration(monkeypatch):
    monkeypatch.setenv("RETAILRAG_APP_NAME", "Test Store")
    assert Settings(_env_file=None).app_name == "Test Store"


@pytest.mark.parametrize("values", [
    {"environment": "invalid"}, {"api_base_url": "not-a-url"},
])
def test_invalid_configuration(values):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **values)
