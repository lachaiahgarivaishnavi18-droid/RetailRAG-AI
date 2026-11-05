"""Offline guards for the deployment migration; live copy needs private credentials."""
import importlib.util
from pathlib import Path

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from retailrag.models import Base

spec = importlib.util.spec_from_file_location(
    "migration", Path(__file__).resolve().parents[1] / "deploy/migrate_postgres.py")
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)


def test_postgres_schema_preserves_every_table_and_foreign_key():
    metadata = migration.destination_metadata("retailrag_test_release")
    assert len(metadata.tables) == len(Base.metadata.tables) == 12
    for table in metadata.sorted_tables:
        original = Base.metadata.tables[table.name]
        assert list(table.columns.keys()) == list(original.columns.keys())
        assert len(table.constraints) == len(original.constraints)
        ddl = str(CreateTable(table).compile(dialect=postgresql.dialect()))
        assert f"retailrag_test_release.{table.name}" in ddl
        for foreign_key in table.foreign_keys:
            assert foreign_key.column.table.schema == "retailrag_test_release"
    assert all(t.schema is None for t in Base.metadata.tables.values())


@pytest.mark.parametrize("schema", ["public", "auth", "storage", "retailrag_x; DROP SCHEMA public", "RetailRAG"])
def test_migration_rejects_nonrelease_or_unsafe_schema_before_connecting(schema):
    with pytest.raises(ValueError):
        migration.copy_rows(None, None, schema)
