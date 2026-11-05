"""Local text document upload and extractive chat. No hosted embeddings or model."""
import hashlib
from pathlib import Path
import sqlite3
import re
from contextlib import contextmanager

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

router = APIRouter(prefix="/documents", tags=["Local documents"])
SAMPLE = """RetailRAG demonstration store policy
Returns: Unused products can be returned within 30 days with the original receipt.
Delivery: Standard shipping takes 3 to 5 business days. Express shipping takes 1 to 2 business days.
Warranty: Electronics include a one year warranty covering manufacturing defects.
Support: Store support is available Monday to Saturday, 9 AM to 6 PM.
These policies are synthetic examples for local demonstrations, not actual retailer terms.
"""


class Upload(BaseModel):
    filename: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=2_000_000)


class Question(BaseModel):
    query: str = Field(min_length=1, max_length=2000)


@contextmanager
def connection(request):
    path = request.app.state.config.document_database.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=15)
    try:
        db.execute("CREATE TABLE IF NOT EXISTS documents (id TEXT PRIMARY KEY, filename TEXT NOT NULL, content TEXT NOT NULL)")
        yield db
        db.commit()
    finally:
        db.close()


@router.get("")
def listing(request: Request):
    with connection(request) as db:
        return {"items": [{"id": r[0], "filename": r[1], "characters": r[2]} for r in db.execute("SELECT id, filename, length(content) FROM documents ORDER BY filename, id")]}


@router.post("/upload")
def upload(payload: Upload, request: Request):
    name = Path(payload.filename.replace("\\", "/")).name
    if Path(name).suffix.lower() not in {".txt", ".md", ".csv", ".json"} or not payload.content.strip() or "\x00" in payload.content:
        raise HTTPException(422, "Upload nonempty UTF-8 text, Markdown, CSV, or JSON. Binary/PDF documents are not supported.")
    identity = hashlib.sha256((name + "\n" + payload.content).encode()).hexdigest()
    with connection(request) as db:
        db.execute("INSERT OR IGNORE INTO documents VALUES (?, ?, ?)", (identity, name, payload.content))
    return {"id": identity, "filename": name, "characters": len(payload.content), "status": "processed"}


@router.post("/sample")
def sample(request: Request):
    return upload(Upload(filename="demo-store-policy.txt", content=SAMPLE), request)


@router.post("/search")
def search(payload: Question, request: Request):
    with connection(request) as db:
        rows = db.execute("SELECT id, filename, content FROM documents ORDER BY id").fetchall()
    chunks = []
    for identity, name, content in rows:
        passages = [line.strip() for line in content.splitlines() if line.strip()]
        for passage in passages:
            for offset in range(0, len(passage), 700):
                chunks.append((identity, name, len(chunks) + 1, passage[offset:offset + 900]))
    if not chunks:
        return {"mode": "local_demo", "answer": "Upload a document or process the sample first.", "references": []}
    try:
        # Minimal local plural normalization matches "return" to "returns".
        plurals = {"returns": "return", "products": "product", "documents": "document", "policies": "policy", "warranties": "warranty"}
        normalize = lambda value: re.sub(r"\b\w+\b", lambda match: plurals.get(match[0], match[0]), value.lower())
        matrix = TfidfVectorizer(stop_words="english", preprocessor=normalize).fit_transform([c[3] for c in chunks] + [payload.query])
        scores = cosine_similarity(matrix[-1], matrix[:-1])[0]
    except ValueError:
        scores = [0] * len(chunks)
    hits = sorted(zip(scores, chunks), key=lambda item: -item[0])[:3]
    refs = [{"document_id": c[0], "filename": c[1], "chunk": c[2], "excerpt": c[3], "score": round(float(score), 6)}
            for score, c in hits if score > 0.05]
    answer = "Local demo answer — relevant passages from your documents:\n\n" + "\n\n".join(f"[{r['filename']}, chunk {r['chunk']}] {r['excerpt']}" for r in refs) if refs else "I couldn't find supporting information in your documents. Try a more specific question."
    return {"mode": "local_demo", "answer": answer, "references": refs}
