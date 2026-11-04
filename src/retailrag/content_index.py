"""Local TF-IDF/cosine retrieval. Fresh per request to avoid stale catalog vectors."""

import numpy as np
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from retailrag.data_schemas import normalize_search_text
from retailrag.models import Product


def product_document(product: Product) -> str:
    return normalize_search_text(" ".join([
        product.name, product.name, product.description, product.category, product.brand,
        *product.features, *product.attributes.keys(), *product.attributes.values(),
        f"{product.price:.2f}",
    ]))


class ContentIndex:
    def __init__(self, products: list[Product]):
        self.products = products
        self.positions = {p.id: i for i, p in enumerate(products)}
        self.vectorizer = TfidfVectorizer(
            preprocessor=normalize_search_text, lowercase=False, strip_accents=None,
            stop_words=sorted(set(ENGLISH_STOP_WORDS) | {"inr", "recommend", "recommendation", "recommendations", "products", "looking"}),
            token_pattern=r"(?u)\b\w+\b", ngram_range=(1, 2), sublinear_tf=True,
        )
        self.matrix = None
        if products:
            try:
                self.matrix = self.vectorizer.fit_transform([product_document(p) for p in products])
            except ValueError as exc:
                if "empty vocabulary" not in str(exc):
                    raise

    def query_scores(self, query: str) -> np.ndarray:
        if self.matrix is None or not query.strip():
            return np.zeros(len(self.products))
        vector = self.vectorizer.transform([query])
        return np.clip(cosine_similarity(vector, self.matrix).ravel(), 0, 1)

    def similar_scores(self, product_id: str) -> np.ndarray:
        if product_id not in self.positions:
            raise LookupError("Product not found")
        if self.matrix is None:
            return np.zeros(len(self.products))
        return np.clip(cosine_similarity(self.matrix[self.positions[product_id]], self.matrix).ravel(), 0, 1)

    def preference_scores(self, affinities: dict[str, float], declared_text: str) -> np.ndarray:
        if self.matrix is None:
            return np.zeros(len(self.products))
        declared = self.vectorizer.transform([declared_text])
        weights = np.array([affinities.get(p.id, 0) for p in self.products])
        if weights.sum():
            centroid = np.asarray(self.matrix.multiply(weights[:, None]).sum(axis=0)) / weights.sum()
            if declared.nnz:
                centroid = 0.7 * centroid + 0.3 * declared.toarray()
        else:
            centroid = declared
        return np.clip(cosine_similarity(centroid, self.matrix).ravel(), 0, 1)
