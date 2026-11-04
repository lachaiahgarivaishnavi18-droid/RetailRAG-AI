"""Audit product photos offline or restore reviewed photos from recorded sources."""

import argparse
import hashlib
import io
import json
from pathlib import Path
from urllib.parse import urlparse

import httpx
from PIL import Image, ImageOps
from sqlalchemy import select
from sqlalchemy.orm import Session

from retailrag.config import get_settings
from retailrag.database import build_engine
from retailrag.models import Product
from retailrag.product_photos import ASSET_ROOT, audit, load_manifest


def restore(root=ASSET_ROOT):
    root = Path(root).resolve()
    for record in load_manifest(root).values():
        target = (root / record["file"]).resolve()
        if not target.is_relative_to(root):
            raise ValueError("Image file must stay inside the asset directory")
        if urlparse(record["download_url"]).hostname not in {"images.pexels.com", "images.unsplash.com"}:
            raise ValueError("Only reviewed photo source hosts are supported")
        response = httpx.get(record["download_url"], timeout=30, follow_redirects=True)
        response.raise_for_status()
        if hashlib.sha256(response.content).hexdigest() != record["original_sha256"]:
            raise ValueError("Source photo changed; review the new photograph before replacing assets")
        with Image.open(io.BytesIO(response.content)) as source:
            image = ImageOps.exif_transpose(source).convert("RGB")
            image = image.crop(tuple(round(v*(image.width if i % 2 == 0 else image.height)) for i, v in enumerate(record["crop"])))
            image = ImageOps.contain(image, (960, 720), Image.Resampling.LANCZOS)
            canvas = Image.new("RGB", (960, 720), "#f5f7f9")
            canvas.paste(image, ((960-image.width)//2, (720-image.height)//2))
            output = io.BytesIO()
            canvas.save(output, "JPEG", quality=92, optimize=True)
        if hashlib.sha256(output.getvalue()).hexdigest() != record["sha256"]:
            raise ValueError("Rendered image differs from reviewed asset; retain the existing photograph")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(output.getvalue())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["audit", "restore"])
    parser.add_argument("--output", type=Path, default=Path("data/product_photo_audit.json"))
    args = parser.parse_args()
    if args.command == "restore":
        restore()
    engine = build_engine(get_settings().database_url)
    try:
        with Session(engine) as session:
            products = [{"id": p.id, "name": p.name, "category": p.category, "description": p.description} for p in session.scalars(select(Product).order_by(Product.id))]
        result = audit(products)
    finally:
        engine.dispose()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "products"}, indent=2))
    if result["missing"] or result["duplicate_photos"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
