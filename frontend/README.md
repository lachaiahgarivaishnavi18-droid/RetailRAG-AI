# Context Cart Vercel frontend — preparation only

An additive Next.js / TypeScript client for the existing RetailRAG FastAPI API. The original Streamlit app and all Python implementation/data are retained. Nothing has been deployed.

See [the deployment plan](../deploy/README.md) for API routes, persistent storage, restore/access-control requirements, Vercel settings, and optional Streamlit hosting. Vercel project root: **`frontend`**. Include source files outside that root for the original photo assets.

## Local Windows PowerShell

Install Node 24 and pnpm 11.25.0 if they are not already available. From the repository root:

```powershell
# Terminal 1: unchanged backend, using your existing database/index
.\.venv\Scripts\python.exe -m uvicorn retailrag.api:app --host 127.0.0.1 --port 8000

# Terminal 2
Set-Location frontend
pnpm install --frozen-lockfile
$env:BACKEND_API_URL = 'http://127.0.0.1:8000'
$env:STREAMLIT_APP_URL = 'http://127.0.0.1:8501'
$env:ENABLE_SAVED_GENERATION = 'false'
pnpm dev
```

Open the printed local frontend URL (normally `http://127.0.0.1:3000`). Alternatively copy `.env.example` to `.env.local` **only if `.env.local` does not already exist**, and configure it there. Production requires an HTTPS backend; localhost is rejected when `VERCEL` is set.

The retained Streamlit command, in another terminal at repository root:

```powershell
.\.venv\Scripts\python.exe -m streamlit run src/retailrag/frontend.py --server.address 127.0.0.1
```

## Checks

```powershell
pnpm test
pnpm build
pnpm typecheck
```

Build prepares 24 verified photographs from the original asset folder without editing them, generates a local photo mapping, and runs the Next.js production build/type checks. Keep the lockfile committed. Tests use Node's built-in test runner and do not need a paid service or deployment. No live saved recommendation/agent request is required to build the frontend.

`GET /api/backend/ready` checks the configured upstream database connection. `GET /api/backend/health` checks its liveness. An unconfigured backend produces a real 503 message. Read-only history browsing never generates another recommendation. Existing FastAPI validation errors remain visible.
# Free Vercel cloud demo

When BACKEND_API_URL is absent, this frontend serves a clearly labeled read-only
demo from the bundled synthetic CSV snapshot: 24 products, sample activity,
keyword browsing, and lexical shopping answers with budget/stock filters.
No API key, database credentials, or local server is needed for this mode.
History is empty; saved recommendations and LangGraph execution are disabled.
Document upload and full Chroma/LangGraph functionality remain in the retained
local Python application. Set BACKEND_API_URL to switch to the real backend,
or VERCEL_DEMO_MODE=false to require a configured backend instead of the demo.

