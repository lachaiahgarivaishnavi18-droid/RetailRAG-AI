# Local demo validation

Implemented and exercised on 5 November 2026. This is local validation, not cloud
deployment acceptance. The original storefront design and business data remain.

- Dependency check: `pip check` reports no broken requirements.
- Initial complete Python run: 216 passed, 2 failed, 374.18 seconds. Failures were
  the changed deterministic answer label and document return/returns matching.
  Both were corrected. No failure was suppressed or skipped.
- Follow-up including both affected cases and foundation tests: 9 passed.
- Final focused local startup, document persistence, RAG grounding, forced demo,
  optional OpenAI selection/invalid-response fallback: 20 passed in 27.73 seconds.
  This includes two additional startup/forced-demo tests beyond the first run.
- Streamlit AppTest against the running backend: dashboard rendered, Document
  Workspace rendered, sample button worked, document chat returned “30 days”.
- Live HTTP checks passed: health/readiness, products, customers, analytics,
  RAG/agent status, document upload/list/search, frontend page and health endpoint.
- Live shopping RAG returned P001/P003 for wireless headphones under INR 3000,
  with `llm_attempted=false` and `llm_used=false` in forced demo mode.
- Live text upload and pickup-hours question returned its source passage; sample
  return-policy query returned the synthetic 30-day policy after the fix.
- Browser rendered Product Discovery with 24 products, prices, stock, photos,
  navigation and existing styling after background startup.
- Common API-key/private-key pattern scan over source/tests/deployment files:
  zero matching files. Private .env and database files remain ignored.

The background launcher prints its actual URLs to `.runtime/local-server.json`.
At verification: frontend http://127.0.0.1:8514, backend http://127.0.0.1:8001.
Port 8000 was already occupied, so the launcher selected 8001 automatically.
Startup was tested on a separate empty temporary database twice: 24 products,
8 customers, one import audit, no duplicate seeding. Existing local history was
not reseeded. Document verification added only local demonstration documents.

Real OpenAI selection is validated with mocked successful/failing responses;
no paid external AI request was made. PDF/OCR is not implemented: uploads support
UTF-8 TXT, Markdown, CSV and JSON, and chat is local extractive evidence retrieval.
