# Local preparation validation

No Vercel or Render project was created, linked, imported, or deployed. No deployment success is claimed.

## Checks actually completed

- Existing Python suite: **209 passed in 247.49 seconds**.
- New frontend tests: **6 passed** (Node built-in test runner): proxy route allowlist, upstream status/query preservation, missing/unsafe backend configuration, cross-origin/disabled writes, RAG forwarding/error redaction, and all 24 copied photo hashes.
- Next.js **16.4.5**, React **19.3.1**, Node **24.22.1**: production build passed. The build produced `/`, `/_not-found`, and `/api/backend/[...path]` routes.
- TypeScript **5.9.3**: `tsc --noEmit` passed.
- Both Render YAML examples parsed locally; auto-deploy setting is a string and health-check paths are configured. This does not substitute for provider-side Blueprint validation.
- Live production-mode Next.js preview at localhost: HTTP 200 for the page and gateway reads to `/health`, `/ready`, `/products`, `/customers`, `/recommendations`, `/analytics/overview`, `/rag/status`, and `/agents/status`.
- All **24** served frontend photo files matched the original SHA-256 digests.
- Default-disabled saved generation returned HTTP **403**, without reaching the backend write route.
- Live proxied deterministic RAG search returned **P001 / P003**, with `llm_used=false`.
- Browser inspection: actual dashboard metrics, keyword search, existing recommendation #18 with evidence/photos, desktop layout, and mobile layout (no document overflow in the inspected 390px viewport).
- Original **12 database tables**, **3 source CSVs**, and the Chroma manifest matched their prior preservation hashes. Counts remain 24 products, 8 customers, 56 interactions, 18 recommendations, 43 items, and 26 agent executions.
- Existing Python application source/configuration were not edited. All deployment/client implementation files are additive in `frontend/` and `deploy/`.

The temporary Next.js preview is stopped after validation. Existing local FastAPI and Streamlit services are retained. Generated `.next`, `node_modules`, copied public photo assets, and local test/runtime files are ignored.

## Still required before a real deployment

- Review paid backend hosting/service size and import the configuration deliberately.
- Restore a consistent SQLite + complete Chroma backup to new persistent storage; check Linux compatibility and restart persistence.
- Configure backend access controls, HTTPS, and a reachable upstream URL. The gateway does not authenticate the unchanged backend.
- Configure Vercel Root Directory `frontend`, access to repository files outside that root, environment settings, and deployment protection.
- Perform actual provider builds and staging acceptance. The local build is not a Vercel/Render deployment test.
- Enable saved generation only after access controls are verified; test writes using staging data.
