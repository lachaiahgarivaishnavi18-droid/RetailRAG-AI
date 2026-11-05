# Free hosting transition — not deployed

The Vercel frontend is live, but the existing disk-backed Render configuration
cannot be used on Render Free. Do not deploy SQLite/Chroma there as authoritative
storage: the filesystem is ephemeral. The original local data stays unchanged.

## Database preparation

Supabase project: `lwbokqcbniygnqxcdhrz` (RetailRAG-AI).
Use its Session pooler URI for IPv4 connectivity, not a paid IPv4 add-on.
Keep the password private in the ignored root `.env`:

```dotenv
RETAILRAG_MIGRATION_DATABASE_URL=postgresql+psycopg://USER:URL_ENCODED_PASSWORD@POOLER_HOST:5432/postgres?sslmode=require
```

This separate variable does not switch the existing application's local database.
Never paste it into chat, commit it, or put it in a frontend variable.

```powershell
.\.venv\Scripts\python.exe -m pip install 'psycopg[binary]>=3.2,<4'
.\.venv\Scripts\python.exe deploy/migrate_postgres.py
# Only after private credentials are configured:
.\.venv\Scripts\python.exe deploy/migrate_postgres.py --apply --schema retailrag_first_import
```

The tool takes a consistent read-only SQLite backup, rejects unknown/missing
tables, creates a new schema in a PostgreSQL transaction, copies every record,
compares every field, and advances integer ID sequences. Existing destination
schemas are refused; a failed transaction rolls back. No demo seeding is used.
The schema has no grants for browser anon/authenticated roles and must not be
added to Supabase's exposed API schemas. The Python backend uses SQL directly.

Later, configure the hosted backend's PostgreSQL connection with a search path
to the verified import schema; install using `pip install '.[postgres]'`.
Do not point a running backend at the default public schema before migration.

## Remaining blockers

- Actual migration/verification requires the private connection URI. Offline
  PostgreSQL DDL tests do not verify a live server or a successful import.
- Chroma still requires a durable solution for its vectors AND LSA manifest.
  Supabase Postgres alone does not make Chroma's PersistentClient durable.
  A cache rebuilt/restored on cold start needs a tested persistent source and
  synchronization for index mutations; it is not implemented by this migration.
- Backend authentication must precede exposing record writes or index mutation.
- Render Free has limited RAM and cold starts. Measure Chroma/RAG memory and
  startup time before claiming the full workflow fits its free instance.
- Do not set Vercel BACKEND_API_URL until the hosted backend passes data,
  RAG, access-control, and restart-persistence checks. Keep saved generation off.

References: https://render.com/docs/free,
https://supabase.com/docs/guides/platform/billing-on-supabase,
https://supabase.com/docs/guides/database/connecting-to-postgres.
