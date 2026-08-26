# sl3dge — Tech Stack & Engineering Handoff for Codex

## Specification Authority

Authority order:

1. `features.md` defines product scope and priority.
2. `backend.md` defines backend behavior, API, and domain contracts.
3. `frontend.md` defines UI behavior and the recorded demo flow.
4. `techstack.md` defines engineering implementation choices.

If two sections conflict, the later section explicitly marked **authoritative**
wins. This document contains one authoritative engineering build order and one
authoritative differentiated acceptance test.

## 0. Goal

This document is the engineering contract for implementing **sl3dge**.

sl3dge is a verification-first AI Finance Controller.

Core loop:

```text
Agreement / Policy
        ↓
Structured Financial Controls
        ↓
Financial Event Graph
        ↓
Expected State
        ↓
Actual State
        ↓
Deterministic Verification
        ↓
Violation / Pass / Unresolved
        ↓
AI Root-Cause Hypothesis
        ↓
Backtest / Evidence Verification
        ↓
Proven / Rejected / Unresolved
```

The system must be easy to demo locally, deterministic where it matters, and able to run without an LLM for its core control engine.

---

# 1. Monorepo Layout

Recommended:

```text
sl3dge/
├── frontend/
├── backend/
├── data/
│   ├── demo/
│   └── fixtures/
├── docs/
│   ├── backend.md
│   ├── frontend.md
│   └── techstack.md
├── docker-compose.yml
├── .env.example
├── README.md
└── Makefile
```

Do not over-engineer into microservices.

One frontend + one backend + one PostgreSQL database is enough. Supabase hosts
the deployed Postgres and private object storage; it does not add another
application backend.

---

# 2. Backend Stack

## Language
Python 3.12+

## API
FastAPI

## Validation
Pydantic v2

## ORM
SQLAlchemy 2.x

## Migrations
Alembic

## Database
Supabase Postgres (PostgreSQL 16+) in deployed environments; local PostgreSQL is
the swappable development fallback through `DATABASE_URL`.

## Batch data processing
Polars

Why Polars:
- fast enough for large synthetic batches
- predictable tabular APIs
- useful for ingestion and control batches

Pandas is acceptable if implementation speed is substantially better, but pick one and stay consistent.

## HTTP client
httpx

## Testing
pytest
pytest-asyncio if needed

## Lint/format
Ruff

## Type checking
mypy or pyright; pyright is preferable if the team already uses it

---

# 3. Frontend Stack

## Framework
Next.js 15+ App Router

## Language
TypeScript

## Styling
Tailwind CSS

## Components
shadcn/ui

## Server state
TanStack Query

## Forms
React Hook Form

## Validation
Zod

## Graph visualization
React Flow

## Charts
Recharts

## Icons
Lucide React

## Testing
Vitest
React Testing Library

Optional:
Playwright for one full demo-flow e2e test.

---

# 4. AI Layer

Use exactly one provider abstraction. The reproducible development/demo default
is Groq with `openai/gpt-oss-120b`, configured by environment rather than
hardcoded in business logic:

```env
LLM_PROVIDER=groq
LLM_MODEL=openai/gpt-oss-120b
GROQ_API_KEY=
```

Implementation should expose an internal interface such as:

```python
class LLMClient(Protocol):
    async def structured_completion(
        self,
        *,
        system: str,
        prompt: str,
        schema: type[BaseModel],
    ) -> BaseModel:
        ...
```

Do not spread provider-specific calls through services.

If provider, model, or key configuration is missing, AI-only actions return an
explicit unavailable/degraded response. The full deterministic transaction,
control, mutation, coverage, and case pipeline remains operational.

---

# 5. What AI Is Allowed To Do

Allowed:
- contract clause → candidate control
- root-cause explanation
- root-cause hypothesis generation
- schema mapping suggestion
- human-readable evidence summary

Not allowed:
- arithmetic truth
- control pass/fail result
- leakage calculation
- precision/recall
- automatic acceptance of financial rules
- forced matching of ambiguous financial records

---

# 6. Why No LangGraph by Default

LangGraph is optional, not assumed.

Use it only if the workflow genuinely benefits from explicit nodes such as:

```text
Collect Evidence
→ Generate Hypothesis
→ Verify Hypothesis
→ Explain Result
```

If a normal service pipeline is simpler, use that.

The project should not advertise "agentic" at the cost of maintainability.

---

# 7. Database and Storage Decision

Use Supabase as infrastructure:

```text
Next.js → FastAPI → Supabase Postgres
                    └─ private Supabase Storage
```

FastAPI remains the only application API and finance trust boundary. Continue
using SQLAlchemy 2.x, Alembic, Pydantic, and repository/domain models through a
standard PostgreSQL connection string. Do not use `supabase-js` for finance
tables and do not let the browser query Postgres directly.

Use private Supabase Storage buckets for merchant agreements, uploaded source
files, and optional evidence artifacts. Store bucket/path/checksum/content-type/
size/provenance metadata in Postgres; do not store large file bodies in rows.

Runtime deployments use the transaction pooler with bounded SQLAlchemy pooling.
Alembic uses a direct or session-mode migration URL. Avoid named prepared
statement assumptions under transaction pooling. Normal queries use a
least-privilege database role.

Supabase Auth and Edge Functions are not required. Realtime is optional P2
run-progress polish. Local PostgreSQL remains supported by swapping connection
configuration only.

Do not introduce:
- Neo4j
- MongoDB
- Redis
- vector DB

unless a concrete requirement appears.

The financial event graph can be stored as relational tables:

```text
financial_events
event_edges
```

For the demo scale, Postgres is sufficient.

---

# 8. Money Handling

Never use binary floating point for finance logic.

Backend:
```python
Decimal
```

Database:
```text
NUMERIC(20, 6)
```

Frontend:
receive decimal values as strings where precision matters.

Use formatting helpers only for presentation.

Control DSL and API JSON encode monetary amounts, rates, and monetary tolerances
as decimal strings. Pydantic parses them into `Decimal` before execution. Raw
JSON floating-point values are invalid for MDR/GST/fee rates, money, and
currency tolerances.

---

# 9. Time Handling

Backend internal standard:
UTC-aware datetimes.

Input adapters may preserve source timezone metadata.

Demo timezone can be Asia/Kolkata where needed.

Settlement SLA control:
- MVP business days = Monday-Friday
- explicit holiday calendar is P2

---

# 10. Control DSL

Do not allow AI-generated Python code.

Use a typed control schema.

Examples:

```json
{
  "type": "MDR_RATE",
  "conditions": {
    "payment_method": "card",
    "card_scope": "domestic"
  },
  "parameters": {
    "rate": "0.0155",
    "tolerance": "0.01"
  }
}
```

```json
{
  "type": "GST_ON_FEE",
  "conditions": {},
  "parameters": {
    "rate": "0.18",
    "tolerance": "0.01"
  }
}
```

```json
{
  "type": "SETTLEMENT_SLA",
  "conditions": {},
  "parameters": {
    "business_days": 2
  }
}
```

The backend owns all executable implementations.

`tolerance` is a currency amount, not a rate. Settlement arithmetic and any
other money comparison use the same decimal-string representation and
`Decimal` parsing. Integer parameters such as `business_days` remain integers.

This is safer and easier to test.

---

# 11. Event Graph Model

Event types:

```text
ORDER
PAYMENT
FEE
TAX
REFUND
SETTLEMENT
BANK_ENTRY
CHARGEBACK
```

Relationships:

```text
PAID_BY
CHARGED_FEE
CHARGED_TAX
REFUNDED_BY
INCLUDED_IN
CREDITED_AS
CHARGEDBACK_BY
RELATED_TO
```

Each edge stores:
- confidence
- matching method
- evidence

`FUZZY` matching is deterministic/scored, never LLM-decided. Supported scoring
features include normalized string similarity, Decimal amount equality or typed
tolerance, timestamp proximity, and reference-token overlap. The matcher emits
an explicit confidence score and feature evidence. A score below the configured
deterministic threshold, or an ambiguous tie, returns `UNRESOLVED` and creates no
edge. LLMs cannot create `EventEdge` records or force ambiguous matches.

The graph is persisted in Postgres and rendered via React Flow.

---

# 12. API Contract

Base:

```text
/api/v1
```

Use REST.

Do not introduce GraphQL.

Critical endpoints:

```text
POST /demo/load

POST /runs
POST /runs/{id}/execute
GET  /runs/{id}/summary

GET  /runs/{id}/violations
GET  /violations/{id}

GET  /runs/{id}/payments/{paymentId}/expected-vs-actual
GET  /runs/{id}/payments/{paymentId}/graph

GET  /runs/{id}/root-causes
GET  /root-causes/{id}
POST /root-causes/{id}/generate-hypothesis
POST /root-causes/{id}/verify-hypothesis

POST /agreements
POST /agreements/{id}/extract-controls

GET  /controls
POST /controls/{id}/approve
```

See `backend.md` for full details.

---

# 13. Local Development

Recommended local services:

```text
frontend    localhost:3000
backend     localhost:8000
postgres    localhost:5432
```

Docker Compose:

```text
postgres
backend
frontend
```

During active development, frontend/backend may run directly on host while Postgres stays in Docker.

---

# 14. Local PostgreSQL Fallback — docker-compose Shape

This Compose database is for offline/local development only. Deployed
environments use Supabase Postgres through environment configuration.

```yaml
services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_DB: sl3dge
      POSTGRES_USER: sl3dge
      POSTGRES_PASSWORD: sl3dge
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data

  backend:
    build: ./backend
    env_file: .env
    depends_on:
      - postgres
    ports:
      - "8000:8000"

  frontend:
    build: ./frontend
    env_file: .env
    depends_on:
      - backend
    ports:
      - "3000:3000"

volumes:
  pgdata:
```

Exact production hardening is not required for the hackathon.

---

# 15. Environment Variables

Root `.env.example`:

```env
DATABASE_URL=postgresql+psycopg://app_role:...@...pooler.supabase.com:6543/postgres
MIGRATION_DATABASE_URL=postgresql+psycopg://migration_role:...@db....supabase.co:5432/postgres
SUPABASE_URL=https://PROJECT_REF.supabase.co
SUPABASE_SERVICE_ROLE_KEY=
SUPABASE_STORAGE_BUCKET=sl3dge-private

# Local fallback example:
# DATABASE_URL=postgresql+psycopg://sl3dge:sl3dge@localhost:5432/sl3dge
# MIGRATION_DATABASE_URL=postgresql+psycopg://sl3dge:sl3dge@localhost:5432/sl3dge

NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api/v1

LLM_PROVIDER=groq
LLM_MODEL=openai/gpt-oss-120b
GROQ_API_KEY=

DEMO_SEED=20260825
CORS_ORIGINS=http://localhost:3000
```

No secrets committed.

All Supabase privileged credentials, Groq keys, and Razorpay credentials are
backend-only. Never put them in `NEXT_PUBLIC_*`. The browser calls FastAPI, and
FastAPI accesses Postgres and Storage. Runtime SQLAlchemy uses a bounded pool
with `pool_pre_ping`; Alembic uses the migration URL.

---

# 16. Recommended Package Management

Frontend:
```text
pnpm
```

Backend:
Either:
```text
uv
```
or Poetry.

Prefer `uv` for speed and simpler setup.

---

# 17. Suggested Commands

Root Makefile:

```text
make dev
make backend
make frontend
make test
make seed
make reset-db
make lint
```

Example behavior:

```text
make seed
```

generates the deterministic demo dataset.

---

# 18. Backend Dependencies

Suggested minimum:

```text
fastapi
uvicorn
pydantic
pydantic-settings
sqlalchemy
psycopg[binary]
alembic
polars
python-multipart
httpx
python-dateutil
supabase  # backend-only Storage client; never used instead of SQLAlchemy for DB access
groq      # selected demo provider behind LLMClient
```

Keep provider and Storage SDKs behind internal adapters.

Dev:

```text
pytest
pytest-asyncio
ruff
pyright
```

Avoid dependency bloat.

---

# 19. Frontend Dependencies

Suggested:

```text
next
react
react-dom
typescript
tailwindcss
@tanstack/react-query
react-hook-form
zod
@hookform/resolvers
reactflow
recharts
lucide-react
```

Plus shadcn/ui generated component dependencies.

---

# 20. PDF / Agreement Parsing

For the Buildathon MVP, keep agreement parsing controlled.

Preferred:
1. accept text-based PDFs
2. extract text server-side
3. preserve page mapping
4. pass extracted text to LLM for structured control proposals

Avoid OCR unless necessary.

Synthetic agreement should be text-based and reliable.

Potential Python package:
```text
pypdf
```

No need for a large document-processing stack.

---

# 21. Data Fixtures

Check the authoritative demo fixture metadata into the repo:

```text
data/demo/
  orders.csv
  payments.csv
  settlements.csv
  bank.csv
  refunds.csv
  chargebacks.csv
  agreement.pdf
  ground_truth.json
  manifest.json
```

`data/demo/manifest.json` is generated/verified against the synthetic generator.
Its exact seeded counts are:

```json
{
  "seed": 20260825,
  "records": {
    "orders": 500,
    "payments": 500,
    "settlements": 84,
    "bank_entries": 84,
    "refunds": 5,
    "chargebacks": 6,
    "financial_events": 1179,
    "event_edges": 1495,
    "control_evaluations": 2018
  },
  "ground_truth": {
    "pass": 439,
    "mdr_rate_deviation": 25,
    "incorrect_gst": 8,
    "duplicate_refund": 5,
    "settlement_sla": 10,
    "unsupported_fee": 8,
    "unresolved": 5
  },
  "known_demo_ids": {
    "mdr_violation": "PAY_82HD9",
    "duplicate_refund": "REF_91",
    "sla_violation": "SET_1042",
    "root_cause": "RC_MDR_01",
    "unresolved": "UNR_003"
  }
}
```

The full manifest also records 439 `PASS`, 56 `VIOLATION`, 0 `WARNING`, 5
`UNRESOLVED`; mutation results 50/47/3 with 0 false positives; and pre-approval
coverage of 2,009 material, 2,000 governed, and 9 ungoverned edges. Decimal
metrics and all acceptance economics are strings. These are exact expectations,
not approximate performance targets.

---

# 22. Testing Strategy

## Backend unit
High coverage for deterministic finance rules.

## Backend integration
One seeded full control run.

## Frontend component
Expected-vs-actual table
violation table
root cause
verification result

## E2E
One Playwright script if time allows:

```text
Load demo
→ Run controls
→ Open PAY_82HD9
→ Assert ₹23.60 leakage
→ Open root cause
→ Verify hypothesis
→ Assert REJECTED
```

This is extremely useful before recording the demo.

---

# 23. CI

GitHub Actions is enough.

Pipeline:

```text
backend lint
backend test
frontend lint
frontend test
frontend build
```

Optional:
Docker build.

Do not spend hackathon time on complex deployment pipelines.

---

# 24. Deployment Recommendation

If public deployment is needed:

```text
Vercel / Next.js
        ↓
FastAPI on Railway / Render / Fly.io / similar
        ├── Groq · openai/gpt-oss-120b (optional AI actions)
        ├── Razorpay direct APIs + optional read-only MCP
        ↓
Supabase
        ├── PostgreSQL
        └── private Storage
```

Supabase is infrastructure, not a replacement for FastAPI or the sl3dge domain
architecture. The frontend continues to call FastAPI only.

For the video, local Docker is acceptable if stable.

Prioritize a reliable demo over production-scale infra.

---

# 25. Logging

Backend:
structured logs.

Minimum fields:

```text
timestamp
level
run_id
stage
duration_ms
count
message
```

AI calls:
log:
- request type
- model
- latency
- success/failure

Do not log secret keys or entire financial payloads.

---

# 26. Error Handling

Frontend should receive machine-readable backend errors.

Format:

```json
{
  "error": {
    "code": "INVALID_SOURCE_SCHEMA",
    "message": "payments.csv is missing payment_id",
    "details": {}
  }
}
```

Frontend maps known codes to user-friendly states.

---

# 27. Engineering Conventions

## Python
- type annotations
- async only where useful
- no business logic in routes
- Decimal for money
- enums for statuses
- pure functions for core finance calculations

## TypeScript
- strict mode
- no `any` in core app code
- typed API boundary
- colocate small UI helpers, not API clients

---

# 28. Git Strategy

Simple:

```text
main
feature/backend-core
feature/frontend-core
feature/ai-controls
feature/demo-flow
```

Small PRs preferred.

No need for elaborate release branches.

---

# 29. Authoritative Engineering Build Order

This is the only build order in this document and matches `backend.md`:

```text
1. Exact seeded manifest + hidden ground truth
2. Canonical domain models
3. Source ingestion and normalization
4. Deterministic/scored Financial Event Graph matching
5. Approved, typed, Decimal control registry
6. Deterministic control engine
7. Expected-vs-Actual, batch metrics, and PAY_82HD9 acceptance slice
8. Financial Mutation Testing on derived data
9. Mutation coverage and control blind-spot detection
10. Candidate-control proposal with agreement provenance
11. Historical + mutation backtest and explicit approval gate
12. Violation Lineage and counterfactual settlement
13. Root-cause clustering
14. Bounded AI hypothesis + independent deterministic verifier
15. Agreement extraction and executable-control provenance UI/API
16. Control Coverage, exception case workflow, and time-versioned controls
17. Direct read-only Razorpay reconciliation ingestion into canonical events/edges
18. Optional read-only Razorpay MCP evidence tools
19. Supabase Postgres/Storage persistence, regression tests, and seeded E2E demo
20. P2 only: temporal replay, schema drift, webhooks, and evidence export
```

---

# 30. Features to Avoid

Do not spend time on:

- blockchain
- wallet login
- tokens/NFTs
- generic finance chatbot
- forecasting
- user accounts
- complex permissions
- billing
- notifications
- full ERP integrations
- huge design system
- a separate graph database
- autonomous policy mutation
- multi-agent architecture for marketing purposes

---

# 31. Demo Performance Targets

Core deterministic run:

```text
500 payments
1,179 financial events
1,495 event edges
2,018 control evaluations
```

Target:
```text
<10 seconds
```

Prefer:
```text
<5 seconds
```

AI actions may be asynchronous at request level, but do not make the user wait through unnecessary chains.

For recorded demo reliability, allow cached AI results for the seeded demo if needed, but keep the deterministic verifier live.

---

# 33. Final Engineering Principle

When deciding between two implementations, prefer the one that makes this statement more demonstrably true:

> **sl3dge does not trust an explanation because AI generated it. It trusts a financial conclusion only when it can verify it against explicit controls and evidence.**


---

# Novelty Extension — Engineering Architecture

## Mutation Testing Subsystem — P0

Backend structure:

```text
backend/app/mutations/
├── registry.py
├── engine.py
├── models.py
├── mdr.py
├── gst.py
├── refund.py
├── settlement.py
├── lifecycle.py
└── coverage.py
```

Each mutation must be deterministic and seedable.

Interface shape:

```python
class Mutation(Protocol):
    def apply(self, dataset: Dataset, target: Target) -> MutatedDataset:
        ...
```

Never mutate canonical source data in place.

Recommended tables:

```text
mutation_tests
mutations
mutation_results
control_backtests
```

## Control Coverage Storage

No graph DB is required.

Use:

```text
event_edges
control_coverage
```

`control_coverage` stores edge, applicable control, and coverage status.

## Violation Lineage Storage

Extend relational `violations` with:

```text
parent_violation_id
root_violation_id
lineage_type
causal_evidence
```

No dedicated causal database is needed at demo scale.

## Time-Versioned Control Storage

Approved controls used by completed runs are immutable.

Use:

```text
logical_control_key
version
effective_from
effective_to
supersedes_control_id
```

Historical reproducibility is required.

## Candidate Control Backtesting

Backtest against:

```text
historical canonical dataset
+
mutation test dataset
```

Return:

```text
historical false positives
historical newly detected violations
mutation detection delta
false-positive delta
```

Backtest is read-only. Approval is separate.

## Frontend Routes / Components

Routes:

```text
/runs/[runId]/mutation-test
/runs/[runId]/coverage
/runs/[runId]/replay
```

Components:

```text
MutationTestSummary
MutationCoverageTable
BlindSpotCard
CandidateControlBacktest
ControlCoverageGraph
ViolationLineage
CounterfactualSettlement
ControlVersionTimeline
TemporalReplayComparison
```

## Updated Testing Strategy

Backend:
- every mutation changes only the intended property
- canonical dataset remains unchanged
- detection-rate calculations are correct
- blind-spot classification is correct
- candidate-control before/after metrics are correct
- false-positive delta is correct
- correct control version is selected at date boundaries
- historical results remain reproducible
- lineage attaches downstream violations to correct root

Frontend:
- mutation summary renders
- blind spot renders
- candidate-control backtest renders before/after
- lineage renders
- control version timeline renders

## Authoritative Differentiated Acceptance Test

This is the only acceptance test in this document. Engineering completion
requires:

1. Generator output equals `data/demo/manifest.json`, including exact IDs and counts.
2. The seeded run has 500 payments, 1,179 events, 1,495 edges, and 2,018 evaluations.
3. `PAY_82HD9` passes gateway-bank matching but fails the 1.55% approved MDR control with `23.60` verified leakage.
4. `REF_91`, `SET_1042`, `RC_MDR_01`, and `UNR_003` resolve to their documented proof cases.
5. All financial JSON rates, amounts, and tolerances are decimal strings parsed to `Decimal`.
6. FUZZY matching is deterministic/scored and sub-threshold or ambiguous matches remain `UNRESOLVED`.
7. The lifecycle graph, exact counterfactual settlement, and primary/downstream lineage render from backend data.
8. A bounded AI hypothesis is independently verified as `REJECTED` for the seeded MDR cluster.
9. At least eight mutation types execute on derived data while canonical data remains unchanged.
10. The seeded mutation result is 50 injected, 47 detected, 3 missed, and 0 false positives.
11. The unsupported-fee blind spot yields a clause-linked `DRAFT` candidate.
12. Backtesting improves detection to 49/50 with false-positive delta 0.
13. Approval is impossible before a successful backtest and explicit user action.
14. Pre-approval coverage is exactly 2,009 material, 2,000 governed, and 9 ungoverned edges.
15. Time-versioned control selection changes from v1 to v2 at the 1 September boundary without rewriting completed runs.
16. The exception case enforces `OPEN → VERIFIED → ESCALATED/RESOLVED` with an audit trail.
17. Five ambiguous cases remain unresolved and no AI creates a financial edge or verdict.
18. Direct Razorpay ingestion is GET-only and maps into the canonical event graph.
19. Optional Razorpay MCP data is supplementary evidence, never financial truth.
20. FastAPI/SQLAlchemy repositories run against local PostgreSQL or Supabase Postgres by configuration alone.
21. Agreements/uploads/evidence use private Supabase Storage objects with Postgres metadata.
22. The browser receives no Supabase privileged credential, Groq key, or Razorpay secret.
23. The deterministic acceptance path works fully with no LLM configuration.

---

# Razorpay Integration Engineering Contract

Razorpay is the next integration layer after the deterministic core, mutation
testing, blind spots, violation lineage and hypothesis verifier.

Use direct HTTPS from the FastAPI backend with `httpx`. Authenticate server-side
with Razorpay test-mode credentials. The frontend calls only sl3dge endpoints.

Direct read-only dependencies:

```text
GET /v1/settlements/recon/combined  primary bulk reconciliation feed
GET /v1/payments                    payment enrichment and completeness
GET /v1/refunds                     refund enrichment and completeness
GET /v1/settlements                 settlement amount/status/UTR enrichment
GET /v1/settlements/{id}            bounded settlement detail
```

All paging, currency-subunit conversion, timestamp normalization, retries and
rate-limit handling live in `backend/app/integrations/razorpay/`. Mapping emits
the existing canonical event and edge schemas; Razorpay-specific database tables
are prohibited unless a later persistence requirement cannot be met with raw
payload provenance.

Optional investigation layer:

```text
Official Razorpay MCP server
Remote endpoint: https://mcp.razorpay.com/mcp
Mode: read-only
Allowed toolsets: payment, refund, settlement
```

Enable only bounded fetch tools. Do not enable or call capture, create, update,
refund-initiation, payout or instant-settlement tools. Direct API ingestion
remains authoritative for input data; MCP results are supplementary evidence for
the AI investigator.

Environment additions:

```env
RAZORPAY_KEY_ID=
RAZORPAY_KEY_SECRET=
RAZORPAY_MODE=test
RAZORPAY_API_BASE_URL=https://api.razorpay.com/v1
```

Do not expose these through `NEXT_PUBLIC_*` variables. Webhooks are P2, and n8n
is out of scope without a concrete implementation blocker.
