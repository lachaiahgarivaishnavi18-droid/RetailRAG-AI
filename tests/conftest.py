from pathlib import Path
import shutil

import pytest
from fastapi.testclient import TestClient

from retailrag.api import create_app
from retailrag.config import Settings
from retailrag.database import build_engine, initialize_database
from retailrag.ingestion import import_directory

DEMO = Path(__file__).parents[1] / "data" / "demo"


@pytest.fixture
def engine(tmp_path):
    value = build_engine(f"sqlite:///{(tmp_path / 'test.db').as_posix()}")
    initialize_database(value)
    yield value
    value.dispose()


@pytest.fixture
def seeded_engine(engine):
    import_directory(engine, DEMO, "synthetic_demo")
    return engine


@pytest.fixture
def dataset(tmp_path):
    target = tmp_path / "csv"
    shutil.copytree(DEMO, target)
    return target


@pytest.fixture
def client(seeded_engine):
    settings = Settings(_env_file=None, environment="test", database_url=str(seeded_engine.url),
                        rag_directory=Path(seeded_engine.url.database).parent / "chroma")
    with TestClient(create_app(settings)) as value:
        yield value
