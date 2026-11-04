"""Persistable local latent-semantic embeddings implementing LangChain's contract.

No downloaded model, credentials, or pickle/joblib deserialization is needed.
This small-catalog LSA model is not a pretrained language embedding model.
"""

import numpy as np
from langchain_core.embeddings import Embeddings
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, TfidfVectorizer
from sklearn.preprocessing import normalize

from retailrag.data_schemas import normalize_search_text

STOP_WORDS = sorted(set(ENGLISH_STOP_WORDS) | {
    "inr", "name", "description", "category", "brand", "price", "features", "attributes",
    "availability", "stock", "quantity", "source", "product", "id", "synthetic", "demo",
    "recommend", "recommendations", "products", "looking",
})


class LocalLSAEmbeddings(Embeddings):
    version = "local_lsa_v1"

    def __init__(self, state: dict | None = None):
        self.vectorizer = TfidfVectorizer(preprocessor=normalize_search_text, lowercase=False,
                                         stop_words=STOP_WORDS, token_pattern=r"(?u)\b\w+\b", sublinear_tf=True)
        self.components = None
        if state is not None:
            if state.get("version") != self.version:
                raise ValueError("Unsupported embedding state version")
            self.vectorizer.set_params(vocabulary=state["vocabulary"])
            self.vectorizer.idf_ = np.asarray(state["idf"], dtype=float)
            self.components = np.asarray(state["components"], dtype=float)
            if self.components.ndim != 2 or self.components.shape[1] != len(state["idf"]) or not np.isfinite(self.components).all():
                raise ValueError("Invalid embedding state")

    def fit(self, texts: list[str]):
        matrix = self.vectorizer.fit_transform(texts)
        dimensions = min(128, max(1, matrix.shape[0] - 1), matrix.shape[1])
        if matrix.shape[0] == 1:
            self.components = normalize(matrix.toarray())
        elif matrix.shape[1] == 1:
            self.components = np.ones((1, 1))
        else:
            model = TruncatedSVD(n_components=dimensions, random_state=42)
            model.fit(matrix)
            self.components = model.components_
        return self

    def state(self) -> dict:
        return {"version": self.version, "vocabulary": self.vectorizer.vocabulary_,
                "idf": self.vectorizer.idf_.tolist(), "components": self.components.tolist()}

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if self.components is None:
            raise ValueError("Embedding model is not fitted")
        matrix = self.vectorizer.transform(texts)
        vectors = normalize(np.asarray(matrix @ self.components.T))
        return vectors.tolist()

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]
