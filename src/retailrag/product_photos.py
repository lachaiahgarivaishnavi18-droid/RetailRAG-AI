"""Local, attributed product photography without changing catalog/RAG records."""

import hashlib
import json
from functools import lru_cache
from pathlib import Path

from PIL import Image, UnidentifiedImageError
import streamlit as st

ASSET_ROOT = Path(__file__).resolve().parents[2] / "assets" / "product_images"


def load_manifest(root=None):
    root = Path(root) if root is not None else ASSET_ROOT
    try:
        data = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        return data["products"] if isinstance(data, dict) and isinstance(data.get("products"), dict) else {}
    except (OSError, ValueError, KeyError):
        return {}


@lru_cache(maxsize=256)
def valid_image(path, modified_ns, size, expected_digest):
    try:
        if hashlib.sha256(Path(path).read_bytes()).hexdigest() != expected_digest:
            return False
        with Image.open(path) as image:
            image.verify()
        return True
    except (OSError, ValueError, UnidentifiedImageError):
        return False


def local_photo(product, root=None):
    """ID plus identity guard prevents reused IDs from inheriting unrelated photos."""
    root = (Path(root) if root is not None else ASSET_ROOT).resolve()
    record = load_manifest(root).get(product.get("id"))
    if not isinstance(record, dict) or any(record.get(key) != product.get(key) for key in ("name", "category")):
        return None
    if "description" in product and record.get("description") != product["description"]:
        return None
    try:
        path = (root / record["file"]).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            return None
        stat = path.stat()
        if not valid_image(str(path), stat.st_mtime_ns, stat.st_size, record["sha256"]):
            return None
        return {**record, "path": path}
    except (OSError, KeyError, TypeError, ValueError):
        return None


def render_product_photo(product, *, detail=False):
    photo = local_photo(product)
    if photo:
        st.image(str(photo["path"]), width="stretch", caption=photo["alt"] if detail else None)
        if detail:
            st.caption(f"Representative stock photograph; fictional catalog brand. Photo: {photo['photographer']}.")
            st.link_button("Photo source & license", photo["source_url"], icon=":material/photo_library:")
        return True
    if product.get("image_url"):
        # Preserve custom catalog image URLs, but never substitute another product's image.
        st.image(product["image_url"], width="stretch")
        return True
    st.caption("Product photograph unavailable.")
    return False


def audit(products, root=None):
    """Offline coverage, identity, unique-file and decode verification."""
    root = Path(root) if root is not None else ASSET_ROOT
    matched, missing, hashes, paths = [], [], set(), set()
    duplicates = []
    for product in products:
        photo = local_photo(product, root)
        if photo is None:
            missing.append(product["id"])
            continue
        with Image.open(photo["path"]) as image:
            dimensions = list(image.size)
        if photo["sha256"] in hashes or str(photo["path"]) in paths:
            duplicates.append(product["id"])
        hashes.add(photo["sha256"])
        paths.add(str(photo["path"]))
        matched.append({"id": product["id"], "file": photo["file"], "dimensions": dimensions,
                        "sha256": photo["sha256"], "source_url": photo["source_url"]})
    return {"total_products": len(products), "real_local_photos": len(matched), "missing": missing,
            "duplicate_photos": duplicates, "products": matched}
