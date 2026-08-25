# sl3dge — Tech Stack & Engineering Handoff for Codex

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

One frontend + one backend + one Postgres instance is enough.

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
PostgreSQL 16+

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

Use exactly one provider abstraction.

Possible providers:
- OpenAI
- Gemini

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

# 7. Database Decision

Use PostgreSQL.

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
    "rate": "0.0155"
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

# 14. Example docker-compose.yml Shape

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
POSTGRES_DB=sl3dge
POSTGRES_USER=sl3dge
POSTGRES_PASSWORD=sl3dge

DATABASE_URL=postgresql+psycopg://sl3dge:sl3dge@localhost:5432/sl3dge

NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api/v1

LLM_PROVIDER=openai
LLM_API_KEY=
LLM_MODEL=

DEMO_SEED=20260825
CORS_ORIGINS=http://localhost:3000
```

No secrets committed.

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
```

AI provider SDK:
only the selected provider SDK.

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

Check demo fixture metadata into the repo if useful.

Suggested:

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

`manifest.json`:

```json
{
  "seed": 20260825,
  "payment_count": 500,
  "known_demo_ids": {
    "mdr_violation": "PAY_82HD9",
    "duplicate_refund": "REF_91",
    "sla_violation": "SET_1042",
    "root_cause": "RC_MDR_01",
    "unresolved": "UNR_003"
  }
}
```

This makes the recorded demo reproducible.

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

Frontend:
- Vercel

Backend:
- Railway / Render / Fly.io / similar

Database:
- managed Postgres

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

# 29. Build Order

## Phase 1 — Deterministic Core

Backend:
- schema
- synthetic data
- controls
- event graph
- run summary

Frontend:
- run screen
- result screen
- transaction inspector

Goal:
Demonstrate hidden overcharge with no AI.

---

## Phase 2 — Visual Proof

Backend:
- transaction graph endpoint
- evidence endpoint
- root-cause clustering

Frontend:
- React Flow graph
- root-cause screen
- exception inbox

Goal:
Make the core moat visually obvious.

---

## Phase 3 — AI Verification Loop

Backend:
- agreement extraction
- hypothesis generation
- hypothesis verification

Frontend:
- agreement side-by-side extraction
- hypothesis card
- verification result

Goal:
Demonstrate AI discovery + deterministic verification.

---

## Phase 4 — Reliability

- ground-truth metrics
- seeded regression tests
- demo IDs fixed
- error states
- Docker
- e2e demo flow

---

## Phase 5 — Optional Differentiators

Only after core demo is stable:
- schema drift
- evidence pack export
- natural-language query layer

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
1,200+ events
1,000+ control evaluations
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

# 32. Core Product Acceptance Test

The implementation is not done until this test passes:

1. Load seeded NovaCart agreement.
2. Extract/approve 1.55% domestic MDR control.
3. Load seeded 500-payment dataset.
4. Execute control run.
5. Gateway net and bank credit for `PAY_82HD9` are equal.
6. sl3dge still flags `PAY_82HD9`.
7. Expected MDR = ₹155.
8. Actual MDR = ₹175.
9. Expected GST = ₹27.90.
10. Actual GST = ₹31.50.
11. Verified leakage = ₹23.60.
12. Financial event graph shows full lifecycle.
13. Root-cause cluster groups similar MDR violations.
14. AI proposes policy-change hypothesis.
15. Verifier checks approved agreement/amendments.
16. Hypothesis is rejected.
17. Duplicate refund control works.
18. SLA control works.
19. At least one ambiguous case remains unresolved.
20. Evaluation reports precision and recall.

If this works end-to-end, the project has a strong demo even without P2 features.

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

## Updated Build Phases

```text
Phase 1 — Deterministic Core
Phase 2 — Mutation Testing + Blind Spots
Phase 3 — Visual Proof: Event Graph, Counterfactuals, Lineage
Phase 4 — AI Verification Loop
Phase 5 — Candidate-Control Backtesting + Coverage + Versioning
Phase 6 — Reliability / Seeded E2E Demo
Phase 7 — Optional Temporal Replay / Schema Drift / Evidence Export
```

## Updated Differentiated Acceptance Test

The project is not done until:

1. agreement produces approved MDR control
2. 500-payment demo loads
3. hidden overcharge is caught despite gateway-bank match
4. correct counterfactual settlement is reconstructed
5. event graph renders
6. violation lineage identifies primary/downstream failures
7. AI hypothesis is generated
8. verifier rejects unsupported policy change
9. at least 8 mutation types can be injected
10. Mutation Detection Rate is calculated
11. at least one deliberate blind spot is visible
12. candidate control can be proposed for that blind spot
13. candidate control is backtested
14. detection coverage improves
15. false-positive delta is shown
16. control remains inactive until explicit approval
17. control coverage identifies governed/ungoverned edges
18. time-versioned control selection works at a boundary
19. unresolved case stays unresolved
20. precision/recall against hidden ground truth still work

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
```
