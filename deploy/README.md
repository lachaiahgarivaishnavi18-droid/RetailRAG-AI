# Deployment preparation — no services have been deployed

## Architecture and verified entrypoints

- Existing Python package: `src/retailrag/`. It contains both the frontend and backend; there was no separate JavaScript application.
- Existing frontend: `src/retailrag/frontend.py` (Streamlit), with `context_cart_ui.py` and `dashboard_ui.py`.
- Existing backend: `src/retailrag/api.py`, ASGI application `retailrag.api:app`.
- New additive frontend: `frontend/` (Next.js / TypeScript), independently deployable to Vercel.
- Backend liveness: **GET `/health`**. Database readiness: **GET `/ready`**. `/` is not an implemented API landing page and can return 404 normally.
- Vector readiness: **GET `/rag/status`**. `/ready` checks the database connection, not catalog population or vector readiness.

The new frontend uses the exact existing routes: GET `/products`, `/customers`, `/recommendations`, `/recommendations/{id}`, `/analytics/overview`, `/ready`; POST `/rag/search`, `/recommendations`, `/agents/run`. The gateway also allows selected supporting GET routes in `frontend/lib/proxy.mjs`. FastAPI schemas remain authoritative and its statuses/validation errors pass through.

```text
Browser → Next.js on Vercel → same-origin /api/backend/* gateway
                                      ↓ HTTPS
                         Existing FastAPI on a Python host
                                      ↓
                 Persistent disk: SQLite + full Chroma directory

Retained Streamlit → existing FastAPI (separate optional Python web service)
```

## Minimal-change storage decision

Keep SQLite and local Chroma together on one durable backend disk, with one Uvicorn worker and one backend instance. The example `deploy/render.yaml` uses a paid Python service and a 1 GB disk mounted at `/var/data`. Review disk size and service plan against measured usage before provisioning. Disk-backed services are not equivalent to automatically scalable stateless replicas.

Backend environment:

```dotenv
RETAILRAG_ENVIRONMENT=production
RETAILRAG_DATABASE_URL=sqlite:////var/data/retailrag.db
RETAILRAG_RAG_DIRECTORY=/var/data/chroma
RETAILRAG_RAG_COLLECTION=retailrag_products
RETAILRAG_RAG_CHUNK_SIZE=1000
RETAILRAG_RAG_GENERATION_MODE=deterministic
```

The SQLite URL has four slashes because `/var/data/retailrag.db` is absolute. Preserve **all** database tables, including customers, interactions, recommendation items/snapshots, workflow/agent history, import audits, simulation records, and tool invocations. Do not recreate history from CSVs. Neither build nor startup commands run the demo importer or Chroma ingestion.

Chroma requires `vectors/` **and** `retailrag_products.json`, including local LSA vocabulary, IDF, components, product snapshots, and generation state. They form one consistent backup. Never copy only the vector database or switch embedding models as part of this deployment.

Managed PostgreSQL/remote Chroma are optional later migrations, not prerequisites for this disk-backed approach. Object storage alone is not a substitute for Chroma's writable local filesystem. Vercel Functions do not supply the persistent disk required by the existing backend.

## Staged deployment plan (future actions only)

1. Review and commit source/assets, retaining `.env`, databases, Chroma files, caches, `.runtime`, and dependency folders outside Git. Current application source has not been replaced. Do not push secrets or backup archives.
2. Create consistent backups of the existing SQLite database and the **entire** Chroma directory while backend writes/index updates are paused. Use SQLite's backup API rather than copying an active WAL database file alone. Record counts and archive checksums. Preserve the local originals.
3. Review `deploy/render.yaml` and the provider's current pricing. Later import it using the repository root and Blueprint path `deploy/render.yaml`. `autoDeployTrigger: off` disables commit-triggered deploys; importing a Blueprint can still create resources and cause an initial deployment. No import has been performed here.
4. Before exposing traffic, restore backups into a **new versioned directory** on the persistent disk, such as `/var/data/releases/first-import/`. Do not overwrite an existing database or index. Startup can create an empty default database, so a successful `/ready` response does not prove that restoration happened.
5. Set the backend database URL and RAG directory to that restored release directory. Verify the exact database counts and foreign keys, index readiness/generation, representative filtered RAG queries, Linux/native-index compatibility, historical snapshots, and tool/agent traces. Keep the original index backup if a separately built Linux index is needed; do not silently overwrite it.
6. Configure HTTPS and access controls at the backend edge before production. The existing FastAPI app has no authentication, and public callers could otherwise invoke catalog writes, index ingestion/deletion, tools, agents, and simulations directly. The restricted Next.js gateway is **not** a backend authentication layer. An authenticated edge/reverse proxy must forward authorized requests to the unchanged app. If that edge requires machine credentials, a compatible server-side integration must be added/tested before production; none is fabricated here.
7. Optionally host the retained Streamlit app with `deploy/streamlit.render.yaml`. Set `RETAILRAG_API_BASE_URL` to a reachable backend origin. Include repository assets. Its health check is `/_stcore/health`; it does not need a second copy of the business database because it uses HTTP APIs. Keep it restricted until access controls are verified.
8. Create a Vercel project later with **Root Directory `frontend`**, Framework **Next.js**, Node **24.x**. Enable access to source files outside the Root Directory in Vercel project settings so the asset preparation script can read `../assets/product_images/`. Install/build commands are in `frontend/vercel.json`; no Python functions or databases are deployed to Vercel.
9. Set server-side `BACKEND_API_URL=https://YOUR-BACKEND-ORIGIN` with no path prefix, query, credentials, or trailing API route. Set optional `STREAMLIT_APP_URL=https://YOUR-STREAMLIT-ORIGIN`. Keep `ENABLE_SAVED_GENERATION=false` initially. Missing or production-localhost backend configuration fails explicitly with HTTP 503; it never falls back to a fake catalog.
10. Protect the Vercel preview, verify read-only browsing/RAG/history/photos and restart persistence, then enable `ENABLE_SAVED_GENERATION=true` only after authentication/access controls are effective. Run write acceptance against a staging copy, not the original production history. Generation creates real records; inspect history after timeouts before retrying.
11. Promote only after the original 209 Python tests, frontend tests, typecheck/build, external HTTPS connectivity, access controls, and restart/restore checks pass. Compare all migrated record counts and keep a rollback target. No production acceptance or deployment success is claimed by local preparation checks.

## Vercel gateway behavior

The browser calls its own `/api/backend/...` routes, avoiding a CORS change in FastAPI. A fixed server-side upstream and allowlist prevent arbitrary proxying. Client cookies/authorization headers are not forwarded; redirects and response caching are disabled. Cross-origin POST requests are rejected. RAG search is allowed because it does not save recommendation history (but optional configured LLM use can still incur provider cost). Saving recommendations/agent workflows is disabled by default. The gateway does not expose product mutations, tool execution, simulations, index ingestion/deletion, or settings.

This is an initial deployment frontend for dashboard/catalog discovery, RAG assistance, recommendations, agents, and history. It is **not** a replacement for every Streamlit page. The retained research workspace preserves the complete existing feature set and is linked once `STREAMLIT_APP_URL` is configured. Pagination shows up to 100 returned catalog items and 20 recent history rows; the current catalog has 24 products.

The proxy aborts at 45 seconds, under its configured 60-second function duration. Measure actual deployed latency. Long jobs must eventually use a separate worker/status flow rather than simply assuming a request completed; existing LangGraph audit snapshots do not automatically resume interrupted work.

## Data and secrets

- Only the separately hosted backend receives database paths, Chroma paths, and optional `OPENAI_API_KEY`.
- Never put secrets in `NEXT_PUBLIC_*` variables. There are no such variables in this frontend.
- `BACKEND_API_URL`, `STREAMLIT_APP_URL`, and `ENABLE_SAVED_GENERATION` are new frontend settings; they do not replace the Python `RETAILRAG_*` configuration.
- The photo build verifies original SHA-256 values and copies assets into ignored, generated `frontend/public` paths. Original photographs and their identity-checked mapping remain unchanged. No API contract is changed to add image URLs.

## Official references

- [Vercel monorepo root directory](https://vercel.com/docs/monorepos)
- [Next.js backend-for-frontend pattern](https://nextjs.org/docs/app/guides/backend-for-frontend)
- [Render persistent disks](https://render.com/docs/disks)
- [Render Blueprint specification](https://render.com/docs/blueprint-spec)
- [Vercel SQLite persistence limitation](https://vercel.com/kb/guide/is-sqlite-supported-in-vercel)
