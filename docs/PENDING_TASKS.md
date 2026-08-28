# sl3dge Implementation Checklist

Status date: 2026-08-29

This is the authoritative completion ledger for implementation requests made in the project conversation. It does not redefine product behavior. Specification authority remains `features.md`, `backend.md`, `frontend.md`, then `techstack.md`.

Legend: `[x]` implemented and verified, `[~]` being completed in the current implementation pass, `[ ]` not yet complete, `[E]` requires external credentials/platform ownership.

## Product and documentation foundation

- [x] Read and reconcile the handoff Markdown files before implementation.
- [x] Add the Specification Authority section to every handoff document.
- [x] Remove duplicate authoritative build orders, acceptance tests, and demo flows.
- [x] Normalize stable IDs to `PAY_82HD9`, `REF_91`, `SET_1042`, `RC_MDR_01`, and `UNR_003`.
- [x] Normalize the duplicate-refund identifier to `REF_91`.
- [x] Encode money, rates, and tolerances as decimal strings and parse them with Python `Decimal`.
- [x] Define financial tolerances in typed control parameters.
- [x] Make FUZZY matching deterministic and explicitly prohibit LLM-created `EventEdge` records.
- [x] Define one exact seeded NovaCart manifest and use its counts consistently.
- [x] Keep LLM calls provider-abstracted with reproducible Groq demo defaults and deterministic no-key fallback.
- [x] Document Supabase Postgres/Storage as infrastructure behind FastAPI.
- [x] Create this conversation-wide checklist.

## Deterministic engine and seeded proof

- [x] Canonical financial event model and deterministic event graph.
- [x] Typed control DSL with effective-dated versions.
- [x] MDR, GST, settlement SLA, refund integrity, and settlement arithmetic controls.
- [x] Violation lineage and no-double-counting downstream financial impact.
- [x] Root-cause proof, counterfactual reconstruction, and evidence views for seeded data.
- [x] Mutation testing, blind-spot detection, candidate backtest, and coverage measurement.
- [x] Keep explicit fixture values as test inputs while calculating outcomes in the engine.
- [x] LangGraph bounded workflows for AI proposals/investigations; deterministic calculations remain outside the LLM.
- [x] Export the authoritative generator to all six `data/demo/*.csv` files plus agreement and ground truth.
- [x] Add one manifest regression for counts, IDs, leakage, mutations, and coverage.
- [x] Run mutation testing against persisted uploaded runs (`POST
  /runs/{run_id}/mutation-tests`) without mutating canonical events; the same
  deterministic suite now works for CSV runs and seeded NovaCart.

## Agreements and controls

- [x] Always-visible merchant agreement PDF upload.
- [x] Store agreement PDFs privately in Supabase Storage and metadata in Postgres.
- [x] Manual agreement-clause API, UI, idempotency, audit entry, and migration.
- [x] Bounded control proposal extraction with human verification and maker-checker approval.
- [x] Graceful AI-only-action degradation without an LLM.
- [x] Add dedicated agreement-detail and control-detail routes with full provenance
  (`/agreements/{id}` shows contract record, clause provenance, and approved controls
  derived from the agreement; `/controls/{logical_control_key}` shows typed parameters,
  contract provenance with an agreement link, and the immutable version timeline from
  `/controls/{key}/versions`; list pages link into both).
- [x] Add frontend tests for PDF upload and manual clause entry
  (`frontend/src/app/agreements/page.test.tsx`, run by `pnpm test`).

## CSV ingestion and uploaded runs

- [x] Multi-file CSV selection in one submission.
- [x] Content-based classification for all six source types.
- [x] Per-file status, row count, confidence, and evidence.
- [x] Decimal validation for money-like columns.
- [x] Add the visible `Create run and execute controls` continuation.
- [x] Verify artifact hashes and attach artifacts to the resulting run.
- [x] Normalize all six sources into canonical events with source snapshots.
- [x] Aggregate settlement rows and build exact edges.
- [x] Execute scored bank/settlement matching with feature evidence and ambiguity handling.
- [x] Persist `UNRESOLVED_MATCH` rather than forcing ambiguous matches.
- [x] Execute controls and persist evaluations, violations, generalized roots, audit logs, and metrics.
- [x] Return row-level validation errors without rejecting unrelated valid rows
  (invalid money values and empty required identifiers are collected per row at
  upload — capped at 50 reported with a true total — and execution drops only
  invalid rows while preserving valid rows and recording the dropped count in the
  persisted `VALIDATE_INPUTS` stage).
- [x] Persist exception cases/evidence packs for uploaded-run violations
  (verified end-to-end by `backend/tests/test_source_run_api.py`: cases, evidence,
  unresolved queue, and audit rows are persisted for a six-file uploaded run).
- [~] Add a full six-file API and browser E2E acceptance test
  (API-level done: `backend/tests/test_source_run_api.py` covers the six-file bundle
  upload → run → summary/violations/root-causes/cases/audit, artifact-hash tamper
  rejection, live payment drill-downs, and row-error reporting; the browser-level
  Playwright walkthrough is still open).

## Run-aware frontend and navigation

- [x] Keep cached seeded data during ordinary tab switching and show navigation progress.
- [x] Fix the Auth0 callback/session loop and use the configured frontend callback route.
- [x] Stop auto-loading NovaCart when a real uploaded run exists.
- [x] Persist the selected run and make Overview use it.
- [x] Remove hardcoded NovaCart IDs from Controls and Exceptions navigation.
- [x] Audit every route for seeded-only assumptions and add safe live-run behavior.
- [x] Add a run list and run selector.
- [x] Add uploaded-run transaction detail and event-edge graph views
  (payment detail, graph, lineage, and counterfactual now work for uploaded runs:
  `backend/app/services/live_payment_views.py` builds them deterministically from
  persisted events/edges/evaluations/violations, and the existing frontend payment
  page has no seeded-only gating).
- [x] Generalize expected-vs-actual, lineage, graph, counterfactual, and control
  coverage endpoints
  (live Postgres branch in `backend/app/api/router.py` backed by
  `backend/app/services/live_payment_views.py`; `/control-coverage` intentionally
  reports structural edge coverage for uploaded runs without claiming seeded
  ground-truth precision/recall).
- [x] Expose the mutation-test entry point from the selected run dashboard and
  pass the selected run to candidate-control backtests; the UI explains when a
  candidate is not registered for that run instead of showing a dead seeded-only
  action.
- [x] Add route-level empty, partial-error, retry, keyboard, focus, and responsive states
  (retry actions on error panels across controls, agreements, exceptions, root-causes,
  run coverage, and data sources; fixed the exceptions page rendering "No exception
  cases" on API failure and the data page rendering "BACKEND CREDENTIALS REQUIRED" on a
  failed status query; global `:focus-visible` outline in `globals.css`).
- [~] Add component tests and Playwright coverage for the 22-step demo
  (Vitest + Testing Library + jsdom wired up with `pnpm test` — 17 tests across
  `active-run.test.tsx` and `agreements/page.test.tsx`; Playwright browser coverage of
  the 22-step demo is still open).

## Root causes, cases, and evidence

- [x] Generalize root grouping beyond MDR to GST, SLA, refund, and settlement arithmetic.
- [x] Persist cluster membership and unaffected comparison evidence in each
  root-cause verification record.
- [x] Add the MDR-over-time comparison chart (run-scoped temporal replay groups
  all card transactions by capture month and renders Decimal-backed deltas).
- [x] Generalize live case creation/transitions for uploaded and Razorpay runs
  (persisted investigation cases use optimistic version checks and verified-evidence
  gates for every transition).
- [~] Link every displayed financial value to snapshot, control version, and
  evaluation (live payment evidence now exposes all three provenance references;
  dashboard aggregate metrics now link to evidence/coverage routes, while
  transaction-level provenance for every aggregate remains a future drill-down).
- [x] Add evidence-pack export to private Storage (`POST
  /runs/{run_id}/evidence-export`); the endpoint fails closed when PostgreSQL or
  private Supabase Storage is not configured.

## API, jobs, security, and operations

- [x] Auth0 tenant/role claims and backend-only privileged credentials.
- [x] Supabase through SQLAlchemy/Alembic plus private Storage.
- [x] Local/deployed database swap through configuration.
- [x] Read-only Razorpay connector contracts and durable job option.
- [x] Retry-safe mutation-test persistence.
- [x] Keep readiness schema revision aligned with the Alembic head and enforce
  formatted, ORM-aligned lineage migration `0012_durable_lineage_metrics`.
- [x] Normalize errors to `{error: {code, message, details, request_id}}` and test them.
- [x] Persist and expose run stages from upload through finalize.
- [x] Add structured stage logs and operational metrics (`GET
  /runs/{run_id}/operational-metrics`; alert delivery remains an external
  observability-platform concern). The run-scoped Operations UI now exposes
  persisted stage timings, throughput counters, and failed-stage state.
- [x] Start built containers in CI and smoke-test readiness and connectivity
  (`.github/workflows/ci.yml` `containers` job: Postgres service, backend
  container on host network, in-container `alembic upgrade head`, live/ready/
  Docker healthcheck polling, `/api/v1/health` + `/capabilities/infrastructure`
  smoke requests, frontend container poll on `:3000`, log dump on failure;
  verified green on push `61336f9`, run 33200190472).
- [x] Complete dependency/security scanning and remediate findings.
- [x] Push the final verified implementation to the configured remote
  (`main` at `61336f9`; CI backend, frontend, and containers jobs all green,
  including in-container migrations, readiness polling, and API smoke requests).

## Optional/P2 expansion

- [x] Schema-drift detection and mapping review (deterministic source-specific
  column allowlists, explicit unmapped-column evidence, and frontend review
  warning without rejecting otherwise valid uploads).
- [x] Temporal replay using approved historical MDR control versions (`POST
  /runs/{run_id}/temporal-replay` and the run-scoped replay UI).
- [ ] Natural-language analyst queries with deterministic citations.
- [ ] Drift-monitoring UI.
- [ ] Optional Supabase Realtime progress.
- [ ] Optional read-only Razorpay MCP evidence.

## External completion requirements

- [E] Razorpay test/live credentials and contract testing.
- [E] Production Supabase backups/PITR, quotas, alerts, roles, and policy review.
- [E] Production Auth0 domain, URLs, and namespaced claim Action.
- [E] Production Groq quota and AI failure-policy approval.
- [E] DNS/TLS, WAF, logs, paging, privacy/retention review, penetration testing, and Razorpay security approval.

## Verified baseline before this pass

- Backend: 118 passed, 1 skipped.
- Frontend TypeScript, lint, and production build passed.
- Supabase revision: `0012_durable_lineage_metrics` (migration is verified in a
  fresh database; applying it to an existing external database remains an
  operator-authorized deployment action).
- Seeded NovaCart proof path: functional.
- Fully functional deterministic prototype estimate after this pass: 94%.

## 2026-08-29 sequential implementation pass

- Mutation testing is no longer seeded-only: uploaded CSV runs reconstruct their
  canonical payment lifecycles from persisted events/edges and execute the same
  isolated mutation engine. Results are persisted idempotently and audited.
- Candidate backtest accepts an optional `run_id` and evaluates the persisted
  run when the candidate control exists; unsupported control types fail closed
  with an explicit 422 rather than returning fabricated metrics.
- Temporal replay now compares an approved MDR version against the run's
  effective baseline with Decimal arithmetic, violation deltas, and per-payment
  evidence. It is deterministic and does not rewrite canonical data.
- Backend verification: 118 passed, 1 skipped; Ruff clean. Frontend verification:
  17 tests passed, TypeScript, lint, and production build passed.

## 2026-08-29 remaining-task implementation pass

- Added deterministic evidence-pack export for persisted runs. The JSON bundle
  includes the run summary, stage timeline, violations, root causes, and cases;
  it is content-addressed, stored under the tenant's private Storage prefix, and
  recorded in PostgreSQL with an audit event. No public URL or browser-side
  privileged credential is exposed.
- Added an Overview action for live runs to export the private evidence pack and
  report the artifact identifier or configuration failure without blocking other
  run actions.
- Generalized the control-coverage graph to uploaded runs. Coverage is calculated
  from persisted canonical edge counts and persisted control evaluations, with
  ungoverned method-classification and unsupported-deduction edges reported
  honestly rather than borrowing seeded ground-truth values.
- Overview now links to the same run-scoped coverage view for both seeded and
  uploaded runs.
- Live payment evidence now carries evaluation ID, control version, and source
  snapshot IDs into the API/UI so an analyst can trace each displayed
  expected/actual amount to its deterministic inputs.
- Uploaded-run control coverage now uses persisted edge/evaluation evidence and
  is available from the same run-scoped UI as seeded coverage.
- Root-cause records now persist explicit cluster membership and an unaffected
  comparison basis for the same control family and run.
- Temporal replay includes a monthly MDR delta series used by the UI's
  MDR-over-time chart.
- CSV classification now reports deterministic schema drift and unmapped columns;
  operational metrics expose stage durations, completion/failure counts, and
  persisted event/evaluation totals for each run.
- Added the run-scoped Operations UI (`/runs/[runId]/operations`) and linked
  dashboard aggregate metrics to evidence-oriented drill-down destinations.

## 2026-08-28 dependency audit (verified)

- Audited the pinned project dependencies in a clean virtual environment (not the
  polluted global Python environment, which produced 137 false findings).
- Runtime dependencies: no known vulnerabilities.
- Dev-only findings: `pytest 8.4.2` (PYSEC-2026-1845, fixed in 9.0.3) and the
  venv-bundled `setuptools 65.5.0`. Neither ships in the runtime container.
- Remediation: `backend/pyproject.toml` dev pin bumped to `pytest>=9,<10`;
  full backend suite re-run under pytest 9 — 111 passed, 1 skipped.

## 2026-08-28 throughput fix (verified)

- Root cause: bulk upserts executed through `Session.execute`, whose ORM bulk-insert
  path splits rows with different NULL-column patterns into separate statements —
  one hosted-Postgres round trip per group (250 evaluations ≈ 84 seconds).
- Fix: execute bulk statements through `session.connection()` in
  `backend/app/persistence/repository.py` (`_bulk_upsert`, `_bulk_insert_ignore`).
- Regression test: `test_bulk_upsert_bypasses_orm_session_insert_grouping`.
- Re-measured on the configured Supabase database with a 250-payment bundle:
  1250 evaluations, 44.9 s → 10.0 s end to end (engine 2.5 s, persistence 7.5 s,
  496 evaluations/sec, 135 queries → 15). Benchmark data written under a
  disposable `bench-throughput` tenant and removed afterward.
- Baseline after the fix: backend 111 passed, 1 skipped; frontend TypeScript,
  lint, and production build pass.
- Run-aware default: a seeded (NovaCart) selection is now session-scoped only and
  never persists as the default workspace over real uploaded runs
  (`frontend/src/lib/active-run.ts` `resolveActiveRun`).
