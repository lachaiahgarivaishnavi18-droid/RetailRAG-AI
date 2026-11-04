import json
from datetime import timezone
from decimal import Decimal

import pandas as pd
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from conftest import DEMO
from retailrag.data_schemas import ProductInput
from retailrag.ingestion import DataImportError, database_summary, import_directory, read_dataset
from retailrag.models import Customer, CustomerInteraction, DatasetImport, Product


def edit_csv(directory, table, column, value):
    path = directory / f"{table}.csv"
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    frame.loc[0, column] = value
    frame.to_csv(path, index=False)


def test_demo_ingestion_and_idempotence(engine):
    first = import_directory(engine, DEMO, "synthetic_demo")
    second = import_directory(engine, DEMO, "synthetic_demo")
    assert {k: v["inserted"] for k, v in first["tables"].items()} == {"products": 24, "customers": 8, "interactions": 56}
    assert all(v["inserted"] == 0 for v in second["tables"].values())
    assert {k: v["skipped_existing"] for k, v in second["tables"].items()} == {"products": 24, "customers": 8, "interactions": 56}
    with Session(engine) as session:
        summary = database_summary(session)
        assert summary["counts"]["recommendations"] == 0
        assert summary["counts"]["agent_executions"] == 0
        assert summary["sources"]["products"] == {"synthetic_demo": 24}
        assert summary["last_import"]["report"] == second
        product = session.get(Product, "P001")
        assert product.price == Decimal("2499.00")
        assert product.attributes["connectivity"] == "Bluetooth"
        assert "usb c" in product.search_text
        assert not session.get(Product, "P004").available
        assert session.get(Customer, "C008").interactions == []
        event = session.get(CustomerInteraction, "I0001")
        assert event.occurred_at.tzinfo == timezone.utc
        assert event.product.id == "P001" and event.customer.id == "C001"


@pytest.mark.parametrize("table,column,value", [
    ("products", "price", "-1"), ("products", "price", "NaN"),
    ("products", "price", "1.234"), ("products", "stock_quantity", "-1"),
    ("products", "rating", "6"), ("products", "rating", "inf"),
    ("products", "name", "   "), ("products", "currency", "USD"),
    ("products", "features", "invalid-json"), ("products", "attributes", "[]"),
    ("products", "image_url", "javascript:alert(1)"), ("products", "id", "../unsafe"),
    ("customers", "budget_min", "9000"), ("customers", "budget_max", ""),
    ("interactions", "channel", "real_store"), ("interactions", "event_type", "clickbait"),
    ("interactions", "quantity", "0"), ("interactions", "occurred_at", "2026-10-01T09:00:00"),
])
def test_bad_rows_reject_entire_import(engine, dataset, table, column, value):
    edit_csv(dataset, table, column, value)
    with pytest.raises(DataImportError, match="row 2"):
        import_directory(engine, dataset)
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(Product)) == 0
        assert session.scalar(select(func.count()).select_from(DatasetImport)) == 0


def test_unknown_foreign_key_rolls_back_all_tables(engine, dataset):
    edit_csv(dataset, "interactions", "product_id", "MISSING")
    with pytest.raises(DataImportError, match="unknown customer or product"):
        import_directory(engine, dataset)
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(Product)) == 0
        assert session.scalar(select(func.count()).select_from(Customer)) == 0


def test_conflicts_preserve_existing_data(seeded_engine, dataset):
    edit_csv(dataset, "products", "price", "1.00")
    with pytest.raises(DataImportError, match="conflicts"):
        import_directory(seeded_engine, dataset, "synthetic_demo")
    with Session(seeded_engine) as session:
        assert session.get(Product, "P001").price == Decimal("2499.00")
        assert session.scalar(select(func.count()).select_from(DatasetImport)) == 1


def test_duplicate_rows_are_deduplicated_but_conflicting_ids_fail(engine, dataset):
    path = dataset / "products.csv"
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    pd.concat([frame, frame.iloc[:1]]).to_csv(path, index=False)
    result = import_directory(engine, dataset)
    assert result["tables"]["products"]["duplicates_removed"] == 1
    frame.loc[1, "id"] = frame.loc[0, "id"]
    frame.to_csv(path, index=False)
    with pytest.raises(DataImportError, match="conflicting duplicate ID"):
        import_directory(engine, dataset)


def test_normalization_preserves_product_facts(dataset):
    edit_csv(dataset, "products", "name", "  Wireless   Everyday\tHeadphones  ")
    edit_csv(dataset, "products", "features", json.dumps([" wireless ", "wireless", "USB-C"]))
    rows, _ = read_dataset(dataset / "products.csv", ProductInput)
    assert rows[0]["name"] == "Wireless Everyday Headphones"
    assert rows[0]["features"] == ["wireless", "USB-C"]
    assert rows[0]["price"] == Decimal("2499.00")


def test_missing_file_and_unknown_columns_fail(engine, dataset):
    with pytest.raises(DataImportError, match="Cannot read"):
        import_directory(engine, dataset / "missing")
    edit_csv(dataset, "products", "unrecognized", "value")
    with pytest.raises(DataImportError, match="unknown columns"):
        import_directory(engine, dataset)


def test_malformed_csv_cannot_shift_columns(engine, dataset):
    path = dataset / "products.csv"
    lines = path.read_text(encoding="utf-8").splitlines()
    lines[1] += ",unexpected"
    path.write_text("\n".join(lines), encoding="utf-8")
    with pytest.raises(DataImportError, match="unexpected number of columns"):
        import_directory(engine, dataset)
