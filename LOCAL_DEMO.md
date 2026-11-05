# Run locally without credentials

From the project folder in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e '.[dev]'
$env:DEMO_MODE='true'
.\.venv\Scripts\python.exe -m retailrag.local
```

Open the URL printed by the launcher (normally http://127.0.0.1:8514).
It starts FastAPI and Streamlit together, waits for backend readiness, chooses
available ports if the requested ones are busy, and stops its own children when
you interrupt the launcher. Active URLs are also in `.runtime/local-server.json`.
Override starting ports with `--port 8514 --api-port 8000`.

SQLite and local Chroma are used. Existing catalog/history are preserved; the
bundled 24-product synthetic dataset is imported only when the catalog is empty.
A missing catalog index is built locally. Existing indexes are not overwritten;
use Settings → Synchronize catalog documents if intentionally changing the catalog.
No PostgreSQL migration variable, cloud storage, model download, Gemini, Groq,
or AI credential is necessary. Installing Python dependencies requires internet
once; running the demo afterwards does not require an external service.

Leave DEMO_MODE=auto (default) to use the existing OpenAI selection integration
when OPENAI_API_KEY is present. `true` disables external AI even when a key exists.
`false` permits configured AI but still falls back without a key or on errors.
RETAILRAG_RAG_GENERATION_MODE=deterministic also disables external generation.
Unsupported providers are not silently called. Never paste credentials into chat.

Shopping assistant answers cite real retrieved product records. The local response
engine uses deterministic templates and evidence, not a downloaded language model.
Recommendations, comparison, analytics, tools, and LangGraph run locally.

Research workspace → Document Workspace supports upload of UTF-8 TXT, Markdown,
CSV, and JSON (2 MB maximum), sample processing, search, and document chat with
source excerpts. Documents persist separately in `data/local_documents.db`.
PDF extraction, OCR, and free-form generative reasoning are not implemented.
Document passages are quoted as data and never executed as instructions.

The existing Next.js/Vercel frontend is retained. The local launcher serves the
full-featured existing Streamlit UI so every research view stays accessible.
