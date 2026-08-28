# sl3dge

sl3dge is a verification-first financial control engine for Razorpay payment
lifecycles. It rebuilds expected financial state from approved controls,
compares it with observed payment, refund, settlement, and bank events, and
keeps AI advisory: deterministic Python establishes every match, amount, and
verdict.

```text
Next.js -> FastAPI -> SQLAlchemy -> Supabase PostgreSQL
                    |             -> private Supabase Storage
                    |-> Razorpay read APIs (worker)
                    `-> LangGraph -> optional Groq structured output
```

The browser calls FastAPI only. Supabase service credentials, Razorpay keys, and
the Groq key are backend-only.

## What is implemented

- Decimal-safe MDR, GST, settlement-SLA, refund-integrity, and settlement
  arithmetic controls
- Deterministic/scored event matching; ambiguous matches remain `UNRESOLVED`
- Exact seeded NovaCart run, mutation testing, coverage, lineage,
  counterfactuals, root-cause clustering, and exception cases
- Versioned agreement/control proposal review with maker-checker approval
- Three bounded LangGraph workflows with deterministic verification and durable
  PostgreSQL checkpoints in deployed environments
- Auth0-compatible OIDC, roles, tenant context, PostgreSQL RLS, audit records,
  private Storage metadata, and production fail-closed configuration
- Bounded, idempotent Razorpay synchronization jobs and a separate worker
- Alembic migrations, health probes, hardened non-root containers, and CI

Razorpay live/sandbox behavior cannot be certified until project credentials are
provided. The deterministic seeded pipeline works without Razorpay or an LLM.

## Seeded acceptance contract

The generator and [manifest](data/demo/manifest.json) are authoritative.

| Record | Exact count |
| --- | ---: |
| Orders | 500 |
| Payments | 500 |
| Settlements | 84 |
| Bank entries | 84 |
| Refunds | 5 |
| Chargebacks | 6 |
| Financial events | 1,179 |
| Event edges | 1,495 |
| Control evaluations | 2,018 |

Stable demo IDs are `PAY_82HD9` (hidden MDR violation), `REF_91` (duplicate
refund), `SET_1042` (SLA violation), `RC_MDR_01` (systemic root cause), and
`UNR_003` (unresolved match).

## Quick start with Docker

Requirements: Docker Engine with Compose v2.

1. Copy `compose.env.example` to `.env` and replace the database password.
2. Leave OIDC disabled for an isolated local demo, or configure the OIDC fields.
3. Start the parity stack:

```bash
docker compose up --build
```

Open `http://localhost:3000`. FastAPI liveness and readiness are available at
`http://localhost:8000/health/live` and `/health/ready`. Compose applies Alembic
migrations and initializes the LangGraph checkpoint schema before starting the
API and worker.

## Native development

Requirements: Python 3.12, Node 24, pnpm 10.33, and PostgreSQL 16 when durable
persistence is required.

```bash
python -m venv backend/.venv
backend/.venv/Scripts/python -m pip install -e "./backend[dev]"
pnpm --dir frontend install --frozen-lockfile
```

Copy `.env.example` to `.env`. Launch the backend from the repository root so
it reads that file:

```bash
backend/.venv/Scripts/python -m alembic -c backend/alembic.ini upgrade head
backend/.venv/Scripts/python -m app.agents.checkpoint setup
backend/.venv/Scripts/python -m uvicorn app.main:app --app-dir backend --reload --port 8000
```

Next.js reads public configuration from `frontend/.env.local`; copy only the
`NEXT_PUBLIC_*` values from the root `.env`, never backend secrets. Then run:

```bash
pnpm --dir frontend dev
```

Run the worker in a separate terminal when testing Razorpay jobs:

```bash
backend/.venv/Scripts/python -m app.workers.runner
```

## Verification

```bash
backend/.venv/Scripts/python -m ruff format --check backend/app backend/tests backend/alembic
backend/.venv/Scripts/python -m ruff check backend/app backend/tests backend/alembic
backend/.venv/Scripts/python -m pytest -q backend/tests
pnpm --dir frontend exec tsc --noEmit
pnpm --dir frontend lint
pnpm --dir frontend build
```

The current implementation gap register and prototype completion estimate are maintained in [docs/PENDING_TASKS.md](docs/PENDING_TASKS.md).

CI repeats these checks against PostgreSQL and builds both containers.

## Production deployment

Use a Supabase transaction pooler URL for `DATABASE_URL`, a direct or session
pooler URL for `MIGRATION_DATABASE_URL`, and keep prepared statements disabled
for transaction-pooler compatibility. Build the frontend with its final public
API and OIDC values; `NEXT_PUBLIC_*` settings are compiled into the bundle.

Production startup validates TLS, OIDC, explicit HTTPS CORS, forced HTTPS,
Supabase Storage credentials, a separate migration DSN, and the checkpoint DSN.
The full release procedure, Auth0 claim setup, rollback, and smoke checks are in
[docs/operations.md](docs/operations.md).

## Documentation

- [Architecture and current status](index.md)
- [Operations and deployment](docs/operations.md)
- [Backend contract](docs/backend.md)
- [Frontend contract and demo flow](docs/frontend.md)
- [Engineering stack and build order](docs/techstack.md)
- [Product scope](docs/features.md)
