# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased] — fixes of 2026-11-24

Bug-fix release. Every fix has a regression test in
`apps/api/tests/test_regressions.py` or the Playwright suite.

### Fixed

- **API failed to import on Python 3.11+.** Two guardrail regexes placed the
  `(?i)` flag mid-pattern, which is a hard `re.error` since 3.11. This broke
  every CI job and the Docker image. The role-hijack rule is now also
  multi-line, so a forged `system:` line is caught anywhere in the input.
- **API refused to start with the documented configuration.** pydantic-settings
  JSON-decodes list fields before validators run, so `CORS_ORIGINS=http://…`
  from `.env.example` (and `docker-compose.yml`) raised `SettingsError`. List
  settings now accept comma-separated values or a JSON list.
- **`email-validator` was never declared**, so a clean install failed on import.
  Now pulled in through `pydantic[email]`.
- **Re-seeding duplicated history.** Every `python -m app.db.seed` appended
  another 8 runs and 232 usage records, inflating cost dashboards. Run and
  usage history are now generated only into an empty database.
- **Blob-store traversal guard used a string-prefix check**, so a sibling such
  as `<root>-evil/` passed as inside the store. It now compares path ancestry.
- **Rate-limited and oversized-body responses lacked a request ID and the
  security headers** because the middleware order was inverted relative to the
  comment describing it.
- **Rate limiter grew without bound**: one deque per client, never pruned.
  Idle windows are now swept periodically, and hashed static assets are exempt.
- **CI security scan failed on a test fixture** shaped like an Azure key; the
  fixture is now assembled at runtime. The `pip-audit` step fed a JSON report
  to `-r` and never audited anything; it now audits the installed environment.
- **mypy reported 12 errors** in the seed module (loop variables typed from
  heterogeneous dict literals). Annotated; the CI type check is now blocking.
- **Three Playwright specs were wrong** (ambiguous text locators and a node
  label the UI never renders). The suite was never executed before; all 12
  journeys now pass against both the dev server and the demo image.
- Vite's `vite.config.ts.timestamp-*.mjs` temp files were committed; removed
  and ignored. Added `.dockerignore` files so local `node_modules`, virtualenvs
  and databases never enter a build context.
- The sign-in error no longer tells deployed users to check port 8000.

### Added

- Root `Dockerfile`, `scripts/start-demo.sh` and `render.yaml`: a
  single-container demo image in which the API also serves the built web app
  (`WEB_DIST_DIR`), with SPA fallback for client-side routes and immutable
  caching for hashed assets. See `docs/DEPLOYMENT.md` → Hosted demo.
- `HEAD /` is answered, for uptime monitors.

## [0.1.0] — 2026-08-16

First working vertical slice. See [BUILD_REPORT.md](BUILD_REPORT.md) for what was
verified and what was not.

### Added

**Platform**

- FastAPI control plane with 14 routers and 57 OpenAPI paths under `/api/v1`
- 24-table PostgreSQL schema with UUID keys, soft delete and a reversible
  Alembic baseline migration
- Provider abstraction for LLM, embeddings, vector store and blob storage, with
  deterministic local implementations and Azure implementations behind the same
  protocols
- JWT and API-key authentication; five-role RBAC enforced on every endpoint
- Structured JSON logging with request/correlation IDs and secret redaction
- Rate limiting, body size limits, security headers and CORS allowlisting

**AI**

- LangGraph agent execution: nine acyclic nodes with retries, bounded model
  fallback, tool failure tolerance and a persisted step-by-step trace
- RAG engine: extraction (PDF/DOCX/CSV/JSON/text), normalisation, sentence-aware
  chunking with page tracking, embedding, indexing, threshold filtering, hybrid
  reranking, context assembly and citations
- Guardrails with detection, policy and enforcement kept explicitly separate
- Evaluation with eight deterministic metrics, pass thresholds, regression
  detection and CSV export
- Closed tool registry: AST-based calculator, clock, URL policy check

**Operations**

- Cost tracking computed at write time from per-model configured rates, with
  budgets and threshold alerting
- Component health checks and an Azure resource inventory that reports
  `not_configured` rather than synthesising metrics
- Append-only audit log covering every mutation
- Background worker for metric collection, alert evaluation and ingestion retry

**Frontend**

- 17-route React command centre with a dark Azure-inspired design system
- Overview dashboard with seven charts and live system health
- Agent manager with inline versioning and a test runner
- Run inspector rendering the execution graph with per-node timings
- RAG playground with live pipeline visualisation and score breakdowns
- Document intelligence with drag-and-drop upload and chunk inspection
- Prompt registry with rendering, comparison and rollback
- Model centre, guardrail tester, evaluation dashboard, cost centre, alerts,
  audit log and settings

**Engineering**

- 102 backend tests and 24 frontend tests, all passing
- 11 Playwright E2E specs (written, not yet executed)
- CI, Docker and deploy GitHub Actions workflows
- Bicep infrastructure for three environments with Managed Identity and
  least-privilege role assignments
- Docker Compose stack and a one-command development script
- Eleven documents covering architecture, API, security, testing, deployment,
  Azure integration, troubleshooting and contribution standards

### Fixed during initial development

- FastAPI startup failure from combining `Annotated[..., Depends]` with a default
  `Depends` value in eight route modules
- 500 response on validation errors caused by a non-serialisable `ValueError` in
  the Pydantic error context
- Retrieval mis-ranking caused by signed hashed embeddings producing negative
  cosine scores for short queries
- Depressed groundedness scores caused by the local LLM appending boilerplate to
  answer text
- Alembic migration `NameError` from unrendered custom column type imports
- Frontend bundle exceeding the chunk size budget

### Known limitations

No OCR; synchronous ingestion and evaluation; per-process rate limiting; no
refresh-token rotation; no SSO or MFA; Azure AI Search provisioned but not wired
into retrieval; guardrails are heuristic rather than a security boundary.
