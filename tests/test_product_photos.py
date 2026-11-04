import json
import hashlib
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from streamlit.testing.v1 import AppTest

from retailrag.product_photos import ASSET_ROOT, audit, local_photo, load_manifest
from test_frontend import backend_mock, backend_post_mock

FRONTEND = Path(__file__).parents[1] / "src/retailrag/frontend.py"


def test_all_existing_products_have_unique_valid_photos_with_attribution(client):
    products = client.get("/products", params={"limit": 100}).json()["items"]
    report = audit(products)
    assert report["total_products"] == report["real_local_photos"] == 24
    assert not report["missing"] and not report["duplicate_photos"]
    assert all(p["dimensions"] == [960, 720] for p in report["products"])
    manifest = load_manifest()
    for product in products:
        row = manifest[product["id"]]
        assert row["photographer"] and row["license_url"].startswith("https://")
        assert row["source_url"].startswith(("https://www.pexels.com/photo/", "https://unsplash.com/photos/"))
        assert local_photo(product)["path"].is_file()


def test_identity_guard_and_safe_missing_image_fallback(client, tmp_path):
    product = client.get("/products/P001").json()
    assert local_photo(product)
    assert local_photo({**product, "name": "A different smartphone"}) is None
    assert local_photo({**product, "category": "Phones"}) is None
    assert local_photo({**product, "description": "A different type of product"}) is None
    assert local_photo(product, tmp_path) is None
    (tmp_path / "manifest.json").write_text("[]")
    assert local_photo(product, tmp_path) is None
    (tmp_path / "manifest.json").write_text('{"products":{"P001":null}}')
    assert local_photo(product, tmp_path) is None
    row = load_manifest()["P001"]
    for bad_path in ("../outside.jpg", str(ASSET_ROOT / row["file"])):
        (tmp_path / "manifest.json").write_text(json.dumps({"products": {"P001": {**row, "file": bad_path}}}))
        assert local_photo(product, tmp_path) is None


def test_corrupt_photo_is_not_rendered_as_a_broken_image(client, tmp_path):
    row = load_manifest()["P001"]
    fake = tmp_path / "broken.jpg"
    fake.write_bytes(b"not a photograph")
    (tmp_path / "manifest.json").write_text(json.dumps({"products": {"P001": {**row, "file": "broken.jpg", "sha256": hashlib.sha256(fake.read_bytes()).hexdigest()}}}))
    assert local_photo(client.get("/products/P001").json(), tmp_path) is None


def test_frontend_photos_across_discovery_recommendations_comparison_and_rag(client):
    client.post("/rag/ingest", json={}).raise_for_status()
    with patch("httpx.get", side_effect=backend_mock(client)), patch("httpx.post", side_effect=backend_post_mock(client)):
        app = AppTest.from_file(str(FRONTEND), default_timeout=25).run()
        assert not app.exception and len(app.get("image")) == 3
        app.sidebar.radio[0].set_value("Product Discovery").run()
        assert not app.exception and len(app.get("image")) == 9
        app.sidebar.radio[0].set_value("Product Comparison").run()
        app.multiselect[0].set_value(["P001", "P003"]).run()
        assert not app.exception and len(app.get("image")) == 2
        app.sidebar.radio[0].set_value("AI Recommendations").run()
        app.text_area[0].set_value("wireless headphones under INR 3000")
        next(b for b in app.button if b.label == "Generate Recommendations").click().run(timeout=30)
        assert not app.exception and len(app.get("image")) >= 2
        app.sidebar.radio[1].set_value("RAG Search").run()
        app.text_area[0].set_value("wireless headphones under INR 3000")
        next(b for b in app.button if b.label == "Search retrieved evidence").click().run(timeout=30)
        assert not app.exception and len(app.get("image")) >= 2
        app.sidebar.radio[1].set_value("Product Catalog").run()
        assert not app.exception and len(app.get("image")) == 6


def test_custom_product_without_photo_has_text_fallback_and_no_placeholder_icon(client):
    from retailrag.product_photos import render_product_photo
    product = client.get("/products/P001").json()
    product.update(id="CUSTOM", name="Unphotographed product", image_url=None)
    with patch("retailrag.product_photos.st.image") as image, patch("retailrag.product_photos.st.caption") as caption:
        assert render_product_photo(product) is False
        image.assert_not_called()
        caption.assert_called_once_with("Product photograph unavailable.")
