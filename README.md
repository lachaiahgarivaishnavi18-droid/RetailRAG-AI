# Context Cart — RetailRAG AI

An agentic retrieval-augmented architecture for context-aware product recommendations in omnichannel retail.

## Current delivery: Phases 1–14 complete

The existing data, database, ML, RAG, LangGraph, and eleven public tools are preserved. The completed local application adds atomic three-channel shopping simulation, shared customer preferences, database-derived analytics, catalog management, readiness/configuration endpoints, and a responsive Streamlit dashboard with Plotly charts, product cards, and light/dark styling. Tools and workflows require no credentials and never call an LLM; standalone RAG retains its separately configured optional selector. This is a functioning local research/demo application; the limitations below describe the boundary to production deployment.

The latest full regression suite, including local product photography, passed **209 tests in 241.79 seconds**. A separate end-to-end acceptance run exercised real database writes, Chroma retrieval, ten LangGraph nodes, tool execution, simulation replay, analytics, and persistence across application restart. Its actual outputs are in [data/final_acceptance.json](data/final_acceptance.json). See the phases 7–14 delivery report below for commands and scope.

## Context Cart frontend redesign

The Streamlit frontend is branded **Context Cart**. Existing Python package names, FastAPI contracts, database schema, LangGraph agents, RAG pipeline, and backend application identity remain unchanged. There is no JavaScript frontend, `package.json`, TypeScript compiler, or separate frontend build.

The navy sidebar provides Dashboard, Product Discovery, AI Shopping Assistant, Recommendations, Product Comparison, Inventory & Store Availability, Evaluation Dashboard, Settings, and About. Expand **Research workspace** for the original catalog editor, Customer Context, RAG Search, Agent Workflow, Omnichannel Analytics, Tool Explorer, and Recommendation History. Native controls retain keyboard operation, visible labels, collapsible navigation, mobile stacking, and reduced-motion styling.

The dashboard shows real product/category/recommendation totals, trending products from recorded interactions, recent recommendations, and calculated evidence summaries. Active sessions are explicitly marked **Not tracked** because no session analytics endpoint exists. Product Discovery supports category, brand, rating, price, stock, sorting, pagination, natural-language retrieval, details, and comparison. It fetches all catalog pages before local facet filtering; natural-language retrieval is limited to the backend's 20 candidates. Untouched price controls preserve budgets parsed from the query. All 24 bundled products now have unique local stock photographs. Generic product illustrations have been removed; genuinely unavailable photographs use a text fallback.

The assistant renders chat bubbles, product explanations and document citations using the existing `/rag/search` API. There is no dedicated chat endpoint or model conversation memory; each question is independent. Messages, comparison selections, displayed recommendation scores, and client round-trip latency measurements last for the current Streamlit browser session. A page render or comparison action never repeats a submitted query. Recommendation generation/history and every existing research integration remain functional.

Comparison supports up to four current catalog products, with prices, brands, ratings, specifications, features, stock, and scores where generated in the session. Inventory is global catalog stock, with no store-level stock feed. Evaluation shows actual recommendation ranking scores, index readiness, persisted workflow durations, and successful assistant request latency. **Precision@K, Recall@K, MRR, and NDCG@K are unavailable**: there is no evaluation API or labeled relevance benchmark, and model scores cannot substitute for these measurements.

Implementation is in `src/retailrag/context_cart_ui.py`, `frontend.py`, `dashboard_ui.py`, and `.streamlit/config.toml`, with no added dependencies. Regression coverage includes all original frontend flows plus six tests for new pages, evidence-backed assistant responses, comparison, dashboard routing, natural-language budgets, rating filters, and honest evaluation fallback. Desktop and mobile browser layouts were inspected; mobile Product Discovery measured a 390px page width with no document overflow. Dashboard checks at 768px, 1280px, and 1440px also showed no document overflow. After final icon-accessibility and metric-wrapping refinements, all **22 frontend tests passed in 63.69 seconds**. Source compilation and live backend/Streamlit health checks passed. The working database still holds 24 products, 8 customers, 56 interactions, and 18 recommendation runs. The redesigned app is running on port 8501 with the original backend on port 8000.

```powershell
.\.venv\Scripts\python.exe -m pytest -q --tb=short -x --basetemp=.test-tmp/context-cart-full -o cache_dir=.test-tmp/cache --junitxml=.test-tmp/context-cart-tests.xml
```

## Local product photography

A full recursive project inventory checked **412 JSON files, 865 CSV files, and 1,839 database files**, including ignored dependency, test, and runtime folders. No 120-product catalog was found. The authoritative database at `data/retailrag.db`, source CSV at `data/demo/products.csv`, and Chroma manifest at `data/chroma/retailrag_products.json` each contain **24 products**. Generated test catalogs contain 0, 23, 24, or 25 products. One intentionally corrupt test manifest is unreadable. No missing products were invented. Findings are recorded in [data/product_dataset_inventory.json](data/product_dataset_inventory.json).

**Coverage: 24 of 24 products have real, unique local photographs**, with no missing files or duplicated image hashes. Assets are organized under `assets/product_images/{category}/Pxxx-product-name.jpg`. All are normalized to 960×720 JPEGs, using visually reviewed crops and proportional padding to retain the subject. The shared renderer uses responsive 4:3 image frames with `object-fit: contain`. The complete asset directory is approximately 2.7 MB.

Photos were downloaded from Pexels and Unsplash under their respective free-use platform licenses. See [photographer credits and source/license links](assets/product_images/CREDITS.md). The catalog's brands/products are fictional; these are representative stock photographs of corresponding product types, not authenticated manufacturer SKU photos. Visible third-party marks do not establish affiliation with the fictional brands. Names, prices, ratings, stock, specifications, and recommendation evidence remain the authoritative catalog facts. Product details identify the photographs as representative and expose the original source link.

`assets/product_images/manifest.json` maps IDs, names, categories, and descriptions to local image paths, photographer attribution, source/license URLs, reviewed crop coordinates, and source/rendered SHA-256 digests. `product_photos.py` validates identity, path containment, file integrity, and image decoding before display. Reusing an ID for a different name/category/description does not inherit the old product's photo. Local photographs are used in dashboard/discovery cards, details, recommendations, comparison, assistant responses, the original catalog, and RAG results, including historical recommendation snapshots. Product rows and CSV image fields remain unchanged, so no Chroma re-ingestion is needed.

Normal use makes no image-provider requests for the bundled products. If a mapped asset is missing/corrupt or a new product has no photo, the renderer preserves any explicit custom catalog image URL; otherwise it displays **Product photograph unavailable.** It never borrows a different product's image or inserts an emoji/placeholder illustration.

Offline coverage audit:

```powershell
.\.venv\Scripts\python.exe -m retailrag.photo_cli audit --output data/product_photo_audit.json
```

Restore reviewed assets from recorded sources if necessary (requires network; refuses changed source content or a rendered image differing from the reviewed hash):

```powershell
.\.venv\Scripts\python.exe -m retailrag.photo_cli restore
```

Keep the checked-in JPEGs as the primary assets. A changed image encoder version or provider file may require a new manual visual review before its hashes can be updated. To add future products, curate a distinct matching licensed photo, retain attribution, and add a reviewed mapping entry; do not use random-image endpoints.

Preservation was checked by comparing fingerprints for all **12 database tables**, the three source CSVs, and the Chroma manifest. They are unchanged; [data/product_photo_preservation.json](data/product_photo_preservation.json) records counts/hashes. [data/product_photo_audit.json](data/product_photo_audit.json) records all 24 image checks. Browser verification loaded all 24 catalog photos across three pages (9/9/6) from local `/media/` URLs at 960×720. The focused image/frontend suite passed **27 tests in 100.18 seconds**. Coverage includes identity mismatch, traversal, missing/corrupt assets, text fallback, and real API-backed image rendering across discovery, comparison, recommendations, RAG search, and the original catalog.

Full regression: **209 passed in 241.79 seconds**, including existing database, recommendation, Chroma, LangGraph, and tool tests. Syntax compilation and live application health checks passed. The frontend is running with the local photograph assets; the backend API contracts are unchanged.

```powershell
.\.venv\Scripts\python.exe -m pytest -q --tb=short -x --basetemp=.test-tmp/product-photos-full -o cache_dir=.test-tmp/cache --junitxml=.test-tmp/product-photos-tests.xml
```

The bundled dataset is **entirely synthetic**: 24 fictional products across 6 categories, 8 demo customers (one without history), and 56 interactions across e-commerce, mobile, and store channels. All names, brands, prices, ratings, specifications, and stock counts in these files are examples, not real retailer data. There are no external retail integrations.

## Architecture and stack

Streamlit calls FastAPI over HTTP; API routes use short-lived SQLAlchemy sessions. SQLite is the default local database. Pandas loads CSV files, Pydantic validates them, and an atomic transaction inserts normalized records. Scikit-learn builds local TF-IDF vectors; NumPy and cosine similarity support ranking against the current catalog and customer history. Both entry points share configuration loaded from environment variables and optional `.env`. HTTPX handles requests, Uvicorn serves FastAPI, and pytest plus Streamlit AppTest verify the application. Python 3.11–3.13 is supported.

For RAG, LangChain Documents and its recursive splitter prepare attributed chunks; a custom LangChain Embeddings implementation fits local LSA vectors. The LangChain Chroma adapter persists/query vectors. A process-safe file lock and atomically replaced JSON manifest keep the embedding state, product snapshots, and active vector generation aligned.

LangGraph's compiled StateGraph coordinates the Phase 5 role agents. Typed JSON-safe state passes between nodes; LangChain StructuredTool contracts validate inputs/outputs. Each started node creates an actual AgentExecution row, linked to its workflow run through an additive association table. Tools use short-lived sessions, while final validation and recommendation persistence run together in one transaction.

Phase 6 shares the StructuredTool registration/audit implementation across the internal workflow and public retail interfaces. The public API accepts only identifiers and validated recommendation/filter requests, loads authoritative facts from the existing services/database, checks results, and persists an invocation record. Recommendation writes and their completed audit/result are committed atomically; a unique idempotency key prevents duplicate saves.

```text
src/retailrag/
  __init__.py       Package version
  config.py         Validated runtime settings
  api.py            FastAPI application factory and database lifecycle
  database.py       Engine configuration and table initialization
  models.py         Tables, relationships, indexes, and constraints
  omnichannel.py    Atomic synthetic shopping journeys and shared channel context
  analytics.py      UTC-filtered metrics from real database records
  analytics_schemas.py   Typed analytics response contracts
  dashboard_ui.py   Plotly charts, product cards, catalog editor, simulator, themes
  acceptance.py     Isolated end-to-end verification and evidence export
  data_schemas.py   Validation and normalization contracts
  ingestion.py      CSV preprocessing, atomic import, provenance
  data_cli.py       Database initialization/import/status commands
  catalog_api.py    Catalog, customer, interaction, and status routes
  content_index.py  TF-IDF product documents and cosine similarities
  preferences.py    Cross-channel customer profile analysis
  recommendation_schemas.py   Validated requests, weights, and results
  recommendation_context.py   Conservative INR/context parsing
  recommendations.py         Filtering, ranking, explanations, persistence
  recommendation_api.py      Generation, history, and preference routes
  examples.py       Generate actual saved examples from demo records
  rag_documents.py  Attributed product documents and chunk metadata
  rag_embeddings.py Local LSA LangChain embeddings and safe JSON state
  rag_store.py      Persistent Chroma generations and synchronization
  rag.py            Retrieval, re-ranking, and grounding validation
  rag_generation.py Deterministic rendering and constrained optional LLM selection
  rag_schemas.py    Validated RAG requests and evidence responses
  rag_api.py        RAG status/ingest/search/index deletion endpoints
  rag_cli.py        Index management and actual retrieval example export
  workflow_schemas.py      Typed state, request, item, output, and audit schemas
  workflow_tools.py        Validated LangChain tools and actual invocation auditing
  workflow_validation.py   Independent final grounding/constraint/arithmetic checks
  workflow_persistence.py  Atomic recommendation save and persisted run reads
  workflow.py              Ten-node LangGraph construction, execution, and tracing
  workflow_api.py          Run, definition, status, and detail endpoints
  workflow_cli.py          Run/inspect workflows and export actual examples
  tool_registry.py        Shared LangChain schemas, registration, summaries, and digests
  tool_schemas.py         Public ID/request-based input/output contracts
  retail_tools.py         Eleven actual retail tool implementations
  tool_validation.py     Independent tool-output grounding checks
  tool_service.py        Durable execution and idempotent atomic saves
  tool_api.py            Tool discovery/execution/invocation history endpoints
  tool_cli.py            Tool discovery, execution, inspection, and actual examples
  frontend.py       Overview, Catalog, Context, Recommendations, RAG, Agents, Tools, History, Settings
data/demo/          Synthetic CSVs: products, customers, interactions
data/phase3_examples.json     Actual generated recommendation examples
data/phase4_examples.json     Actual Chroma retrieval examples
data/phase5_examples.json     Actual LangGraph execution examples
data/phase6_examples.json     Actual public tool results and idempotent save retry
data/chroma/                 Generated vector storage/manifest (Git-ignored)
tests/
  conftest.py
  test_*.py         Foundation, database, ingestion, CLI, API, and UI tests
.env.example
pyproject.toml
```

## Windows PowerShell setup

Install Python 3.11 with the Python launcher, then run from this directory:

```powershell
Set-Location 'C:\Users\ADMIN\Documents\ChatGPT\RetailRAG AI 3'
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e '.[dev]'
Copy-Item .env.example .env
```

Copy `.env.example` only on first setup; preserve any existing `.env`. Virtual environment activation is optional; these commands work without changing PowerShell execution policy. `.env`, local environments, caches, and generated databases are excluded from Git.

If this workspace already has `.venv`, keep it and update dependencies with:

```powershell
.\.venv\Scripts\python.exe -m pip install -e '.[dev]'
```

## Database setup and data loading

Run from the repository root. The default SQLite file is `data/retailrag.db`; its parent directory and missing tables are created automatically. Startup does not seed data. Load the demo explicitly:

```powershell
.\.venv\Scripts\python.exe -m retailrag.data_cli init
.\.venv\Scripts\python.exe -m retailrag.data_cli demo
.\.venv\Scripts\python.exe -m retailrag.data_cli status
```

`demo` imports `data/demo` with source `synthetic_demo`. Repeating it skips identical existing rows. Custom datasets must contain all three CSV files:

```powershell
.\.venv\Scripts\python.exe -m retailrag.data_cli import --directory 'C:\RetailData' --source 'local_catalog_v1'
```

Imports validate all files before writing. Unknown customer/product references, malformed CSV, invalid fields, or conflicting IDs abort the entire transaction. Exact duplicate rows within one file are deduplicated. Existing IDs must match all normalized values **and provenance**; imports never overwrite them. Successful import reports persist inserted/skipped/duplicate counts in `dataset_imports`. A repeated import adds an audit record, but no duplicate business records. Back up the database before manually changing existing data. `init` creates missing tables; it does not migrate existing table definitions or delete data. Future schema changes require explicit migrations.

### CSV contracts

Use UTF-8 (BOM accepted), comma-separated headers, and standard CSV quoting. See the bundled files for fully quoted JSON examples. Unknown/duplicate columns and malformed row widths are rejected. Optional columns may be omitted; required values cannot be blank.

| File | Required columns | Optional columns |
| --- | --- | --- |
| `products.csv` | `id,name,description,category,brand,price,stock_quantity` | `currency,rating,features,attributes,image_url` |
| `customers.csv` | `id,name,budget_max` | `preferred_categories,preferred_brands,budget_min` |
| `interactions.csv` | `id,customer_id,product_id,event_type,channel,occurred_at` | `quantity` |

- IDs: 1–64 ASCII letters, digits, underscores, or hyphens; first character must be alphanumeric.
- Price and budgets: nonnegative decimal INR amounts, at most two decimal places and ten integer digits. The application accepts INR only. `budget_max >= budget_min`.
- Ratings: finite numbers from 0 to 5. Stock: nonnegative integer; availability is derived from `stock_quantity > 0`. No availability is guessed.
- `features`, `preferred_categories`, `preferred_brands`: JSON arrays of strings. `attributes`: JSON object with string values. Empty optional JSON cells use empty arrays/objects. Image URLs are optional HTTP(S) URLs; the demo has none.
- Channels: `ecommerce`, `mobile`, `store`. Events: `view`, `purchase`, `wishlist`, `cart`. Quantity: positive integer.
- `occurred_at`: ISO 8601 timestamp **with timezone**, normalized to UTC. Example: `2026-10-01T09:00:00Z`.
- Unicode text uses NFKC normalization and collapsed whitespace. Features/preferences are deduplicated. Product facts are preserved; a separate lowercased search field combines name, description, category, brand, features, attributes, and price.

The schema includes `products`, `customers`, `customer_interactions`, `recommendations`, `recommendation_items`, `recommendation_snapshots`, `agent_executions`, `dataset_imports`, `workflow_runs`, `workflow_steps`, `tool_invocations`, and `omnichannel_simulations`. Foreign keys are enforced in SQLite. Phase 3 added recommendation snapshots; Phase 5 added workflow audit tables; Phase 6 added tool invocations; Phase 7 adds only the simulation table, with a customer foreign key, unique retry key, and indexes. Missing tables are created non-destructively on startup/init. Existing table definitions and working catalog/customer/history records are preserved. Actual node executions populate `agent_executions`; standalone public tool invocations have their own audit table.

### Optional PostgreSQL configuration

The models and engine factory also accept PostgreSQL through SQLAlchemy. Install the optional driver and set the connection string in `.env`:

```powershell
.\.venv\Scripts\python.exe -m pip install -e '.[dev,postgres]'
# In .env: RETAILRAG_DATABASE_URL=postgresql+psycopg://USER:PASSWORD@localhost:5432/retailrag
.\.venv\Scripts\python.exe -m retailrag.data_cli init
```

Create the PostgreSQL database/user yourself first. SQLite is tested locally; no PostgreSQL server has been used for verification.

## Running the application

Start the backend:

```powershell
.\.venv\Scripts\python.exe -m uvicorn retailrag.api:app --host 127.0.0.1 --port 8000
```

In a second PowerShell terminal in the same directory, start the frontend:

```powershell
.\.venv\Scripts\python.exe -m streamlit run src/retailrag/frontend.py --server.address 127.0.0.1
```

Open [the app](http://127.0.0.1:8501), [health](http://127.0.0.1:8000/health), or [API documentation](http://127.0.0.1:8000/docs).

## Configuration

`RETAILRAG_APP_NAME`, `RETAILRAG_ENVIRONMENT` (`development`, `test`, or `production`), `RETAILRAG_API_BASE_URL`, and `RETAILRAG_DATABASE_URL` configure the application. Environment variables override `.env`. Relative SQLite paths are resolved from the current working directory, so run the CLI/backend from the repository root. Restart services after configuration changes.

`OPENAI_API_KEY` is optional. Phase 3 recommendations never call an LLM. Phase 4 RAG also makes no external calls by default: set `RETAILRAG_RAG_GENERATION_MODE=openai` **and** provide a key to enable optional product-ID selection. A key alone does not enable calls. Keys are represented as secrets and never included in API responses or the UI.

## Phase 2 endpoints

| Method | Path | Behavior |
| --- | --- | --- |
| GET | `/health` | Application liveness, version, environment, phase |
| GET | `/database/status` | Live table counts, provenance totals, latest import |
| GET | `/products`, `/products/search` | Literal normalized keyword search and filters |
| GET | `/products/{product_id}` | Product details with actual stock-derived availability |
| GET | `/customers` | Paginated imported profiles |
| GET | `/customers/{customer_id}` | Profile, declared preferences, budgets, provenance |
| GET | `/customers/{customer_id}/history` | Chronological history, optional channel filter |
| POST | `/interactions` | Record a synthetic shopping interaction |

List responses have `total`, `limit`, `offset`, `items`; limits are 1–100. Product filters: `q`, `category`, `brand`, `min_price`, `max_price`, `available`. Category/brand are exact case-insensitive matches for the demo's ASCII labels. Sort: `name`, `price_asc`, `price_desc`, `rating`. Search is token matching over normalized text, not semantic retrieval. Prices serialize as decimal strings.

`POST /interactions` accepts the interaction CSV fields as JSON (quantity defaults to 1). It validates references, rejects duplicate IDs with 409, and always labels new records `synthetic_simulation`. These are historical simulation events; they do not process orders, payments, or decrement inventory. Invalid inputs return 422; missing records return 404. API database failures return a generic 503.

## Phase 3 recommendations

Update dependencies using the setup command above, start the backend/frontend, then open **AI Recommendations**. The form supports customer selection (or ID override), a shopping request, recommendation type, source product for similarity, category/brand filters, budget, stock filtering, purchase exclusion, channel, and result count. **Recommendation History** loads saved results without generating another run. **Customer Context** now includes inferred preference data. Overview recommendation counts come from the database.

No API credentials or model downloads are needed. Phase 3 explicitly reports `engine=deterministic_tfidf` and `llm_used=false`; its behavior is preserved. Chroma retrieval and grounded responses are available separately through Phase 4's RAG endpoints and page.

| Mode | Required input | Behavior |
| --- | --- | --- |
| `personalized` | `customer_id` | Declared preferences and weighted cross-channel history |
| `similar` | `product_id` | Cosine similarity within the source category by default; source excluded |
| `budget` | Price bound, or recognizable budget query | Budget-compatible catalog recommendations |
| `category` | `category` | Exact category filter with ranking |
| `brand` | `brand` | Exact brand filter with ranking |
| `new_customer` | No customer ID | Anonymous popularity/rating baseline, with optional filters |
| `context_aware` | Nonblank `query` | Lexical query relevance, conservative context rules, optional customer |

An existing customer with no history can use `personalized`; declared preferences are used when available, otherwise the popularity/rating baseline applies. `new_customer` is explicitly anonymous. Contextual category/brand inference matches whole catalog labels; multiple matching labels produce a warning and no inferred filter for that dimension. Explicit category/brand fields take precedence and always filter strictly.

### Customer preference analysis

Profiles include normalized category/brand/product affinities; declared preferences; budget bounds; event/channel counts; viewed, purchased, and wishlisted product IDs; cold-start status; and an observed purchase-price median. Event weights are view **1**, wishlist **3**, cart **4**, purchase **6**; quantity is capped at 10 for affinity calculations. Matching-channel events receive a **2×** boost, while history from every channel remains included. Declared categories/brands contribute a prior weight of **2**.

Customer text affinity uses a history-weighted product-vector centroid, blended **70% history / 30% declared preference text** when both exist. If no usable customer vector exists, the baseline is **80% normalized weighted catalog activity / 20% rating**; without any activity it uses rating alone. The observed purchase-price statistic uses **current catalog prices per purchase event**, because Phase 2 interactions did not record transaction prices. It does not override the declared budget or claim to reproduce historical spending.

### TF-IDF, filters, and ranking

Product documents combine name (weighted by repetition), description, category, brand, features, attributes, and numeric price. The vectorizer uses normalized Unicode text, English stop words, unigram/bigram features, sublinear term frequency, and cosine similarity. A fresh index is fitted to the current database catalog per generation request, so catalog edits do not leave stale vectors. Similar mode uses source-product cosine similarity, or **70% source / 30% query similarity** when both inputs are present.

Similar mode filters to the source product's category unless an explicit category override is supplied. The effective category and its source appear in `context`. It returns fewer than the requested count when too few related products meet the budget/stock filters; it does not pad the list with other categories.

The final relevance score is the weighted sum of these components, with weights renormalized across applicable signals:

| Component | Default weight | Evidence |
| --- | --- | --- |
| `text_relevance` | 0.40 | Query/source cosine similarity |
| `customer_preference` | 0.20 | Customer centroid, or disclosed cold-start baseline |
| `category_match` | 0.15 | Explicit category, source category, or profile affinity |
| `brand_match` | 0.10 | Explicit brand, source brand, or profile affinity |
| `budget_compatibility` | 0.10 | 1 within bounds; relative price compatibility outside |
| `availability` | 0.05 | Actual `stock_quantity > 0` |

Send a `weights` object to override defaults; values must be finite, between 0 and 1, and at least one positive weight must apply to the request. Scores/components and normalized active weights are returned and saved. Ties use similarity, rating, price, and product ID deterministically. These scores are ranking signals, not purchase probabilities or measured recommendation accuracy.

- `available_only=true` by default; disabling it explicitly warns that out-of-stock products can appear. Stock is catalog-wide; there is no invented per-store/channel inventory.
- `strict_budget=true` by default. Explicit numeric bounds are inclusive. Query phrases `under/below/less than` and `over/above/more than` are exclusive; `up to/at most/at least/between` are inclusive. Repeated bounds intersect using the tightest limits. Supported amounts include `INR 3000`, `₹3,000`, `Rs. 3000`, `3000 INR`, and `3k`.
- Explicit price fields override query bounds on the same side. If any price bound is explicitly supplied or parsed from the query, unspecified bounds remain open; otherwise customer profile bounds apply. Effective bounds and their sources appear in the response. Invalid or contradictory effective bounds return 422.
- `strict_budget=false` makes price a soft ranking preference and displays a warning. Category/brand filters remain strict.
- `exclude_purchased=true` removes the customer's purchased IDs; it defaults to false. Previously viewed and wishlisted products remain eligible.
- A nonempty text query must have a positive vocabulary match; out-of-vocabulary/stopword-only queries return an empty result rather than unrelated substitutes. Recognized budget phrases are removed before text matching, so a budget-only query can rank all eligible products.
- Negative-language constraints and explicit unsupported currencies are rejected with 422. This rule-based parser does not understand arbitrary language, negation, synonyms, or product suitability. Use explicit filters for precise control.

### Recommendation API

| Method | Path | Behavior |
| --- | --- | --- |
| POST | `/recommendations` | Generate, explain, and atomically save a run (201), including empty results |
| GET | `/recommendations` | Paginated history; optional `customer_id`, `channel`, `mode` filters |
| GET | `/recommendations/{recommendation_id}` | Original saved product/profile/filter/score snapshot |
| GET | `/customers/{customer_id}/preferences` | Inferred profile; optional channel weighting |

Requests also accept `query`, `customer_id`, `product_id` (similar mode only), `category`, `brand`, `min_price`, `max_price`, `strict_budget`, `available_only`, `exclude_purchased`, `channel`, `weights`, and `limit` (1–50). Unknown fields are rejected. Missing customers/source products return 404. Generation uses one atomic transaction for the recommendation, items, and full snapshot; failures leave no partial run.

PowerShell example against the running backend:

```powershell
$body = @{
    mode = 'context_aware'
    customer_id = 'C001'
    query = 'wireless headphones under INR 3000'
    channel = 'mobile'
    available_only = $true
    strict_budget = $true
    limit = 3
} | ConvertTo-Json
$result = Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8000/recommendations' -ContentType 'application/json' -Body $body
$result.items | Select-Object rank, similarity_score, relevance_score, explanation
Invoke-RestMethod 'http://127.0.0.1:8000/recommendations?customer_id=C001'
Invoke-RestMethod "http://127.0.0.1:8000/recommendations/$($result.id)"
Invoke-RestMethod 'http://127.0.0.1:8000/customers/C001/preferences?channel=mobile'
```

Saved prices, stock, specifications, explanations, profile, filters, and scores reflect **generation time**; fetch `/products/{id}` for current details. Older records without a full snapshot remain readable and explicitly disclose that their product details come from the current catalog. History requests never regenerate recommendations or fabricate missing evidence. Empty runs are persisted with zero items; no filters are automatically relaxed.

### Actual generated examples

`data/phase3_examples.json` contains seven actual results generated from the existing synthetic demo catalog, one per supported mode, with database recommendation IDs, timestamps, effective filters, product references, prices, scores, and explanations. Regenerate them with:

```powershell
.\.venv\Scripts\python.exe -m retailrag.examples --output data/phase3_examples.json
```

This command requires the bundled demo IDs, writes the report, and saves **seven new recommendation runs** each time. It does not overwrite product/customer data or create fake agent activity.

## Phase 4: persistent Chroma RAG

### Setup and local execution

After updating dependencies, ingest the existing catalog explicitly. Startup never indexes data or contacts an LLM automatically:

```powershell
.\.venv\Scripts\python.exe -m pip install -e '.[dev]'
.\.venv\Scripts\python.exe -m retailrag.rag_cli ingest
.\.venv\Scripts\python.exe -m retailrag.rag_cli status
.\.venv\Scripts\python.exe -m retailrag.rag_cli search --query 'wireless headphones under INR 3000'
.\.venv\Scripts\python.exe -m retailrag.rag_cli examples --output data/phase4_examples.json
```

Use the same backend/frontend launch commands above. In **RAG Search**, click **Synchronize catalog index**, enter a query and optional customer/category/brand/budget/channel filters, then search. The page shows actual index status, generated grounded text, product references, similarity/ranking scores, and retrieved documents/metadata. It labels generation mode and whether an LLM was actually attempted/used. Phase 3's recommendation page and saved history remain separate and unchanged. RAG searches do not write recommendation history or fabricate agent activity.

### Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `RETAILRAG_RAG_DIRECTORY` | `data/chroma` | Local vector storage, lock, and manifest |
| `RETAILRAG_RAG_COLLECTION` | `retailrag_products` | Index namespace; lowercase letters/digits/underscores |
| `RETAILRAG_RAG_CHUNK_SIZE` | `1000` | Description/features/attributes chunk size (300–5000 characters) |
| `RETAILRAG_RAG_GENERATION_MODE` | `deterministic` | `deterministic` or explicitly enabled `openai` |
| `RETAILRAG_RAG_OPENAI_MODEL` | `gpt-4.1-mini` | Model used only for optional retrieved-ID selection |
| `RETAILRAG_RAG_LLM_TIMEOUT` | `15` | External request timeout in seconds |
| `OPENAI_API_KEY` | empty | Optional credential; never displayed or persisted in results |

The default embedding implementation is **local LSA**: corpus TF-IDF projected with deterministic truncated SVD into up to 128 normalized dimensions. Documents and queries share the saved vocabulary/IDF/projection for each generation. No pretrained model files, remote embeddings, credentials, or pickle deserialization are used. This is a small-catalog latent-semantic retrieval baseline, not general language understanding. Unmatched vocabulary and stopword-only requests return no products. A budget-only request uses catalog category context for vector retrieval while retaining strict price/stock filters.

### Documents, storage, and synchronization

Each product document includes its ID, name, category, brand, exact INR price, features, attributes, current availability/stock, and dataset source. LangChain recursively chunks long descriptions/feature/attribute content with overlap; every chunk repeats the identifying facts needed for attribution. A chunk's complete text can exceed the configured body chunk size because the factual product header is repeated. IDs, product fingerprints, and document hashes are deterministic.

Chroma stores actual normalized dense vectors in a cosine-distance collection. The accompanying JSON manifest stores the active collection ID, embedding state, product snapshots, chunk size/count, and timestamp. Updates publish a fully written and verified new collection using atomic manifest replacement, then remove retired collections in this namespace. All application index reads/writes use the same process-safe file lock. Failed builds preserve the previous active index. An unchanged repeated ingest keeps its generation; changing chunk size rebuilds it. Index-only deletion never deletes relational catalog/customer/history data.

```powershell
# Update selected product records while retaining the other indexed products:
.\.venv\Scripts\python.exe -m retailrag.rag_cli ingest --product-id P001
# Remove a product from the vector index only:
.\.venv\Scripts\python.exe -m retailrag.rag_cli delete --product-id P001
# Full synchronization restores every current catalog product and prunes catalog deletions:
.\.venv\Scripts\python.exe -m retailrag.rag_cli ingest
# Rebuild embeddings/documents, including recovery from a corrupt manifest:
.\.venv\Scripts\python.exe -m retailrag.rag_cli ingest --force
```

Partial ingestion updates selected IDs and prunes records no longer in the catalog; unselected changed records remain reported as stale. Full `--force` ingestion can recover an unreadable manifest using the relational database as the source of truth. Partial recovery requires a readable prior manifest. Keep the whole RAG directory together when backing it up; its JSON state and Chroma storage must refer to the same generation. The default generated directory is Git-ignored. This local index is not a hosted Chroma integration.

### Retrieval, filtering, and grounding

The workflow is: resolve query/customer context → embed query → query Chroma with native metadata constraints → deduplicate/rank product candidates → verify document hashes and current catalog fingerprints → optionally select retrieved IDs with an LLM → render canonical product facts and references.

Metadata filters use integer `price_cents` for exact money boundaries, stock-derived availability, normalized category/brand keys, dataset source, and optional product IDs. Natural-language budget extraction and declared customer budget defaults follow Phase 3 rules. RAG enforces effective budget bounds strictly. Channel affects customer preference weighting, not invented channel-specific inventory.

Returned cosine similarity is `clip(1 - Chroma cosine distance, 0, 1)`, with a default minimum of 0.05. Without a customer, this is also the ranking score. With a customer, ranking uses **75% similarity + 15% category/brand affinity + 10% budget compatibility**. Only retrieved candidates are ranked; the highest-similarity chunk represents each product. Scores are not probabilities or measured recommendation accuracy.

Changed/deleted catalog records are excluded until synchronization, and status reports missing/stale/deleted IDs. Retrieved text/metadata must exactly match their expected indexed document and current product fingerprint; corrupt evidence is discarded. Empty results do not relax filters or substitute unrelated products. A status count check does not audit every stored vector/document; use forced ingestion to repair suspected corruption. No API can replace catalog facts with LLM-generated content.

### RAG endpoints

| Method | Path | Behavior |
| --- | --- | --- |
| POST | `/rag/ingest` | Full synchronization with `{}`; optional `product_ids` and `force` |
| POST | `/rag/search` | Retrieve validated documents and return grounded answer/references |
| GET | `/rag/status` | Actual indexed counts/generation, freshness, generation mode, credential-presence flag |
| DELETE | `/rag/products/{product_id}` | Remove that product from the active vector index only |

Search fields: required `query`; optional `customer_id`, `channel`, `category`, `brand`, `source`, `product_ids`, `min_price`, `max_price`, `available_only` (default true), `limit` (1–20), and `min_similarity` (0–1). Ingestion accepts up to 500 selected IDs; unknown selected IDs return 404 without changing the index. Unknown fields and malformed filters return 422. Index/storage failures return generic 503 errors while the existing catalog/recommendation APIs remain available. Status values include `not_ingested`, `ready`, `stale`, and `empty`.

```powershell
Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8000/rag/ingest' -ContentType 'application/json' -Body '{}'
$body = @{
    query = 'wireless headphones under INR 3000'
    brand = 'SoundNest'
    customer_id = 'C001'
    channel = 'mobile'
    available_only = $true
    limit = 5
} | ConvertTo-Json
$rag = Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8000/rag/search' -ContentType 'application/json' -Body $body
$rag.answer
$rag.items | Select-Object document_id, similarity_score, relevance_score
Invoke-RestMethod 'http://127.0.0.1:8000/rag/status'
```

### Optional LLM assistance and fallback

Leave generation mode `deterministic` for the fully local path. To enable optional selection, set `RETAILRAG_RAG_GENERATION_MODE=openai` and `OPENAI_API_KEY` in `.env`, then restart the backend. An enabled request sends the shopping query and selected retrieved product chunks to OpenAI. It requests only a structured list of product IDs from the allowed evidence set; the Responses request uses `store=false` and does not retry automatically. The implementation follows [OpenAI's Structured Outputs documentation](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses).

Unknown IDs, duplicates, extra fact fields, refusals, incomplete output, malformed JSON, timeouts, and HTTP failures trigger deterministic fallback. Missing credentials never prevent startup, ingestion, or search. Responses expose `generation`, `llm_attempted`, `llm_used`, and `llm_status`, so a failed attempt is distinct from a successful selection. Even a successful LLM response cannot supply prices, stock, specifications, or free-form factual claims; displayed facts are rendered locally from validated evidence. The tested default examples use **no LLM**. The optional API contract and success/failure paths are tested using mocked responses; no paid request has been made.

## Phase 5: actual LangGraph agent workflows

### Workflow and real responsibilities

The application compiles and invokes a real `StateGraph` with typed shared state and conditional edges, following the [LangGraph Graph API](https://docs.langchain.com/oss/python/langgraph/graph-api). These are deterministic specialized role agents; no LLM call or API key is required.

| Agent node | Actual work |
| --- | --- |
| Supervisor | Chooses retrieval from the requested mode/policy and actual vector-index readiness |
| Query Understanding | Resolves validated budget/category/brand/source-product constraints against the catalog |
| Customer Context | Analyzes real cross-channel preferences/history or reads the anonymous catalog baseline |
| Product Retrieval | Calls Chroma document retrieval or content retrieval with attributable evidence |
| Recommendation | Computes the six ranking components using query/source similarity, customer affinity, filters, and stock |
| Product Ranking | Sorts scored candidates using weighted relevance and deterministic tie breakers |
| Availability | Rechecks current database facts/stock, excludes changed records, and selects the requested count |
| Explanation | Renders product-specific explanations from real scores, prices, availability, and evidence IDs |
| Validation | Independently verifies live products, request/customer constraints, score arithmetic, references, and documents |
| Response | Renders the grounded answer and atomically saves validated output, or returns an audited failure |

The normal route executes all ten nodes in that order. An empty retrieval routes directly to Validation → Response, so recommendation/ranking/availability/explanation nodes are **not** recorded as executed. If availability removes every candidate, Explanation is bypassed. A failed node routes to Response with an error; unexecuted downstream agents have no fake history rows. The UI shows only actual steps and names nodes not executed on the selected route.

### Strategy, tools, and state

`retrieval_strategy` accepts `auto`, `rag`, or `content`:

- `auto`: contextual queries with strict budgets use an available nonempty Chroma index. Other recommendation modes and soft budgets use content retrieval. Missing/unavailable Chroma produces an explicit content-fallback warning. If a Chroma tool fails, its failed call is audited before content fallback executes. Empty valid Chroma results do not trigger an unrelated fallback.
- `rag`: requires `context_aware` mode and `strict_budget=true`. An unavailable/un-ingested index produces a failed audited run, not fake vector results.
- `content`: uses the preserved TF-IDF/cosine components and current catalog evidence without accessing the vector index. Similar mode filters to the source category by default, excludes the source ID, and allows the same explicit category override as Phase 3.

Workflow retrieval explicitly disables the optional RAG LLM selector even if standalone RAG is configured for OpenAI. All workflow output reports `engine=langgraph_workflow`, `generation=deterministic_agents`, and `llm_used=false`. Chroma and content candidates use the same six requested weights as Phase 3, normalized over active signals; Chroma similarity replaces TF-IDF similarity for retrieved vector candidates. The actual selected source and index generation are returned. Channel weighting, budgets, purchased-product exclusion, metadata constraints, and cold-start behavior remain evidence-backed.

The original twelve workflow StructuredTools remain intact. Phase 6 adds `get_product_details`, `get_customer_history`, `search_similar_products`, `filter_by_budget`, and `get_recommendation_history` to the internal registry, bringing its allowlist to seventeen. The Context Agent actually invokes `get_customer_history` and records a paginated sample plus its real total in shared state. Internal and public contracts are deliberately separate: internal tools exchange trusted workflow evidence objects, while public tools accept IDs/requests only. Audits record actual arguments, timing, success/failure, output summaries, and a SHA-256 digest of the validated result.

Shared state stores the request, supervisor plan, resolved context, profile, retrieval evidence, scored/ranked candidates, final items, weights, validation, warnings, actual executed-node names, and final output/error. Each node's start/finish is committed to the existing `agent_executions` table. Additive `workflow_runs` and `workflow_steps` tables connect executions and preserve a JSON state snapshot after each completed/failed node. Other API clients can observe a genuinely running node while the synchronous run request is in progress.

### Persistence and failure behavior

The save tool rechecks grounding, budget/category/brand/purchase/availability constraints, current customer context, document identity, and score arithmetic **inside the final save transaction**. A price/stock change between Validation and Response cannot silently become a valid saved result. The transaction writes the recommendation, items, full evidence snapshot, workflow recommendation link, and execution links together. Failed saves roll back those writes while preserving the actual failure trace.

Completed empty runs save a recommendation with zero items. Failed runs save no unverified recommendation and return no invented products. Successful workflow recommendations appear in the existing Recommendation History; their original product/price/evidence snapshots remain readable after catalog edits. Workflow status/inspection calls never execute agents again.

Execution is synchronous and sequential. Persisted JSON snapshots are audit checkpoints, **not** a resumable LangGraph checkpointer or background-job queue. A process crash can leave a previously running run marked running; it is not automatically replayed. There are no simulated timers or agent animations. Status/errors reflect recorded execution only.

### API and application UI

| Method | Path | Behavior |
| --- | --- | --- |
| POST | `/agents/run` | Validate a request and execute/persist a new workflow run |
| GET | `/agents/status` | Real run counts/list; optional `status`, `limit`, `offset` |
| GET | `/agents/runs/{run_id}` | Original request, timestamps, status, output, step/tool traces, and latest state |
| GET | `/agents/definition` | Actual compiled node/edge definition, LangGraph version, and Mermaid graph |

Requests support all seven Phase 3 modes and their fields/weights, with a workflow `limit` of 1–20 and the additional `retrieval_strategy`. Unknown fields, invalid modes, bad bounds, and unsupported strategy combinations return 422 before a run is created. A valid execution request returns **201** with `status=completed` **or** `status=failed`; inspect that field and `error` rather than assuming every 201 is a successful recommendation. Missing run IDs return 404. Infrastructure failures that prevent database access use the application's generic 503 response.

The **Agent Workflow** page lets you choose a mode, shopping query, customer/source product, filters, strategy, and channel. It runs the actual backend workflow and shows real tasks, statuses, timings, tool calls, output summaries, errors, grounded products, and the saved checkpoint. Its definition view is derived from the compiled graph. Refreshing status or browsing history does not create a new run.

```powershell
$body = @{
    mode = 'context_aware'
    query = 'wireless headphones under INR 3000'
    customer_id = 'C001'
    channel = 'mobile'
    retrieval_strategy = 'auto'
    limit = 3
} | ConvertTo-Json
$run = Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8000/agents/run' -ContentType 'application/json' -Body $body
$run.status
$run.steps | Select-Object sequence, agent, status, duration_ms, error
$run.output.answer
Invoke-RestMethod 'http://127.0.0.1:8000/agents/status'
Invoke-RestMethod "http://127.0.0.1:8000/agents/runs/$($run.run_id)"
```

### CLI and actual examples

```powershell
.\.venv\Scripts\python.exe -m pip install -e '.[dev]'
.\.venv\Scripts\python.exe -m retailrag.workflow_cli definition
.\.venv\Scripts\python.exe -m retailrag.workflow_cli run --query 'wireless headphones under INR 3000' --customer-id C001 --channel mobile --strategy auto
.\.venv\Scripts\python.exe -m retailrag.workflow_cli inspect --run-id 'PASTE_RUN_ID_HERE'
.\.venv\Scripts\python.exe -m retailrag.workflow_cli examples --output data/phase5_examples.json
```

The examples command uses the existing demo records and executes three real runs: contextual retrieval, personalized content retrieval, and an unmatched query with the shorter empty-result route. It saves three recommendations (including the empty run) and their actual agent executions each time. The report includes the actual compiled graph, run/recommendation IDs, outputs, step statuses/timings, and tool-result summaries/digests. CLI execution returns a nonzero code for a failed run. Use the same repository-root working directory and database/index configuration as the backend.

## Phase 6: reusable, validated retail tools

The public API exposes the eleven requested tools through the same LangChain StructuredTool registration/validation/audit implementation used by the workflow. The implementation follows [LangChain's tool schema contracts](https://docs.langchain.com/oss/python/langchain/tools). Public tools accept IDs or validated requests; callers cannot supply authoritative prices, availability, product specifications, score components, or pretend tool results.

### Available tools

| Tool | Main input | Actual result / business-data effect |
| --- | --- | --- |
| `search_products` | Query, category/brand, price/stock filters, sort, pagination | Literal catalog search; read |
| `get_product_details` | Product ID | Current product facts; read |
| `get_customer_profile` | Customer ID, optional channel | Cross-channel inferred preferences; read |
| `get_customer_history` | Customer ID, optional channel, pagination | Actual interaction records; read |
| `search_similar_products` | Source ID, optional budget/stock filters | Same-category TF-IDF/cosine preview, source excluded; read |
| `retrieve_product_documents` | RAG query and metadata/customer filters | Actual Chroma evidence and deterministic grounded response; read |
| `filter_by_budget` | Product IDs and at least one price bound | Products matching current database prices; read |
| `check_product_availability` | Product IDs | Current stock/availability; read |
| `rank_recommendations` | Validated recommendation request, optional candidate IDs | Server-computed scores/explanations; read preview |
| `save_recommendation` | Same request/candidate scope plus idempotency key | Generate, validate, and atomically save one recommendation |
| `get_recommendation_history` | Optional customer/channel filters, pagination | Original stored product IDs, explanations, scores, and price snapshots; read |

Each discovery entry publishes its description, effect, JSON input/output schemas, and example arguments. `read` describes business-data access: every executed public tool also creates an invocation audit. Only `save_recommendation` writes recommendation history. Tools never update products, inventory, customer profiles, interactions, or vector indexes, and they never call an LLM. The document tool explicitly disables standalone RAG's optional selector.

`search_products` is literal normalized keyword search; use the document tool for Chroma retrieval. Budget/availability tools accept **IDs only** and fetch actual facts. Prices remain exact INR decimals. Rank/save accepts all seven recommendation modes and up to 50 results. Optional candidate IDs are applied **before** ranking and the limit, and saved request metadata preserves their scope. Public ID lists are deduplicated and sorted during argument normalization. Missing selected IDs fail the invocation rather than producing invented or partial product facts.

### Validation, grounding, and durable history

Inputs reject unknown fields, invalid money/ranges/channels/IDs, unsupported modes, and oversized candidate lists. Public arguments are finite JSON objects with at most 100 top-level keys and at most 64 KiB encoded content. Payload-size/nonfinite rejection occurs before an invocation is created. Other accepted execution attempts are recorded as running/completed/failed; schema-invalid and unknown-tool attempts are recorded as failed without executing an operation.

Outputs are validated against their registered Pydantic contracts. Independent checks compare product snapshots with the live catalog, validate budgets and stock references, compare profiles/interactions with actual history, check recommendation context/score arithmetic/explanations, validate RAG document hashes/references/canonical text, and preserve historical recommendation prices. A valid-looking fabricated price or explanation is rejected rather than returned as a successful result.

`tool_invocations` stores actual arguments, effect, status, start/finish timestamps, result snapshot, error code, validated-result digest, and tool audit. Known credential field names in invalid arguments are redacted. An output rejected by grounding is stored as a failed call with no accepted result or result digest. Inspection is read-only; it returns the original snapshot even after catalog changes. Execute a new read tool to obtain current facts. `get_recommendation_history` labels its price basis as `saved_recommendation_snapshot` rather than comparing those historical prices with today's catalog.

Internal workflows retain their original evidence-object contracts and use the shared registry. The five added helper tools bring the internal allowlist to seventeen. The Context Agent now executes `get_customer_history`; its audit stays in the workflow's actual AgentExecution trace and its paginated sample/total appear in the state checkpoint. Those internal calls do not manufacture duplicate standalone public invocation rows.

### Atomic save and idempotency

`save_recommendation` accepts a request, **not** caller-generated scores/facts/answers. It generates the recommendation server-side. Its required `idempotency_key` is 8–64 letters/digits/underscores/hyphens and is globally unique within this local database. The operation commits the recommendation, items, evidence snapshot, invocation result, and completed audit together. A recommendation-write failure or audit-commit failure rolls back all business writes while retaining a failed invocation.

- First successful save: HTTP **201**, `replayed=false`, one new recommendation and invocation.
- Same key and semantically equivalent normalized arguments: HTTP **200**, `replayed=true`, the original call/result/recommendation IDs; no regeneration or additional rows. Equivalent money formatting and candidate-ID order/duplicates normalize consistently.
- Same key with different arguments: HTTP **409**, `error_code=idempotency_conflict`; the request is not executed and no mismatched result is returned. The response references the original invocation; its persisted original status remains unchanged.
- Same key while the original call is running: HTTP **409**, `error_code=in_progress`; inspect that call rather than starting a duplicate save.
- A failed saved invocation remains failed on replay. Use a new key for a deliberately new attempt after correcting the cause; failed calls are not silently re-executed.

Completed reads return HTTP 200. Missing records/unknown tools return 404; schema/grounding failures return 422; operation/persistence failures return 503. Executed failures return an inspectable call ID with no result. Outer-body/path validation can reject malformed requests before execution/auditing. Tools are synchronous; a process crash can leave a running record for operator review. There is no automatic replay of interrupted operations.

### API and Tool Explorer

| Method | Path | Behavior |
| --- | --- | --- |
| GET | `/tools` | Discover eleven public tools and schemas |
| GET | `/tools/{tool_name}` | Describe a specific allowed tool |
| POST | `/tools/{tool_name}/execute` | Execute `{ "arguments": { ... } }` and persist its audit/result |
| GET | `/tools/invocations` | Paginated invocation history; optional `tool` and `status` filters |
| GET | `/tools/invocations/{call_id}` | Original result, audit, status, timing, and recommendation link |

In **Tool Explorer**, choose a tool, inspect its published schema/example, edit JSON arguments, and click **Execute Tool**. Write effects and idempotency behavior are stated before execution. The page displays actual results and invocation history; refreshing/inspecting does not run a tool again. Invalid JSON is rejected in the UI without an API invocation. The save example retains its key across retries; edit it for a deliberately new save. Workflow/recommendation/RAG pages remain functional.

PowerShell read/save/retry examples:

```powershell
$body = @{ arguments = @{ product_id = 'P001' } } | ConvertTo-Json -Depth 10
Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8000/tools/get_product_details/execute' -ContentType 'application/json' -Body $body

$saveKey = [guid]::NewGuid().ToString('N')
$body = @{
    arguments = @{
        request = @{
            query = 'wireless headphones under INR 3000'
            customer_id = 'C001'
            channel = 'mobile'
        }
        idempotency_key = $saveKey
    }
} | ConvertTo-Json -Depth 10
$saved = Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8000/tools/save_recommendation/execute' -ContentType 'application/json' -Body $body
# Retry the exact request with the same key; this returns the original saved result:
$retry = Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8000/tools/save_recommendation/execute' -ContentType 'application/json' -Body $body
$retry.replayed
Invoke-RestMethod "http://127.0.0.1:8000/tools/invocations/$($saved.call_id)"
```

### CLI and actual examples

No new dependencies or API credentials are required beyond the existing project environment.

```powershell
.\.venv\Scripts\python.exe -m retailrag.tool_cli list
.\.venv\Scripts\python.exe -m retailrag.tool_cli describe --name filter_by_budget
New-Item -ItemType Directory -Path .test-tmp -Force | Out-Null
@{ product_id = 'P001' } | ConvertTo-Json | Set-Content -Encoding utf8 .test-tmp/tool-arguments.json
.\.venv\Scripts\python.exe -m retailrag.tool_cli execute --name get_product_details --arguments-file .test-tmp/tool-arguments.json
.\.venv\Scripts\python.exe -m retailrag.tool_cli inspect --call-id 'PASTE_CALL_ID_HERE'
.\.venv\Scripts\python.exe -m retailrag.tool_cli examples --output data/phase6_examples.json
```

The examples command executes all eleven tools against existing demo IDs, then retries its one save using the same key. It exports **twelve execution responses backed by eleven distinct invocation records and one new recommendation**. Each new examples run uses a new save key. It does not ingest/recreate catalog data or generate fake agent activity. Failed CLI executions return a nonzero exit code.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest -q
Invoke-RestMethod http://127.0.0.1:8000/health
```

The health endpoint checks application liveness; `/database/status` checks database-backed queries. Tests use isolated databases and verify ingestion rollback/idempotence, constraints, persistence after reconnection, customer history, filters, input validation, simulated interactions, API errors, and Streamlit navigation/search against the actual test API.

Phase 1 verification (2026-11-04): Python 3.11.18; `python -m pytest -q` completed with **7 passed** in 11.63 seconds. One upstream Starlette warning reports deprecated HTTPX TestClient integration. `python -m compileall -q src tests` also passed. Streamlit was verified with AppTest; a manual browser review has not been performed.

### Phase 2 delivery and actual results (2026-11-04)

- Added: `database.py`, `models.py`, `data_schemas.py`, `ingestion.py`, `data_cli.py`, `catalog_api.py`; three synthetic CSVs in `data/demo`; database/ingestion/CLI/API tests and shared test fixtures.
- Updated: `api.py` (database lifecycle and routes), `frontend.py` (database counts/catalog/customer history), existing foundation/UI tests, dependencies and CLI entry point in `pyproject.toml`, `.env.example`, `.gitignore`, and this README.
- Installed SQLAlchemy 2.0.57 and loaded the local application database: **24 products, 8 customers, 56 interactions**; all provenance is `synthetic_demo`. Recommendation and agent execution counts are zero.
- Full suite: **56 passed, 1 upstream deprecation warning in 24.31 seconds** using Python 3.11.18. Command: `python -m pytest -q --tb=short -x --basetemp=.test-tmp/phase2-run2 -o cache_dir=.test-tmp/cache` after creating `.test-tmp`. Initial attempts were blocked by Windows access permissions on the shared temporary directory; the successful run used workspace-local temporary files.
- `python -m compileall -q src tests` and `git diff --check` passed.
- Live subprocess smoke checks passed: Uvicorn `/health` reported Phase 2; `/products/search?q=wireless+headphones&max_price=3000` returned `P001`; Streamlit `/_stcore/health` returned `ok` and its root page returned HTTP 200. Smoke-check servers were stopped afterward.
- Streamlit navigation and filters were tested against the actual in-process API. No manual browser visual review or PostgreSQL server verification was performed.
- At the end of Phase 2, the recommendation engine and later RAG/agent/UI/analytics phases remained outstanding. Phase 2 added persistence only for future recommendation and agent records.

### Phase 3 delivery and actual results (2026-11-04)

- Added `content_index.py`, `preferences.py`, `recommendation_schemas.py`, `recommendation_context.py`, `recommendations.py`, `recommendation_api.py`, and `examples.py`. Added engine/API/example tests and expanded Streamlit tests. Updated API registration/health, models, frontend navigation, dependency declarations, configuration comments, and this README.
- All seven recommendation modes are functional. Runs store original product/profile/filter/score evidence in the additive `recommendation_snapshots` table, with no alteration of Phase 2 tables. Category/brand/budget/availability constraints and purchased-product exclusions are applied before final ranking.
- Full suite after the similar-category correction: **109 passed, 1 upstream Starlette TestClient deprecation warning in 52.30 seconds** on Python 3.11.18, scikit-learn 1.9.1, and SQLAlchemy 2.0.57. Exact command:

```powershell
.\.venv\Scripts\python.exe -m pytest -q --tb=short -x --basetemp=.test-tmp/phase3-full2 -o cache_dir=.test-tmp/cache
```

- Tests cover TF-IDF/cosine scores, all modes, profile/history/channel preferences, cold-start baselines, custom weights, exact and exclusive price boundaries, availability, ambiguous/unsupported queries, out-of-vocabulary/empty results, fresh catalog changes, transactional rollback, history filters, immutable snapshots after catalog changes, legacy records, and UI generation/history/navigation against the real test API. All existing Phase 1–2 tests remain passing.
- Live subprocess smoke checks against an isolated backup of the application database passed: `/health` reported Phase 3; generation returned HTTP 201 with `P001` at **INR 2499.00** for a mobile-channel headphone query; history returned the exact saved snapshot; preferences reported 8 existing customer interactions; Streamlit health returned `ok` and its root page returned HTTP 200. Both smoke-check servers were stopped.
- `python -m compileall -q src tests` and `git diff --check` passed. No manual browser visual review or PostgreSQL server test was performed.
- `data/phase3_examples.json` contains the final seven actual example runs, recommendation IDs **8–14**. Top results: personalized `P003` (INR 1799), similar `P003` (INR 1799), budget `P024` (INR 799), category `P008` (INR 3499), brand `P001` (INR 2499), new customer `P024` (INR 799), context-aware running shoes `P005` (INR 2999). The similar example correctly returns one qualifying product instead of filling the requested count with unrelated categories.
- Existing source data remains **24 products, 8 customers, 56 interactions**. The local database now has **14 saved recommendation runs, 36 items, 14 snapshots, and 0 agent executions**: the first seven development example runs were preserved, and the final seven were added. Live smoke checks did not change this database.
- At the end of Phase 3, ChromaDB and grounded RAG remained next, followed by LangGraph agents and the complete analytics experience.

### Phase 4 delivery and actual results (2026-11-04)

- Added eight RAG modules: document processing, local LSA embeddings, persistent Chroma index management, retrieval/grounding, constrained generation, schemas, API routes, and CLI commands. Added retrieval/API/CLI tests and expanded UI tests. Updated configuration, `.env.example`, API registration/health, Streamlit navigation, dependency declarations, isolated test fixtures, and this README. No relational models/tables or existing catalog/customer/history records were replaced.
- Actual dependencies tested: **ChromaDB 1.5.9**, **langchain-chroma 1.1.0**, **langchain-core 1.7.4**, **langchain-text-splitters 1.1.3**, and **scikit-learn 1.9.1**, on Python 3.11.18.
- Final full suite: **131 passed in 76.18 seconds; no warnings reported**. Exact command:

```powershell
.\.venv\Scripts\python.exe -m pytest -q --tb=short -x --basetemp=.test-tmp/phase4-full3 -o cache_dir=.test-tmp/cache
```

- New coverage includes real Chroma ingestion/querying/reopening; JSON embedding-state round trips; chunking and product deduplication; metadata/price/stock/source/ID filters; query/customer context; stale catalog evidence; update/deletion/re-synchronization; last-product deletion through a newly opened store; failed vector-write preservation; corrupt document rejection; forced recovery; grounded price/reference validation; missing credentials/provider failures/invalid structured outputs; CLI examples; and actual API-backed Streamlit RAG interaction. All prior tests pass. UI tests now use a 15-second bounded default to accommodate Windows startup variability, and their HTTPX response adapter handles Starlette's HTTPX2 test transport without changing the frontend's production transport.
- The application index is persisted under `data/chroma`: **24 products, 24 chunks**, status `ready`. A separate API process reopened it successfully; repeat ingestion reported **24 unchanged** products.
- Live smoke checks passed: `/health` reported Phase 4; `/rag/search` returned HTTP 200 with reference **P001**, exact price **INR 2499.00**, and `generation=deterministic_fallback`, `llm_used=false` for a filtered mobile-channel headphone request. Streamlit health returned `ok` and its root page returned HTTP 200. Smoke-check servers were stopped.
- `data/phase4_examples.json` contains four real Chroma results: wireless headphones under INR 3000 → **P001, P003**; running shoes with Footwear/INR 3500 filters → **P005, P008, P007**; SoundNest headphones → **P002, P001**; unmatched vocabulary → **empty**. Every example reports deterministic fallback and no LLM use. The report includes actual retrieved text, metadata, scores, index generation, filters, and product references.
- Existing database totals remain **24 products, 8 customers, 56 interactions, 14 recommendation runs, 36 recommendation items, and 0 agent executions**. RAG examples/searches do not create recommendation history.
- Syntax compilation and `git diff --check` passed. Generated vectors/databases/test artifacts remain Git-ignored. Optional OpenAI selection was tested with mocks only; no live paid LLM call, PostgreSQL server test, or manual browser visual review was performed.
- At the end of Phase 4, LangGraph orchestration remained next, followed by the broader tool/omnichannel/dashboard/analytics phases.

### Phase 5 delivery and actual results (2026-11-04)

- Added seven workflow modules: schemas/state, validated tools, independent validation, atomic persistence, LangGraph execution, API routes, and CLI commands. Added workflow engine/API/CLI tests and expanded UI tests. Updated dependency declarations, API health/registration, frontend navigation/history rendering, additive database models, database/foundation assertions, and this README. The Phase 4 retrieval function gained an optional LLM-disable flag with its existing behavior preserved by default.
- Actual graph runtime: **LangGraph 1.2.19**. Ten functioning role nodes execute validated tools, conditional routes, real stock/grounding checks, and final response persistence. Twelve reusable StructuredTools are registered; execution history contains only calls that actually occurred.
- Full suite: **159 passed in 116.60 seconds; no warnings reported**. Exact command:

```powershell
.\.venv\Scripts\python.exe -m pytest -q --tb=short -x --basetemp=.test-tmp/phase5-full2 -o cache_dir=.test-tmp/cache
```

- After the final workflow-timeout guidance change and one additional timeout-path test, the frontend suite passed **10 tests in 24.22 seconds** with no warnings. Exact command:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_frontend.py --tb=short -x --basetemp=.test-tmp/phase5-ui-final -o cache_dir=.test-tmp/cache
```

- Coverage includes actual compiled graph structure/conditional edges; all seven recommendation modes; real Chroma versus content/fallback routes; missing/unavailable index behavior; auditable tool errors and schema failures; live running-status inspection during a blocked tool call; immutable history; strict and soft filters/custom weights; changed stock; fabricated explanations; late price changes; failed-save rollback; CLI examples; and backend-connected workflow UI execution/inspection. A UI expectation was corrected to select the intended mobile channel explicitly; rankings legitimately vary with channel context.
- Live subprocess checks against an isolated backup passed: `/health` reported Phase 5; `/agents/run` returned HTTP 201 and `status=completed`; **10 actual nodes and 11 tool calls** executed; Chroma returned reference **P001** at **INR 2499.00** with `llm_used=false`; run inspection and recommendation history returned the original saved output; Streamlit health returned `ok` and its root page returned HTTP 200. Both smoke-check servers were stopped. The smoke run did not alter the source application database.
- `data/phase5_examples.json` contains three actual completed runs with recommendation IDs **15, 16, 17**: contextual Chroma retrieval → **P001, P003** (10 nodes); personalized content retrieval → **P008, P007, P005** (10 nodes); unmatched vocabulary → **empty** (6 nodes). The report includes actual run IDs, graph definition, outputs, tool digests, statuses, and timings.
- Preserved catalog/customer/interaction totals: **24 products, 8 customers, 56 interactions**. The local database now has **17 recommendations, 41 items, 17 snapshots, 3 workflow runs, 26 workflow steps, and 26 actual agent executions**. The previous 14 recommendations were preserved. The existing Chroma index remains intact.
- Added only `workflow_runs` and `workflow_steps`; reused existing agent/recommendation tables without changing their definitions. Syntax compilation and `git diff --check` passed. Generated database/index/test files remain ignored. No real LLM call, PostgreSQL verification, or manual browser visual review was performed.
- At the end of Phase 5, expansion of the tool layer remained next, followed by omnichannel, endpoint, UI/dashboard, and analytics work.

### Phase 6 delivery and actual results (2026-11-04)

- Added seven modules: shared tool registry, public schemas, eleven retail tool implementations, independent grounding validation, durable/idempotent execution service, tool API, and CLI. Added tool/API/CLI coverage and expanded UI tests. Updated workflow registry/helper registration and Context Agent history use, state schema, additive database model, recommendation candidate/transaction support, API routes/health, frontend navigation, existing schema/health assertions, and this README. No new dependencies were needed.
- All eleven requested public tools are discoverable and functional. The workflow's original twelve contracts remain private and compatible, with five reusable helpers added. LangChain registration, input/output validation, summaries, and result digests are shared. Public requests cannot inject prices, stock, score components, or pretend tool results.
- Final full suite: **186 passed in 152.90 seconds; no warnings reported**. Exact command:

```powershell
.\.venv\Scripts\python.exe -m pytest -q --tb=short -x --basetemp=.test-tmp/phase6-full-final -o cache_dir=.test-tmp/cache
```

- Coverage includes all eleven tools, published schema discovery, real catalog/profile/history/stock facts, Chroma documents without LLM calls, candidate scoping before ranking limits, provenance, rejected fabricated inputs/output prices, unknown IDs/tools, strict filters, canonical idempotency, concurrent running-call retries, conflicting keys without mismatched results, frozen save replay after catalog edits, historical price snapshots, failed recommendation/audit rollback, secret-field redaction, actual Context Agent history invocation, CLI examples, and real API-backed Tool Explorer interactions. All prior phases' tests pass.
- Live subprocess checks on an isolated database backup passed: `/health` reported Phase 6; discovery returned **11** tools; product read returned HTTP **200** and **INR 2499.00**; first save returned **201**, same-key retry returned **200** with the same call/result/recommendation, and a conflicting request returned **409** with no mismatched result. A ten-node LangGraph workflow completed and its new history tool reported **8** actual customer events. Streamlit health returned `ok` and its root page returned HTTP 200. Smoke-check processes were stopped; they did not alter the source database.
- `data/phase6_examples.json` contains **12 actual execution responses** for **11 distinct invocation records** across all eleven tools, including one successful save and its idempotent retry. The save created recommendation **18** exactly once. Every reported invocation completed; the final replay reuses the original call/result.
- Preserved source totals remain **24 products, 8 customers, 56 interactions, 3 workflow runs, and 26 agent executions**. The example save brings recommendation totals to **18 runs, 43 items, and 18 snapshots**. The source database contains **11 public tool invocation records**. All earlier records and the existing Chroma index are preserved.
- Added only `tool_invocations`; existing table definitions remain unchanged. Syntax compilation and `git diff --check` passed. Generated databases, vector storage, and test artifacts remain Git-ignored. No paid LLM call, PostgreSQL server verification, or manual browser visual review was performed.
- Remaining work begins with Phase 7: broader omnichannel simulation and channel analytics, followed by remaining endpoint/UI/dashboard phases.

## Omnichannel simulation, analytics, and dashboard

The sidebar exposes Overview, Product Catalog, Customer Context, AI Recommendations, RAG Search, Agent Workflow, Omnichannel Analytics, Tool Explorer, Recommendation History, and Settings. Overview and channel analytics use actual stored records. Native forms retain validation/loading/error states; product cards show catalog facts or explicitly indicate missing images. The catalog editor creates/updates products through the API. The sidebar collapses on mobile and the content stacks vertically; the dark-mode switch changes dashboard and chart styling.

In **Omnichannel Analytics → Shopping simulator**, choose a customer and events for the e-commerce website, mobile app, and physical store. Submitting records synthetic history and generates one recommendation run for each channel using the same customer history. Inspect the saved before/after profiles and actual results. Retrying the same journey reuses its key and creates no duplicate history. Use **Start a new journey** when another run is intended. The simulator does not place orders, collect payments, decrement stock, or contact retailers.

| Method | Path | Behavior |
| --- | --- | --- |
| POST | `/omnichannel/simulations` | Atomic events, shared profiles, and three saved recommendation runs; 201 new / 200 replay / 409 conflicting key |
| GET | `/omnichannel/simulations` | Paginated simulation history; optional customer filter |
| GET | `/omnichannel/simulations/{id}` | Original saved journey evidence |
| GET | `/omnichannel/customers/{id}/context` | Shared preferences viewed from all three channels |
| GET | `/analytics/overview` | Catalog totals, activity, provenance, popularity, recent recommendations |
| GET | `/analytics/recommendations` | Run trends, mode/category distribution, scores, product frequency, active customers |
| GET | `/analytics/channels` | Per-channel interactions, customers, synthetic purchase events, recommendations, workflows |
| POST | `/products` | Create validated catalog product; duplicate ID returns 409 |
| PUT | `/products/{id}` | Replace editable product facts while preserving its ID and saved history |
| DELETE | `/products/{id}` | Delete only an unreferenced product; referenced products return 409 |
| GET | `/ready` | Database readiness; vector ingestion remains explicit |
| GET | `/settings` | Safe configuration, generation mode, key-configured boolean; no key or database connection URI |

Analytics accept optional `date_from` / `date_to` ISO dates. Both boundaries are inclusive UTC days; reversed dates return 422. Product/customer totals and current inventory describe the entire current catalog; event/recommendation/agent/tool/simulation counts use the requested period. Popularity counts events, not quantities. Synthetic purchase quantities are recorded units, not verified orders or revenue. Product recommendation performance means frequency and average ranking score; recommendation impressions/clicks, CTR, attributed conversions, and sales lift are not instrumented. Category aggregation uses the current catalog taxonomy. Aggregation loads the selected records into memory and is intended for the local dataset, not large production analytics.

Example API journey (writes synthetic events and three recommendation runs to the running application's database):

```powershell
$journey = @{
  customer_id = 'C008'
  query = 'wireless headphones under INR 3000'
  idempotency_key = 'my-demo-shopping-journey-001'
  events = @(
    @{product_id='P001'; event_type='view'; channel='ecommerce'},
    @{product_id='P005'; event_type='wishlist'; channel='mobile'},
    @{product_id='P013'; event_type='purchase'; channel='store'; quantity=2}
  )
} | ConvertTo-Json -Depth 8
Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8000/omnichannel/simulations' -ContentType 'application/json' -Body $journey
Invoke-RestMethod 'http://127.0.0.1:8000/analytics/channels'
```

Catalog edits do not silently rewrite the Chroma index. Synchronize explicitly from RAG Search or Settings after changes. Recommendation snapshots preserve prices and evidence from the original run. Deleting a referenced product is intentionally rejected; setting its stock to zero preserves history while excluding it from available-only results.

## Phases 7–14 delivery and verification

Historical phase reports above describe the state at each earlier delivery. This section supersedes their remaining-work notes.

| Phase | Files / verified result | Validation |
| --- | --- | --- |
| 7: Omnichannel | `omnichannel.py`, `analytics.py`, `analytics_schemas.py`, `models.py`, API router registration; three-channel context and atomic retry-safe journeys | 5 focused tests passed, including rollback, filters, replay, and actual counts |
| 8: Backend | `catalog_api.py`, `api.py`; catalog management, safe settings, readiness, required endpoint coverage | 3 focused tests passed, including immutable historical snapshots and stale-index detection |
| 9: UI | `dashboard_ui.py`, `frontend.py`, Plotly dependency; actual charts, cards, editor, simulator, navigation, themes | 16 frontend/dashboard tests passed; desktop 1440×900 and mobile 390×844 browser layouts inspected |
| 10: Database | Existing models/database retained; additive simulation table only | SQLite foreign keys/checks, atomic rollback, history, indexes/constraints, and reopen persistence verified |
| 11: LLM config | Existing `config.py`, `.env.example`, RAG fallback retained; safe settings page/API | No-key startup/search/ML/RAG/workflow verified; keys redacted; paid provider path remains mocked |
| 12: Testing | All existing tests plus `test_omnichannel_analytics.py`, `test_catalog_management.py`, `test_dashboard_ui.py` | Full suite: **198 passed in 248.74 seconds**, no failures or reported warnings |
| 13: Delivery | This README, existing environment example and ignore rules | Exact PowerShell install/database/Chroma/backend/frontend/test commands supplied; `.env` excluded from Git |
| 14: Acceptance | `acceptance.py`, `data/final_acceptance.json` | Actual isolated services, data load/search, personalized recommendations, Chroma documents, ten-node graph/tools, evidence, simulation, analytics/history, restart persistence passed |

Full regression command used:

```powershell
.\.venv\Scripts\python.exe -m pytest -q --tb=short -x --basetemp=.test-tmp/final-suite -o cache_dir=.test-tmp/cache --junitxml=.test-tmp/final-tests.xml
```

Repeatable end-to-end acceptance command (requires `.[dev]`, creates a fresh SQLite/Chroma workspace under `.runtime/acceptance`, preserves the working application database, makes no paid LLM request):

```powershell
.\.venv\Scripts\python.exe -m retailrag.acceptance --output data/final_acceptance.json
```

The recorded acceptance run imported 24 products, 8 customers, and 56 synthetic events; generated 5 recommendation runs (one personalized, one workflow, three simulated channels); ended with 59 events; replayed the simulation without duplicates; and reopened the database/index successfully. Chroma returned P001/P003 for the headphone query. The graph completed all ten role nodes with actual tool calls. The separate live Uvicorn process reported Phase 14, Streamlit health returned `ok`, and the browser displayed actual metrics/charts. Acceptance and browser checks used isolated data. The working source database remains at 24 products, 8 customers, 56 interactions, 18 recommendation runs, 43 recommendation items, and 26 agent executions.

After the final chart-label adjustment, the four dashboard tests passed again in 17.41 seconds. Source compilation passed; the working SQLite database has 12 tables, zero foreign-key violations, and the expected simulation primary key, unique retry key, customer index, and timestamp index. Temporary live review servers were stopped. Start the application using the two PowerShell commands under Running the application.

## Troubleshooting

- Backend unavailable: start Uvicorn, verify `/health`, and check `RETAILRAG_API_BASE_URL`.
- Port in use: choose another Uvicorn port and update the API base URL accordingly.
- Import errors: install the package using the same `.venv` interpreter used to launch it.
- Installation fails under Python 3.15: recreate the environment using Python 3.11–3.13.
- Empty catalog: run the explicit demo/import command and verify `/database/status` points to the same database used by the CLI.
- Import conflict: use the same source label and unchanged records on repeat imports; conflicts deliberately preserve existing data.
- SQLite locked: let the current writer finish, close other editing tools, and retry. Transactions have a 15-second connection timeout.
- RAG index not ingested/stale: synchronize it through the RAG page, `/rag/ingest`, or `python -m retailrag.rag_cli ingest`. Ingestion is explicit, not automatic.
- RAG storage/manifest failure: verify the configured directory is writable; use full `python -m retailrag.rag_cli ingest --force` to rebuild from the relational catalog. Back up the existing index first if you need it for diagnosis. Catalog and Phase 3 endpoints can run while the vector index is unavailable.
- RAG returns no documents: check exact filters, stock, price boundaries, and vocabulary. Local LSA has no knowledge of unseen words. Do not interpret an empty filtered retrieval as proof that the entire catalog has no suitable product.
- Optional LLM unavailable: inspect `llm_status`; missing credentials, provider errors, invalid IDs, or malformed output use grounded deterministic fallback. A paid API call is not required for local operation.
- Agent run returned 201 with failed status: inspect `/agents/runs/{run_id}` for the actual failed node/tool. Shape validation errors create no run; valid requests that fail during execution retain an audited failed run.
- Explicit RAG agent run fails before retrieval: ingest the index or choose `auto`/`content`. The workflow never creates vector results or silently indexes data.
- Agent request timed out: inspect actual workflow status before resubmitting. The synchronous request may still be executing or may already have saved a recommendation. Refreshing/inspecting a run is read-only.
- Public tool request rejected: inspect its published `/tools/{tool_name}` input schema and recorded invocation error. Public inputs use IDs/requests, not internal workflow evidence objects or caller-supplied product facts.
- Save retry/conflict: reuse the same key only for the same normalized request. Inspect a running/failed original call; do not generate another key unless you intend a new attempt. HTTP 409 conflicts return no result from the mismatched request.
- Old tool prices/availability: invocation inspection is a frozen historical snapshot. Execute a fresh read tool for current catalog facts; historical recommendation prices remain original snapshots.
- Pytest temporary directory access denied: create a fresh local test directory and use `--basetemp` (pytest owns and clears the chosen leaf directory):

```powershell
New-Item -ItemType Directory -Path .test-tmp -Force | Out-Null
.\.venv\Scripts\python.exe -m pytest -q --basetemp=.test-tmp/local-run -o cache_dir=.test-tmp/cache
```

## Limitations

Role agents are deterministic programs coordinated by LangGraph. Execution is synchronous with durable audit/state snapshots; process-interrupted workflows or public tool invocations are not automatically resumed, and a process crash can leave a running record for operator review. Save and simulation keys are global within the local application database; authentication/user-scoped tenancy is not implemented. The local design favors transparent validation over production job-queue throughput. ML uses lexical TF-IDF. RAG uses corpus-fitted LSA embeddings with limited vocabulary coverage; index updates rebuild the local basis/vector generation. Workflow RAG retrieval returns at most 20 unique candidates, while internal scored content requests are bounded to 500 candidates. Inventory is global catalog stock; there is no per-store warehouse integration. The project has no real retailer integrations, inventory updates, authentication, automatic relational schema migrations, or deployment hardening. PostgreSQL and paid LLM requests remain unverified against live services. Browser checks cover desktop/mobile overview and channel analytics; automated AppTest covers every navigation page and the principal interactions. No deployment or production-scale performance claim is made.
