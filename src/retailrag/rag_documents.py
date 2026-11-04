"""Product records become attributed, independently grounded LangChain documents."""

import hashlib
import json

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from retailrag.catalog_api import ProductOutput


def fingerprint(product: ProductOutput) -> str:
    return hashlib.sha256(json.dumps(product.model_dump(mode="json"), sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def product_documents(product: ProductOutput, chunk_size=1000) -> list[Document]:
    header = f"Product ID: {product.id}\nName: {product.name}\nCategory: {product.category}\nBrand: {product.brand}\nPrice: {product.currency} {product.price:.2f}\nAvailability: {'in stock' if product.available else 'out of stock'}\nStock quantity: {product.stock_quantity}\nSource: {product.source}\n"
    body = f"Description: {product.description}\nFeatures: {json.dumps(product.features, ensure_ascii=False)}\nAttributes: {json.dumps(product.attributes, sort_keys=True, ensure_ascii=False)}"
    splitter = RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=min(120, chunk_size // 5))
    parts = splitter.split_text(body)
    result = []
    for number, part in enumerate(parts):
        text = header + part
        digest = hashlib.sha256(text.encode()).hexdigest()
        result.append(Document(id=f"{product.id}:{number}:{digest[:12]}", page_content=text, metadata={
            "product_id": product.id, "name": product.name, "category": product.category,
            "category_key": product.category.casefold(), "brand": product.brand, "brand_key": product.brand.casefold(),
            "price_cents": int(product.price * 100), "currency": product.currency, "available": product.available,
            "stock_quantity": product.stock_quantity, "source": product.source,
            "chunk": number, "product_fingerprint": fingerprint(product), "document_hash": digest,
        }))
    return result
