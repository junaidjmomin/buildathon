# GLM 5.3 Coding Guidelines for sl3dge

This document is the operating guide for GLM 5.3 when implementing or reviewing
sl3dge. It is deliberately strict: correctness, auditability, and reproducible
verification take priority over speed or cosmetic changes.

## 1. Read before editing

1. Read `docs/features.md`, `docs/backend.md`, `docs/frontend.md`,
   `docs/techstack.md`, and `docs/PENDING_TASKS.md` completely.
2. Follow the specification authority order: features define scope and priority;
   backend defines API/domain contracts; frontend defines UI/demo behavior;
   techstack defines engineering choices.
3. Treat the latest section explicitly marked authoritative as the winner if a
   conflict is discovered. Do not silently invent a third interpretation.
4. Inspect the current implementation, migrations, tests, and git diff before
   proposing changes. Preserve unrelated user work.

## 2. Work one bounded checklist item at a time

For every task, write down: contract affected, files to change, invariants,
tests to add or update, and verification commands. Do not start new product
features while a blocking correctness, security, performance, or migration
finding remains unresolved. Never mark a task complete because code was written;
mark it complete only after the relevant tests and checks pass.

Required implementation loop:

1. Inspect and reproduce the issue.
2. Make the smallest coherent patch with `apply_patch`.
3. Add a regression test that would fail before the patch.
4. Run focused tests, then the complete backend and frontend checks.
5. Review the final diff for accidental API, data, or UI regressions.
6. Report files changed, tests run, failures, and remaining external blockers.

## 3. Financial correctness is non-negotiable

- Use Python `Decimal` for every monetary amount, rate, tolerance, comparison,
  aggregation, and persisted financial result.
- Control DSL JSON must encode financial values as strings, for example
  `"rate": "0.0155"`, `"gst_rate": "0.18"`, and `"tolerance": "0.01"`.
- Parse and validate those strings at the domain boundary. Reject non-finite or
  malformed values with a safe, structured error.
- Never introduce Python `float` arithmetic in the deterministic engine or raw
  JSON numeric literals for rates, amounts, fees, taxes, or tolerances.
- Frontend code must treat financial API values as decimal strings. It may format
  them for display, but must not use JavaScript `Number` as financial truth.
- Keep expected amount, actual amount, difference, tolerance, and impact sourced
  from the evaluation/control result; do not hardcode an outcome in production
  logic or a dashboard component.

## 4. Source and run contracts

- The only run source values are `DEMO`, `CSV_UPLOAD`, and `RAZORPAY`.
- Use the field name `source_type` consistently in backend models, API payloads,
  persistence, and frontend types. Do not add a competing `source` field to run
  summaries or list items.
- A selected run must be explicit. Do not silently fall back to NovaCart when a
  real uploaded or Razorpay run exists; show an empty/loading/error state instead.
- Seeded IDs belong in the synthetic fixture adapter and tests only. Domain
  services must operate on IDs and data supplied by the run, not branch on
  `PAY_82HD9`, `REF_91`, `SET_1042`, or other demo constants.

## 5. Deterministic graph, matching, and lineage

- Canonical events and `EventEdge` records are created by deterministic Python
  code. LLMs must never create edges or force an ambiguous match.
- `FUZZY` matching must be scored and reproducible. Permitted evidence includes
  normalized string similarity, amount equality/tolerance, timestamp proximity,
  and reference-token overlap. Persist the confidence score and matching
  evidence. Scores below the configured threshold become `UNRESOLVED`.
- Persist violation lineage (`PRIMARY` or `DOWNSTREAM`, parent violation ID,
  root violation ID, and causal evidence). Read lineage from persistence; do not
  reconstruct it with payment-ID naming heuristics in API handlers.
- Root-cause direct, downstream, and total impacts must be Decimal values and
  must round-trip through ORM, migration, repository, and API tests.
- Downstream effects must not double-count the same verified financial impact.

## 6. Summary and dashboard invariants

The authoritative summary is the backend `RunSummary` response. The invariant is:

`pass_count + violation_count + warning_count + unresolved_count == control_evaluation_count`

Unresolved relationship matches are separate (`unresolved_relationship_count`)
and must not be added to the control-outcome breakdown. The frontend renders this
single summary and does not calculate alternate financial truth from fixtures,
hardcoded demo IDs, or independently fetched counts.

## 7. AI, LangGraph, MCP, and provenance

- Keep AI provider access behind the provider abstraction. Configure
  `LLM_PROVIDER` and `LLM_MODEL`; do not hardcode provider calls in business
  logic. A reproducible development/demo default may be documented in config.
- If no key or model is configured, the deterministic pipeline must remain fully
  functional. AI-only actions must return a clear degraded/deterministic result,
  never a fake success.
- LangGraph may orchestrate bounded hypothesis/investigation steps, but controls,
  arithmetic, matching, lineage, and verification remain deterministic.
- Provenance must be truthful: label orchestration, LLM, MCP, and Razorpay context
  only when those paths actually ran. Record provider/model and evidence sources.
  Never call or label Razorpay context for DEMO or CSV runs.

## 8. Persistence, migrations, and Supabase

- FastAPI + SQLAlchemy + Alembic remain the backend architecture. Supabase is the
  managed PostgreSQL and private Storage layer, not a replacement for domain
  services.
- Every schema change needs a forward migration, a safe downgrade where
  practical, ORM alignment, and a round-trip test. Keep one linear Alembic head.
- Tenant IDs must scope every query and mutation. Privileged Supabase, Groq, and
  Razorpay credentials stay backend-only.
- Store uploaded PDFs/CSVs/evidence artifacts in private Storage and metadata/path
  references in PostgreSQL; never expose service keys to the browser.
- Prefer bulk SQL operations and bounded queries. Avoid N+1 repository loops and
  measure persistence separately from deterministic engine time.

## 9. API, UI, and error behavior

- Preserve the structured error envelope `{error: {code, message, details,
  request_id}}` and include request IDs in logs.
- Upload endpoints may report per-row CSV errors (capped response plus true total)
  while allowing unrelated valid rows to proceed. Never discard valid rows merely
  because another row is malformed.
- Every route needs explicit loading, empty, partial-error, retry, keyboard-focus,
  and responsive behavior where applicable. Do not render a success state from a
  failed request.
- Keep navigation run-aware and cache-safe. Switching tabs must not trigger a
  surprise seeded reload or erase the selected run.

## 10. Mandatory verification before handoff

From `backend/` run:

```text
python -m pytest -q
python -m ruff check app tests
python -m ruff format --check app tests
```

From `frontend/` run:

```text
pnpm test -- --run
pnpm exec tsc --noEmit
pnpm lint
pnpm build
```

When persistence or deployment files changed, also run the applicable Alembic
upgrade test, container build/smoke checks, and a focused API round-trip test.
Do not suppress failures, weaken assertions, or claim a command passed without
showing its result.

## 11. Handoff format

End every GLM 5.3 task with:

- concise outcome and percentage complete only if it is evidence-based;
- exact files and migrations changed;
- contracts/invariants affected;
- focused and full verification results;
- known limitations and external credentials/platform blockers;
- the next unchecked item from `docs/PENDING_TASKS.md`.

