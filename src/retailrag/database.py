"""Engine lifecycle and non-destructive table initialization."""

from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.pool import StaticPool

from retailrag.models import Base


def build_engine(database_url: str) -> Engine:
    url = make_url(database_url)
    options = {"pool_pre_ping": True}
    if url.get_backend_name() == "sqlite":
        options["connect_args"] = {"check_same_thread": False, "timeout": 15}
        if url.database in (None, "", ":memory:"):
            options["poolclass"] = StaticPool
        else:
            Path(url.database).resolve().parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(url, **options)
    if url.get_backend_name() == "sqlite":
        @event.listens_for(engine, "connect")
        def sqlite_pragmas(connection, _):
            cursor = connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()
    return engine


def initialize_database(engine: Engine) -> None:
    # Creates missing tables only; never drops tables or rewrites existing records.
    Base.metadata.create_all(engine)
