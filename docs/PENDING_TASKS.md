# sl3dge Implementation Checklist

Status date: 2026-08-28

This is the authoritative completion ledger for implementation requests made in the project conversation. It does not redefine product behavior. Specification authority remains `features.md`, `backend.md`, `frontend.md`, then `techstack.md`.

Legend: `[x]` implemented and verified, `[~]` being completed in the current implementation pass, `[ ]` not yet complete, `[E]` requires external credentials/platform ownership.

## Product and documentation foundation

- [x] Read and reconcile the handoff Markdown files before implementation.
- [x] Add the Specification Authority section to every handoff document.
- [x] Remove duplicate authoritative build orders, acceptance tests, and demo flows.
- [x] Normalize stable IDs to `PAY_82HD9`, `REF_91`, `SET_1042`, `RC_MDR_01`, and `UNR_003`.
- [x] Replace `REFUND_91` with `REF_91`.
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
- [ ] Export the authoritative generator to all six `data/demo/*.csv` files plus agreement and ground truth.
- [ ] Add one manifest regression for counts, IDs, leakage, mutations, and coverage.

## Agreements and controls

- [x] Always-visible merchant agreement PDF upload.
- [x] Store agreement PDFs privately in Supabase Storage and metadata in Postgres.
- [x] Manual agreement-clause API, UI, idempotency, audit entry, and migration.
- [x] Bounded control proposal extraction with human verification and maker-checker approval.
- [x] Graceful AI-only-action degradation without an LLM.
- [ ] Add dedicated agreement-detail and control-detail routes with full provenance.
- [ ] Add frontend tests for PDF upload and manual clause entry.

## CSV ingestion and uploaded runs

- [x] Multi-file CSV selection in one submission.
- [x] Content-based classification for all six source types.
- [x] Per-file status, row count, confidence, and evidence.
- [x] Decimal validation for money-like columns.
- [~] Add the visible `Create run and execute controls` continuation.
- [~] Verify artifact hashes and attach artifacts to the resulting run.
- [~] Normalize all six sources into canonical events with source snapshots.
- [~] Aggregate settlement rows and build exact edges.
- [~] Execute scored bank/settlement matching with feature evidence and ambiguity handling.
- [~] Persist `UNRESOLVED_MATCH` rather than forcing ambiguous matches.
- [~] Execute controls and persist evaluations, violations, generalized roots, audit logs, and metrics.
- [ ] Return row-level validation errors without rejecting unrelated valid rows.
- [ ] Persist exception cases/evidence packs for uploaded-run violations.
- [ ] Add a full six-file API and browser E2E acceptance test.

## Run-aware frontend and navigation

- [x] Keep cached seeded data during ordinary tab switching and show navigation progress.
- [x] Fix the Auth0 callback/session loop and use the configured frontend callback route.
- [~] Stop auto-loading NovaCart when a real uploaded run exists.
- [~] Persist the selected run and make Overview use it.
- [~] Remove hardcoded NovaCart IDs from Controls and Exceptions navigation.
- [~] Audit every route for seeded-only assumptions and add safe live-run behavior.
- [ ] Add a run list and run selector.
- [ ] Add uploaded-run transaction detail and event-edge graph views.
- [ ] Generalize expected-vs-actual, lineage, graph, and counterfactual endpoints.
- [ ] Add route-level empty, partial-error, retry, keyboard, focus, and responsive states.
- [ ] Add component tests and Playwright coverage for the 22-step demo.

## Root causes, cases, and evidence

- [~] Generalize root grouping beyond MDR to GST, SLA, refund, and settlement arithmetic.
- [ ] Persist cluster membership and unaffected comparison evidence.
- [ ] Add the MDR-over-time comparison chart.
- [ ] Generalize live case creation/transitions for uploaded and Razorpay runs.
- [ ] Link every displayed financial value to snapshot, control version, and evaluation.
- [ ] Add evidence-pack export to private Storage.

## API, jobs, security, and operations

- [x] Auth0 tenant/role claims and backend-only privileged credentials.
- [x] Supabase through SQLAlchemy/Alembic plus private Storage.
- [x] Local/deployed database swap through configuration.
- [x] Read-only Razorpay connector contracts and durable job option.
- [x] Retry-safe mutation-test persistence.
- [ ] Normalize errors to `{error: {code, message, details, request_id}}` and test them.
- [ ] Persist and expose run stages from upload through finalize.
- [ ] Add structured stage logs and operational metrics/alerts.
- [ ] Start built containers in CI and smoke-test readiness and connectivity.
- [ ] Complete dependency/security scanning and remediate findings.
- [ ] Push the final verified implementation to the configured remote.

## Optional/P2 expansion

- [ ] Schema-drift detection and mapping review.
- [ ] Temporal replay using historical controls.
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

- Backend: 105 passed, 1 skipped.
- Frontend TypeScript, lint, and production build passed.
- Supabase revision: `0010_manual_agreement_clauses`.
- Seeded NovaCart proof path: functional.
- Fully functional prototype estimate before upload-run completion: 84%.
