# sl3dge — Backend Handoff for Codex

## Specification Authority

Authority order:

1. `features.md` defines product scope and priority.
2. `backend.md` defines backend behavior, API, and domain contracts.
3. `frontend.md` defines UI behavior and the recorded demo flow.
4. `techstack.md` defines engineering implementation choices.

If two sections conflict, the later section explicitly marked **authoritative**
wins. This document contains one authoritative backend build order and one
authoritative differentiated acceptance test.

## Current implementation note

`POST /api/v1/sources/uploads` accepts a bounded multi-file CSV batch, validates Decimal money fields, deterministically classifies orders/payments/refunds/settlements/chargebacks/bank reconciliation from content, and returns per-file evidence. `POST /api/v1/agreements/{agreement_id}/clauses` adds an idempotent, audited manual clause to a durable tenant agreement. The schema authority is Alembic revision `0010_manual_agreement_clauses`. Upload-to-run execution remains a P0 item in `PENDING_TASKS.md`.

## 0. Mission

Build the backend for **sl3dge**, an AI Finance Controller for the Razorpay Buildathon.

Core product distinction:

> Reconciliation asks whether records match. sl3dge asks whether they should.

The backend must convert approved financial controls into deterministic checks over a transaction lifecycle graph, detect provable violations, calculate verified monetary impact, cluster related failures, and use AI only for bounded tasks such as contract-control extraction, root-cause hypotheses, and schema-mapping suggestions.

The system must be able to process at least **50 records**. The authoritative
NovaCart seed contains exactly **500 payments and 1,179 financial events**; all
seeded counts come from `data/demo/manifest.json`.

The backend must never require an LLM to produce the core reconciliation/control result.

---

# 1. Backend Priority Rule

The only backend implementation sequence is the **Authoritative Backend Build
Order** near the end of this document. Do not infer a competing order from the
domain-model or API section numbering. Mutation testing and independent control
verification precede generalized agent features.

---

# 2. Core Architecture

```text
Next.js
   │ HTTPS + tenant identity
   ▼
FastAPI API ───────────────► durable background_jobs ───► worker
   │                                                        │
   │                                                        ▼
   │                                           read-only Razorpay APIs
   │                                                        │
   ├────────────────────────────────────────────────────────┘
   ▼
Supabase Postgres
   ├── immutable source_snapshots + provenance
   ├── events + deterministic/scored event_edges
   ├── typed controls + control_evaluations + violations
   ├── root causes + cases + audit log
   └── durable LangGraph checkpoints + execution traces

Supabase private Storage
   └── agreements, uploaded sources, optional evidence artifacts

Deterministic finance pipeline
   Source snapshot → normalize → event graph → controls → expected vs actual
                                                     ├── PASS
                                                     ├── VIOLATION
                                                     └── UNRESOLVED

Three bounded LangGraph workflows
   ├── root-cause investigation → deterministic verifier → case
   ├── blind-spot remediation → deterministic backtests → human approval
   └── agreement compilation → schema/conflict checks → human approval
```

LangGraph orchestrates bounded investigation and control-governance work. It
does not own matching, arithmetic, control execution, financial verdicts, or
money movement.

---

# 3. Hard Architectural Rule

The backend must separate:

## Deterministic logic
Used for:
- identifier matching
- arithmetic
- fee calculations
- tax calculations
- date/SLA calculations
- lifecycle validation
- monetary impact
- control execution
- precision/recall metrics
- backtesting
- ground-truth evaluation

## AI logic
Used only for:
- extracting candidate controls from agreement text
- summarizing evidence
- generating root-cause hypotheses
- suggesting schema mappings
- explaining already-computed results

AI output must never silently become financial truth.

Every AI-generated control or mapping is a proposal until approved or backtested.

---

# 4. Backend Framework

Use:

- Python 3.12+
- FastAPI
- Pydantic v2
- SQLAlchemy 2.x
- Alembic
- Supabase Postgres for deployed environments; ordinary PostgreSQL remains the
  local fallback through the same SQLAlchemy `DATABASE_URL`
- LangGraph for the three explicitly defined agent workflows only
- LangChain Pydantic structured output with the provider-abstracted LLM client
- Polars preferred for batch processing
- pytest
- httpx for API tests

Keep business logic in service modules, not route handlers.

---

# 5. Domain Model

## 5.1 Control

Represents an approved expected financial rule.

Fields:

```text
id: UUID
name: string
control_type: enum
description: string
conditions: JSON
expected_formula: JSON
effective_from: datetime | null
effective_to: datetime | null
source_document_id: UUID | null
source_page: int | null
source_clause: string | null
status: enum[DRAFT, APPROVED, REJECTED, RETIRED]
confidence: float | null
created_at
updated_at
```

Suggested `control_type` values:

```text
MDR_RATE
GST_ON_FEE
SETTLEMENT_SLA
REFUND_INTEGRITY
SETTLEMENT_ARITHMETIC
LIFECYCLE_VALIDITY
CUSTOM
```

---

## 5.2 FinancialEvent

Canonical representation of source records.

Fields:

```text
id: UUID
run_id: UUID
source: enum[ORDER, PAYMENT, SETTLEMENT, BANK, REFUND, CHARGEBACK]
external_id: string
event_type: string
amount: Decimal
currency: string
timestamp: datetime
status: string | null
raw_payload: JSON
normalized_payload: JSON
created_at
```

---

## 5.3 EventEdge

Links lifecycle events.

Fields:

```text
id: UUID
run_id: UUID
from_event_id: UUID
to_event_id: UUID
relationship: enum
confidence: float
method: enum[EXACT, RULE, FUZZY, HUMAN]
evidence: JSON
```

`FUZZY` is deterministic and scored; it is never an LLM-created edge. A fuzzy
matcher may combine normalized string similarity, Decimal amount
equality/tolerance, timestamp proximity, and reference-token overlap. It must
return an explicit confidence score plus component evidence in `evidence`.
Scores below the typed deterministic threshold produce `UNRESOLVED`; they do
not produce an `EventEdge`. LLMs may explain an existing match but may not
create an edge or force an ambiguous match.

Suggested relationships:

```text
PAID_BY
INCLUDED_IN
CREDITED_AS
REFUNDED_BY
CHARGEDBACK_BY
CHARGED_FEE
RELATED_TO
```

---

## 5.4 ControlEvaluation

One evaluation of a control against one event or event group.

Fields:

```text
id: UUID
run_id: UUID
control_id: UUID
subject_event_id: UUID | null
subject_group_key: string | null
expected_value: JSON
actual_value: JSON
difference: Decimal | null
status: enum[PASS, VIOLATION, WARNING, UNRESOLVED]
confidence: float
calculation: JSON
evidence: JSON
created_at
```

---

## 5.5 Violation

Fields:

```text
id: UUID
evaluation_id: UUID
run_id: UUID
category: string
financial_impact: Decimal
confidence: float
root_cause_id: UUID | null
review_status: enum[OPEN, CONFIRMED, REJECTED, RESOLVED]
human_note: string | null
```

Only put money into `financial_impact` when the amount is provable.

Ambiguous exposure must not be added to verified leakage totals.

---

## 5.6 RootCause

Fields:

```text
id: UUID
run_id: UUID
title: string
description: string
signature: JSON
affected_violation_ids: list[UUID]
affected_count: int
verified_impact: Decimal
hypothesis: string | null
verification_status: enum[NOT_TESTED, PROVEN, REJECTED, UNRESOLVED]
verification_evidence: JSON | null
```

---

## 5.7 ControlRun

Fields:

```text
id: UUID
name: string
status: enum[PENDING, RUNNING, COMPLETE, FAILED]
started_at
completed_at
transaction_count
event_count
control_evaluation_count
pass_count
violation_count
warning_count
unresolved_count
verified_leakage
cash_delayed
precision
recall
false_positive_rate
processing_ms
metadata
```

---

## 5.8 GroundTruthRecord

Only for synthetic/evaluation runs.

Fields:

```text
event_external_id
expected_status
expected_violation_type
expected_loss
expected_related_ids
```

Do not feed ground truth into the inference pipeline.

---

# 6. Synthetic Dataset Generator

This is P0.

Create deterministic seeded generation.

Example:

```bash
python -m app.synthetic.generate --seed 42 --payments 500 --output ./data/demo
```

Generate:

```text
orders.csv
payments.csv
settlements.csv
bank.csv
refunds.csv
chargebacks.csv
agreement.pdf or agreement.txt
ground_truth.json
```

The generator and `data/demo/manifest.json` are jointly authoritative for the
seeded run. With `DEMO_SEED=20260825`, generate exactly:

```text
orders                         500
payments                       500
settlements                     84
bank entries                    84
refunds                          5
chargebacks                      6
financial events             1,179
event edges                  1,495
control evaluations          2,018

PASS                            439
MDR rate deviations              25
incorrect GST                     8
duplicate refunds                 5
settlement SLA violations         10
unsupported fees                   8
UNRESOLVED                         5
```

The payment-level ground truth is 439 `PASS`, 56 labeled violations, and 5
unresolved records. The authoritative control-evaluation summary is 1,655
`PASS`, 358 `VIOLATION`, 0 `WARNING`, and 5 `UNRESOLVED` (2,018 total); the
unresolved relationship count is tracked separately. These are exact demo
expectations, not illustrative targets.

Ensure the generator can also produce a 50-record lightweight test set.

---

# 7. Canonical Input Schemas

## payments.csv

```text
payment_id
order_id
amount
currency
payment_method
card_network
card_scope
captured_at
fee
tax
status
```

## settlements.csv

```text
settlement_id
payment_id
gross_amount
fee
tax
refund_adjustment
other_adjustment
net_amount
settled_at
```

Many payments may share a settlement ID.

## bank.csv

```text
bank_txn_id
posted_at
description
credit
debit
currency
reference
```

## refunds.csv

```text
refund_id
payment_id
amount
created_at
status
```

## chargebacks.csv

```text
chargeback_id
payment_id
amount
fee
created_at
status
```

---

# 8. Ingestion and Normalization

Build adapters per source.

Required behavior:

- normalize timestamps to UTC internally
- preserve source timezone metadata if provided
- use Decimal for money
- normalize currency
- preserve raw source row
- normalize IDs
- flag malformed rows
- reject impossible values where appropriate
- return ingestion summary

An ingestion API response should include fields like the following. These
values are **illustrative for a non-seeded upload** and are not NovaCart demo
counts:

```json
{
  "accepted": 1215,
  "rejected": 3,
  "warnings": 8
}
```

---

# 9. Financial Event Graph Builder

Build event relations in descending confidence order.

## Exact relationships

Examples:

```text
payment.order_id == order.order_id
settlement.payment_id == payment.payment_id
refund.payment_id == payment.payment_id
```

## Settlement-to-bank

Use:

1. exact settlement reference in bank narration
2. deterministic score over normalized narration/reference tokens, Decimal net
   amount equality or typed tolerance, and timestamp proximity
3. grouped deterministic evidence
4. otherwise unresolved

Persist the score and feature-level matching evidence. The configured threshold
is deterministic and typed. If the best candidate is below it, or multiple
candidates remain tied within the ambiguity margin, return `UNRESOLVED`. Do not
force ambiguous matches, and do not ask an LLM to choose an `EventEdge`.

Persist confidence and matching method.

---

# 10. Control Representation

Avoid arbitrary Python execution from AI-generated text.

Represent controls as structured JSON/DSL.

Example MDR control:

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

GST control:

```json
{
  "type": "GST_ON_FEE",
  "parameters": {
    "rate": "0.18",
    "tolerance": "0.01"
  }
}
```

SLA:

```json
{
  "type": "SETTLEMENT_SLA",
  "parameters": {
    "business_days": 2
  }
}
```

Keep the MVP control system explicit and type-safe.

All rates, monetary amounts, and monetary tolerances in JSON are decimal
strings. Pydantic validators parse them into Python `Decimal` before the
deterministic executor runs. Raw JSON floating-point values are invalid for MDR
rates, GST rates, fee rates, amounts, and currency tolerances. Integer counts
such as `business_days` remain integers.

---

# 11. Deterministic Control Engine

Implement a registry:

```python
CONTROL_EXECUTORS = {
    ControlType.MDR_RATE: evaluate_mdr,
    ControlType.GST_ON_FEE: evaluate_gst,
    ControlType.SETTLEMENT_SLA: evaluate_sla,
    ControlType.REFUND_INTEGRITY: evaluate_refund_integrity,
    ControlType.SETTLEMENT_ARITHMETIC: evaluate_settlement_arithmetic,
    ControlType.LIFECYCLE_VALIDITY: evaluate_lifecycle,
}
```

Each executor returns:

```python
EvaluationResult(
    status=...,
    expected=...,
    actual=...,
    difference=...,
    financial_impact=...,
    calculation=...,
    evidence=...,
    confidence=...
)
```

---

# 12. Required MVP Controls

## 12.1 Domestic card MDR

Expected:

```text
amount * configured_rate
```

Compare against actual gateway fee.

Require a typed `tolerance` parameter such as `"0.01"`. It is a currency
amount encoded as a decimal string and parsed into `Decimal`; it is not a rate
and never uses binary floating-point semantics.

---

## 12.2 GST on processing fee

Expected:

```text
valid_processing_fee * 18%
```

Do not calculate GST from an incorrect overcharged fee if the control is intended to compare expected contractual state.

Expose both:

```text
expected_fee
actual_fee
expected_gst
actual_gst
```

The GST control also carries a monetary tolerance as a decimal string, e.g.
`"tolerance": "0.01"`, parsed into `Decimal`.

---

## 12.3 Settlement SLA

Need business-day helper.

For MVP, define weekends as non-business days.
Optional holiday calendar later.

Output:

```text
expected_latest_date
actual_date
delay_days
delayed_amount
```

---

## 12.4 Refund integrity

Detect:
- refund amount > original payment
- duplicate principal deduction for one refund
- refund attached to uncaptured/nonexistent payment
- multiple deductions that exceed refund amount

---

## 12.5 Settlement arithmetic

Expected:

```text
gross
- valid fees
- valid taxes
- refunds
+/- legitimate adjustments
```

Compare to settlement net.

Settlement arithmetic uses a typed monetary tolerance such as
`"tolerance": "0.01"`, parsed into `Decimal`.

---

## 12.6 Lifecycle validity

Detect examples:
- failed payment included in settlement
- settlement references missing payment
- refund before payment capture where impossible
- duplicate chargeback fee
- chargeback exceeding valid constraints

---

# 13. Expected-vs-Actual Service

Expose a transaction inspection object suitable for direct rendering.

Example:

```json
{
  "payment_id": "PAY_82HD9",
  "rows": [
    {
      "label": "Gross",
      "expected": "10000.00",
      "actual": "10000.00",
      "status": "PASS"
    },
    {
      "label": "MDR",
      "expected": "155.00",
      "actual": "175.00",
      "status": "VIOLATION"
    },
    {
      "label": "GST",
      "expected": "27.90",
      "actual": "31.50",
      "status": "VIOLATION"
    },
    {
      "label": "Net",
      "expected": "9817.10",
      "actual": "9793.50",
      "status": "VIOLATION"
    }
  ],
  "verified_leakage": "23.60"
}
```

---

# 14. Metrics and Ground-Truth Evaluation

For synthetic runs, calculate:

- precision
- recall
- false positive rate
- unresolved count
- verified leakage
- control evaluations per second
- processing duration

Definitions:

```text
precision = true_positive_violations / all_predicted_violations

recall = true_positive_violations / all_ground_truth_violations

false_positive_rate = false_positive_violations / non_violation_ground_truth
```

The results API should explicitly expose confusion-matrix counts.

---

# 15. Root-Cause Clustering

Start deterministic.

Do not begin with embeddings.

Create signatures such as:

```text
control_type
payment_method
card_network
card_scope
observed_rate
expected_rate
time_bucket
```

Example cluster:

```text
MDR_RATE + card + Visa + domestic + expected 1.55% + actual 1.75%
```

Then optionally ask an LLM to explain the already-identified cluster.

Required API output:

```json
{
  "title": "Domestic Visa MDR deviation",
  "affected_count": 25,
  "expected_rate": "0.0155",
  "observed_rate": "0.0175",
  "first_seen": "...",
  "last_seen": "...",
  "verified_impact": "2042.82"
}
```

---

# 16. Agreement Control Compilation — LangGraph

Input:
- agreement text or parsed PDF text

Run one bounded, checkpointed graph:

```text
extract_clauses
→ classify_financial_terms
→ generate_typed_controls
→ validate_schemas
→ detect_conflicts
→ human_approval
```

Output candidate structured controls. LangChain must request strict Pydantic
structured output from the configured provider. Every rate, fee, tolerance, and
amount inside candidate parameters remains a decimal string and passes the same
no-binary-float validation as manually authored controls.

The model output must conform to a Pydantic schema.

Each proposal must include:

```text
control_type
conditions
parameters
source_quote_or_clause_reference
source_page
confidence
```

Store as `DRAFT`.

Schema validation must reject malformed or binary-float financial parameters.
Conflict detection must reject overlapping effective periods or incompatible
versions. A successful graph ends at `AWAITING_HUMAN_APPROVAL`; only a separate,
authorized human action can move a proposal to `APPROVED`.

Do not execute unapproved controls.

For the demo, support a synthetic merchant agreement with:
- domestic MDR
- international MDR
- GST
- T+2 settlement
- refund fee = ₹0

---

# 17. Root-Cause Investigation — LangGraph + Deterministic Verifier

Run one bounded, checkpointed graph with explicit state, nodes, conditional
edges, and an attempt limit:

```text
collect_evidence
→ load_source_context
→ load_contract_context
→ generate_hypothesis
→ verify_hypothesis
    ├── PROVEN     → create_case
    ├── REJECTED   → generate_alternative_hypothesis → verify_hypothesis
    └── UNRESOLVED / attempts exhausted → escalate_unresolved
```

Each node appends a sanitized trace event containing sequence, node, status,
message, and timestamp. The execution ID is also the LangGraph thread/checkpoint
key so retries and resumptions are auditable. Production uses a Postgres-backed
checkpointer; an in-memory saver is development-only.

AI may generate a hypothesis, e.g.:

```text
"Domestic Visa MDR changed to 1.75% starting Aug 18."
```

Represent hypothesis structurally:

```json
{
  "kind": "POLICY_CHANGE",
  "field": "mdr_rate",
  "segment": {
    "card_network": "visa",
    "card_scope": "domestic"
  },
  "proposed_value": "0.0175",
  "effective_from": "2026-08-18"
}
```

Verifier must check:

1. current approved control
2. amendments/effective dates
3. historical transactions
4. affected transactions
5. unaffected segments

Return:

```text
PROVEN
REJECTED
UNRESOLVED
```

Critical demo case:
- observed rate changes
- no approved contract amendment exists
- the first policy-change hypothesis is deterministically `REJECTED`
- the graph generates an alternate gateway-deviation hypothesis
- the alternate is deterministically `PROVEN` from the approved `"0.0155"`
  rate, observed `"0.0175"` rate, and `"0.01"` currency tolerance
- create or attach the evidence-backed case and classify it as a potential
  systemic overcharge

The model cannot create `EventEdge` rows, alter controls, approve proposals,
write a financial verdict, or call money-moving tools. Missing or unverified
evidence must produce `UNRESOLVED`, never a forced conclusion. If the configured
LLM is unavailable, the workflow reports degraded AI capability while the
deterministic verifier and the entire core pipeline remain available.

---

# 18. Schema Drift Detection

P1/P2.

Detect when columns change between a known schema and a new file.

Suggested method:
- lexical similarity
- data type
- uniqueness profile
- value overlap
- sampled relationship retention

AI may suggest mapping.

Then deterministic backtest verifies it.

Example:

```text
payment_id -> txn_reference
fee -> processing_charge
tax -> gst
```

Backtest metrics:
- identifier collisions
- broken graph relations
- previously valid control outcomes retained
- amount inconsistencies

---

# 19. API Surface

Use `/api/v1`.

## Health

```http
GET /api/v1/health
```

---

## Runs

```http
POST /api/v1/runs
GET /api/v1/runs
GET /api/v1/runs/{run_id}
POST /api/v1/runs/{run_id}/execute
GET /api/v1/runs/{run_id}/summary
```

---

## Upload / ingestion

```http
POST /api/v1/runs/{run_id}/sources/orders
POST /api/v1/runs/{run_id}/sources/payments
POST /api/v1/runs/{run_id}/sources/settlements
POST /api/v1/runs/{run_id}/sources/bank
POST /api/v1/runs/{run_id}/sources/refunds
POST /api/v1/runs/{run_id}/sources/chargebacks
```

For demo speed, also support:

```http
POST /api/v1/demo/load
```

which loads a seeded synthetic dataset.

---

## Controls

```http
GET /api/v1/controls
POST /api/v1/controls
GET /api/v1/controls/{control_id}
PATCH /api/v1/controls/{control_id}
POST /api/v1/controls/{control_id}/approve
POST /api/v1/controls/{control_id}/reject
```

---

## Agreement import

```http
POST /api/v1/agreements
POST /api/v1/agreements/{agreement_id}/extract-controls
POST /api/v1/agreements/{agreement_id}/compile-controls
GET /api/v1/agreements/{agreement_id}/control-proposals
```

`compile-controls` returns the bounded LangGraph execution trace and stops at
`AWAITING_HUMAN_APPROVAL`; approval remains a separate role-gated endpoint.

---

## Violations

```http
GET /api/v1/runs/{run_id}/violations
GET /api/v1/violations/{violation_id}
PATCH /api/v1/violations/{violation_id}/review
```

Support filters:

```text
category
min_impact
status
control_type
confidence
```

---

## Transaction inspection

```http
GET /api/v1/runs/{run_id}/payments/{payment_id}
GET /api/v1/runs/{run_id}/payments/{payment_id}/expected-vs-actual
GET /api/v1/runs/{run_id}/payments/{payment_id}/graph
```

---

## Root causes

```http
GET /api/v1/runs/{run_id}/root-causes
GET /api/v1/root-causes/{root_cause_id}
POST /api/v1/root-causes/{root_cause_id}/investigate
GET /api/v1/agent/investigations/{execution_id}
```

The investigation response exposes the explicit node trace, hypothesis
attempts, verifier evidence, final `PROVEN | REJECTED | UNRESOLVED` status, and
case ID when one is created. The older single-step generate/verify routes, if
retained during migration, are compatibility endpoints rather than the
authoritative investigation contract.

---

## Blind-spot remediation

```http
POST /api/v1/runs/{run_id}/blind-spots/remediate
```

The response includes the candidate, schema verdict, historical and mutation
backtest results, metric comparison, graph trace, and human-approval state.

---

## Durable Razorpay jobs

```http
POST /api/v1/integrations/razorpay/sync-jobs
Idempotency-Key: <stable caller-generated key>

GET /api/v1/jobs/{job_id}
```

Production synchronization is queued and returns `202`. The worker claims jobs
with a tenant-scoped lease, bounded attempts, and retry classification. Reusing
the same tenant, job type, and idempotency key returns the original job rather
than importing duplicate source data. Foreground synchronization is local
development-only.

---

## Evaluation

```http
GET /api/v1/runs/{run_id}/evaluation
```

---

## Schema drift

```http
POST /api/v1/schema-drift/analyze
POST /api/v1/schema-drift/backtest
```

---

# 20. API Error Format

Use consistent errors.

```json
{
  "error": {
    "code": "INVALID_SOURCE_SCHEMA",
    "message": "payments.csv is missing payment_id",
    "details": {}
  }
}
```

---

# 21. Authoritative Seeded Demo Manifest

Support a known deterministic demo seed.

Example:

```text
DEMO_SEED=20260825
```

`data/demo/manifest.json` is the single machine-readable authority. The exact
record, event, edge, evaluation, ground-truth, outcome, mutation, and coverage
counts are the counts listed in Section 6. Do not substitute rounded UI examples.

Stable featured IDs are:

```text
PAY_82HD9   hidden MDR violation
REF_91      duplicate refund case
SET_1042    settlement SLA violation
RC_MDR_01   systemic MDR root cause
UNR_003     unresolved case
```

The seed contains five unresolved records, with `UNR_003` as the featured case.

---

# 22. Persistence Strategy — Supabase Infrastructure

The deployed primary database is **Supabase Postgres**. FastAPI continues to use
SQLAlchemy 2.x and Alembic through standard PostgreSQL connection strings; do
not rewrite repositories around direct Supabase client calls.

Use Postgres for:
- controls
- runs
- immutable, content-addressed source snapshots and ingestion provenance
- events
- edges with matching evidence and deterministic confidence
- append-only control evaluations
- violations
- root causes
- human review states
- mutation tests, results, backtests, and control coverage
- idempotent background jobs, leases, attempts, and bounded failure details
- LangGraph checkpoints, execution metadata, and sanitized node traces
- integration status and last successful sync metadata
- tenant-scoped audit records
- file metadata and immutable Supabase Storage object paths

Use Supabase Storage for merchant agreement PDFs, uploaded source files, and
optional evidence artifacts. Store only object metadata, checksum, bucket, path,
content type, size, and provenance in Postgres rather than duplicating file
contents in relational rows.

```text
sl3dge-private/
  agreements/novacart-v1.pdf
  runs/RUN_001/payments.csv
  runs/RUN_001/settlements.csv
  runs/RUN_001/bank.csv
  evidence/CASE_1042/evidence.json
```

Runtime FastAPI deployments should use the Supabase transaction pooler through
`DATABASE_URL`, with bounded SQLAlchemy pools and `pool_pre_ping`. Alembic uses
`MIGRATION_DATABASE_URL` with a direct or session-mode connection because
transaction pooling must not be assumed to preserve session state or named
prepared statements. Use a least-privilege application database role, not a
superuser or service role, for normal queries.

Local development remains swappable by pointing the same variables at a normal
local PostgreSQL instance. No business-logic branch may depend on whether the
database host is local PostgreSQL or Supabase Postgres.

Every tenant-owned table carries `tenant_id`; repository reads and writes are
tenant-scoped and production Postgres enables row-level security as defense in
depth. Migrations are immutable Alembic operations and never call live ORM
`metadata.create_all()` or `drop_all()`. Raw Razorpay responses are sanitized
and content-addressed before persistence; duplicate content maps to the same
source snapshot instead of silently producing duplicate evidence.

For the event graph MVP, do **not** add Neo4j.
Relational tables are enough.

---

# 23. Testing

Required tests:

## Unit
- MDR expected calculation
- GST expected calculation
- T+2 business-day calculation
- duplicate refund detection
- settlement arithmetic
- lifecycle invalid cases
- leakage aggregation
- root-cause signature generation
- no binary float accepted in typed AI control output
- deterministic hypothesis verification cannot be overridden by model text
- sub-threshold or ambiguous FUZZY evidence remains unresolved
- job idempotency, lease ownership, retry bounds, and terminal failure behavior

## Integration
- ingest demo files
- build graph
- execute controls
- compare against ground truth
- retrieve run summary
- resume all three LangGraph workflows from Postgres checkpoints
- persist source snapshots, evaluations, violations, and audit events
- prove tenant isolation and Postgres row-level security with two tenants
- replay an idempotent Razorpay sync submission without duplicate ingestion

## Regression
Create one fixed seeded dataset and assert minimum metrics.

Example:

```text
precision >= 0.98
recall >= 0.95
unresolved == expected_unresolved_count
```

Do not assert exact runtime in CI.

---

# 24. Observability

Log:
- run ID
- stage
- record counts
- control execution counts
- duration
- AI call identifiers
- agent execution/thread ID, node, branch, attempt, and verifier result
- job ID, idempotency replay, lease owner, attempt, and terminal outcome
- source snapshot checksum and mapping version
- failures

Never log full sensitive raw payloads in normal logs.

---

# 25. Security / Safety

For production and the recorded demo:
- seeded synthetic data remains the primary scored evaluation path
- Razorpay ingestion is read-only
- file size limits
- MIME validation
- sanitize filenames
- do not execute uploaded content
- contract extraction treats document text as untrusted input
- structured AI outputs only
- secrets via environment variables
- Supabase service credentials, Groq keys, and Razorpay credentials are
  backend-only and never serialized by an API

The browser calls FastAPI only. It does not query finance tables or Storage with
a privileged Supabase key. Supabase Auth, Realtime, and Edge Functions are not
required for the MVP; Realtime is P2 run-progress polish only.

Production API access requires validated OIDC bearer tokens, role checks, and a
tenant claim. Background workers and graph checkpoints use backend-only
credentials. Razorpay access is restricted to an explicit HTTPS GET allowlist,
bounded pagination/response sizes, timeouts, retries, and no redirects. AI
prompts treat source and agreement text as untrusted data and expose no write or
money-moving tool.

---

# 26. Environment Variables

Example:

```env
DATABASE_URL=postgresql+psycopg://app_role:...@...pooler.supabase.com:6543/postgres
MIGRATION_DATABASE_URL=postgresql+psycopg://migration_role:...@db....supabase.co:5432/postgres
AGENT_CHECKPOINT_DATABASE_URL=postgresql+psycopg://checkpoint_role:...@db....supabase.co:5432/postgres?sslmode=require
SUPABASE_URL=https://PROJECT_REF.supabase.co
SUPABASE_SERVICE_ROLE_KEY=
SUPABASE_STORAGE_BUCKET=sl3dge-private
AUTH_MODE=oidc
OIDC_ISSUER=https://identity.example.com/
OIDC_AUDIENCE=sl3dge-api
OIDC_JWKS_URL=https://identity.example.com/.well-known/jwks.json
OIDC_TENANT_CLAIM=merchant_id
OIDC_ROLES_CLAIM=roles
LLM_PROVIDER=groq
LLM_MODEL=openai/gpt-oss-120b
GROQ_API_KEY=
LLM_TIMEOUT_SECONDS=30
LLM_MAX_OUTPUT_TOKENS=1200
LLM_MAX_INPUT_CHARS=24000
AGENT_MAX_ATTEMPTS=2
RAZORPAY_KEY_ID=
RAZORPAY_KEY_SECRET=
RAZORPAY_MODE=test
RAZORPAY_API_BASE_URL=https://api.razorpay.com/v1
RAZORPAY_TIMEOUT_SECONDS=20
RAZORPAY_MAX_RETRIES=3
RAZORPAY_MAX_PAGES=100
RAZORPAY_MAX_RECORDS=100000
WORKER_TENANT_IDS=novacart_demo
WORKER_LEASE_SECONDS=900
WORKER_POLL_SECONDS=2
DEMO_SEED=20260825
CORS_ORIGINS=http://localhost:3000
```

`LLM_PROVIDER=groq` and `LLM_MODEL=openai/gpt-oss-120b` are the reproducible
development/demo defaults. Provider-specific calls live behind the `LLMClient`
abstraction, never in control or finance business logic. If the provider, model,
or key is absent, the deterministic pipeline still works fully and AI-only
actions return an explicit unavailable/degraded state.

---

# 27. Recommended Backend Structure

```text
backend/
├── app/
│   ├── main.py
│   ├── api/
│   │   ├── runs.py
│   │   ├── controls.py
│   │   ├── agreements.py
│   │   ├── violations.py
│   │   ├── root_causes.py
│   │   └── drift.py
│   ├── core/
│   │   ├── config.py
│   │   └── money.py
│   ├── db/
│   │   ├── models.py
│   │   ├── session.py
│   │   └── migrations/
│   ├── persistence/
│   │   ├── orm.py
│   │   └── repository.py
│   ├── schemas/
│   ├── ingestion/
│   ├── normalization/
│   ├── graph/
│   ├── controls/
│   │   ├── registry.py
│   │   ├── mdr.py
│   │   ├── gst.py
│   │   ├── sla.py
│   │   ├── refund.py
│   │   ├── settlement.py
│   │   └── lifecycle.py
│   ├── evaluation/
│   ├── root_cause/
│   ├── agents/
│   │   ├── investigation.py
│   │   ├── control_workflows.py
│   │   ├── checkpoint.py
│   │   └── models.py
│   ├── ai/
│   │   ├── contract_extractor.py
│   │   ├── hypothesis.py
│   │   ├── explanation.py
│   │   └── provider.py
│   ├── integrations/
│   │   └── razorpay/
│   ├── workers/
│   │   └── runner.py
│   ├── drift/
│   └── synthetic/
├── tests/
├── alembic/
├── pyproject.toml
└── Dockerfile
```

---

# 28. Backend Completion Gate

Backend completion is defined only by the **Authoritative Differentiated
Acceptance Test** below. This section intentionally contains no competing MVP
checklist.

---

# 29. Explicit Non-Goals

Do not implement:
- blockchain
- wallets
- Razorpay money-moving operations
- accounting ERP integrations
- generic chat
- forecasting
- tax filing
- payment initiation
- arbitrary user-written code execution
- autonomous contract-rule activation
- graph database unless the relational model becomes demonstrably insufficient

Focus on the verification loop.


---

# Novelty Extension — Control Quality & Verification

These requirements are first-class product architecture. See `features.md` for product rationale and demo priority.

## Financial Mutation Testing — P0

sl3dge must verify not only transactions but whether approved controls can actually detect realistic failures.

Mutation testing operates on a derived copy of a known-good dataset and must never mutate canonical run data.

Required mutation types for the demo:

```text
MDR_RATE_INCREASE
GST_BASE_CORRUPTION
DUPLICATE_REFUND_DEDUCTION
SETTLEMENT_DELAY
UNSUPPORTED_FEE
FAILED_PAYMENT_SETTLED
REFUND_EXCEEDS_PAYMENT
DUPLICATE_CHARGEBACK_FEE
PAYMENT_METHOD_RECLASSIFICATION
```

Suggested models:

```text
MutationTest
id
source_run_id
status
mutation_count
detected_count
missed_count
mutation_detection_rate
false_positive_count
created_at
```

```text
Mutation
id
mutation_test_id
mutation_type
target_event_id
target_edge_id
parameters
expected_control_type
```

```text
MutationResult
id
mutation_id
detected
detected_by_control_ids
blind_spot_reason
false_positive_side_effects
```

Endpoints:

```http
POST /api/v1/runs/{run_id}/mutation-tests
POST /api/v1/mutation-tests/{test_id}/execute
GET  /api/v1/mutation-tests/{test_id}
GET  /api/v1/mutation-tests/{test_id}/coverage
```

Required metrics:

```text
mutation_count
detected_count
missed_count
mutation_detection_rate
false_positive_count
coverage_by_control_type
blind_spot_count
```

## Control Blind-Spot Detection — P0

When a mutation is missed, classify why:

```text
NO_APPLICABLE_CONTROL
CONTROL_LOGIC_FAILED
UNGOVERNED_LIFECYCLE_EDGE
INSUFFICIENT_EVIDENCE
```

Return a structured blind-spot object with the affected event/edge and relevant agreement context when available.

Remediation runs as the second bounded LangGraph workflow:

```text
identify_gap
→ retrieve_contract_clause
→ propose_control
→ schema_validate
    ├── invalid → REJECTED
    └── valid   → historical_backtest
                → mutation_backtest
                → compare_metrics
                → human_approval
```

The graph may propose a typed control, but the deterministic backtest services
own every metric. The graph may stop at `AWAITING_HUMAN_APPROVAL`; it must never
activate the control itself.

## Candidate Control Backtesting — P1

AI-generated controls must be tested before approval.

Workflow:

```text
candidate control
→ historical backtest
→ mutation suite
→ precision/recall delta
→ false-positive delta
→ explicit authorized human approval/rejection
```

Endpoint:

```http
POST /api/v1/controls/{control_id}/backtest
```

Return before/after metrics. Backtesting is read-only. Approval remains a separate action.

## Control Coverage Graph — P1

Each material `EventEdge` must be mapped to applicable approved controls.

Suggested model:

```text
ControlCoverage
id
run_id
edge_id
control_id nullable
coverage_status: GOVERNED | PARTIALLY_GOVERNED | UNGOVERNED
```

Metrics:

```text
total_material_edges
governed_edges
ungoverned_edges
coverage_percentage
```

Endpoint:

```http
GET /api/v1/runs/{run_id}/control-coverage
```

Run operations are exposed separately and never substitute fabricated timing
values when a stage log is unavailable:

```http
GET /api/v1/runs/{run_id}/operational-metrics
```

The response contains completed/failed stage counts, persisted stage durations,
total processing time, and event/evaluation counters. The frontend renders this
at `/runs/{runId}/operations`.

## Time-Versioned Controls — P1

Approved controls are immutable once used by completed runs.

When a rule changes, create a new version rather than overwriting history.

Add/ensure fields:

```text
logical_control_key
version
effective_from
effective_to
supersedes_control_id
```

Control selection must use the financial event timestamp.

Boundary test example:

```text
30 Aug 2026 → MDR 1.55%
01 Sep 2026 → MDR 1.65%
```

## Temporal Replay — P1/P2

Allow historical events to be evaluated using an alternate control suite.

```http
POST /api/v1/runs/{run_id}/temporal-replay
```

Return:
- changed pass/fail counts
- expected-fee delta
- verified-exposure delta
- affected transactions

This is what-if control verification, not forecasting.

## Violation Lineage — P1

Avoid presenting downstream consequences as separate root problems.

Extend `Violation`:

```text
parent_violation_id
root_violation_id
lineage_type: PRIMARY | DOWNSTREAM
causal_evidence
```

Example:

```text
MDR violation
  ↓
GST downstream violation
  ↓
Expected settlement downstream violation
  ↓
Expected bank-credit downstream violation
```

Endpoint:

```http
GET /api/v1/violations/{violation_id}/lineage
```

Root-cause summaries must expose:

```text
primary_violation_count
downstream_effect_count
```

## Counterfactual Settlement Reconstruction — P1

Expose the actual cash flow and the verified correct cash flow.

```http
GET /api/v1/runs/{run_id}/payments/{payment_id}/counterfactual
```

Response shape:

```json
{
  "actual": {"gross":"10000.00","mdr":"175.00","gst":"31.50","refunds":"0.00","net":"9793.50"},
  "expected": {"gross":"10000.00","mdr":"155.00","gst":"27.90","refunds":"0.00","net":"9817.10"},
  "difference":"23.60",
  "drivers":[
    {"type":"EXCESS_MDR","amount":"20.00"},
    {"type":"EXCESS_GST","amount":"3.60"}
  ]
}
```

## Authoritative Backend Build Order

```text
1. Exact seeded manifest + hidden ground truth
2. Canonical domain contracts with tenant, audit, provenance, and Decimal invariants
3. Supabase/local Postgres repositories, immutable Alembic migrations, RLS, and private Storage metadata
4. Immutable source snapshots, ingestion, and normalization
5. Deterministic/scored Financial Event Graph matching
6. Approved, typed, time-versioned Decimal control registry
7. Deterministic control engine with persisted evaluations and violations
8. Expected-vs-Actual, batch metrics, and PAY_82HD9 acceptance slice
9. Financial Mutation Testing on derived data with canonical-data integrity checks
10. Mutation coverage and control blind-spot detection
11. LangGraph blind-spot remediation with deterministic historical/mutation backtests and a human gate
12. LangGraph agreement compilation with strict Pydantic output, schema/conflict checks, and a human gate
13. Violation Lineage and counterfactual settlement
14. Root-cause clustering
15. LangGraph root-cause investigation with bounded alternatives, deterministic verification, checkpoints, trace, and case creation
16. Control Coverage, exception case workflow, and time-versioned controls
17. Durable, idempotent read-only Razorpay sync jobs into canonical snapshots/events/evaluations
18. Optional read-only Razorpay MCP evidence tools
19. Frontend execution-trace, job-status, approval, and deterministic evidence UX
20. OIDC/RBAC, tenant isolation, secret boundaries, input limits, and production HTTP hardening
21. Regression/E2E tests, CI, structured observability, backup/recovery, and deployment verification
22. P2 only: temporal replay, schema drift, webhooks, Realtime progress, and evidence export
```

Mutation testing must be built before generalized agent features.

## Authoritative Differentiated Acceptance Test

This is the only backend acceptance test in this document. The differentiated
MVP is not backend-complete until all items are proven by automated tests or
seeded API evidence:

1. `data/demo/manifest.json` and generator output agree on every exact count and stable ID.
2. The seeded run produces 500 payments, 1,179 events, 1,495 edges, and 2,018 evaluations.
3. `PAY_82HD9` has the exact Decimal economics recorded in the manifest; all JSON financial rates, tolerances, fees, and amounts are decimal strings parsed to `Decimal`.
4. Gateway net equals bank credit at `9793.50`, while the approved control yields a violation.
5. Verified leakage for `PAY_82HD9` is exactly `23.60`.
6. `REF_91` proves duplicate refund deduction and `SET_1042` proves the SLA control.
7. The event graph shows the complete lifecycle without LLM-created edges.
8. Every FUZZY result exposes a deterministic score and matching evidence; sub-threshold or ambiguous candidates remain `UNRESOLVED`.
9. Counterfactual settlement reconstructs `9817.10` with `20.00` MDR and `3.60` GST drivers.
10. Violation lineage identifies one primary MDR failure and three downstream effects.
11. Similar MDR violations cluster under `RC_MDR_01`.
12. Root-cause investigation records `collect_evidence → load_source_context → load_contract_context → generate_hypothesis → verify_hypothesis` in its trace; source context is loaded only for the actual run source.
13. The verifier rejects the unsupported contract-change hypothesis, the bounded alternate is proven as a systemic gateway deviation, and the graph creates or attaches the evidence case.
14. Unverified evidence, verifier disagreement, or exhausted attempts end `UNRESOLVED`; model text cannot force a verdict.
15. At least eight deterministic mutation types execute against a derived copy.
16. The seeded mutation run reports 50 injected, 47 detected, 3 missed, 0 false positives, and `0.9400` mutation detection rate.
17. Mutation testing proves the canonical dataset is unchanged.
18. The blind-spot graph retrieves the agreement clause, schema-validates the proposal, and uses deterministic historical and mutation backtests.
19. The draft candidate backtests from 47/50 to 49/50 with false-positive delta 0.
20. The candidate remains inactive in `AWAITING_HUMAN_APPROVAL` until an authorized user explicitly approves it.
21. Agreement compilation produces strictly typed, versioned `DRAFT` controls, detects effective-date conflicts, and also stops at a human gate.
22. Control coverage reports 2,009 material edges, 2,000 governed, and 9 ungoverned before approval.
23. The correct immutable MDR version is selected on both sides of the 1 September boundary.
24. `UNR_003` and the other four ambiguous cases remain `UNRESOLVED` without forced matching.
25. The evidence-backed case enforces `OPEN → VERIFIED → ESCALATED/RESOLVED` and retains its tenant-scoped audit trail.
26. Precision, recall, false-positive rate, verified leakage, unresolved count, processing time, mutation rate, coverage, and lineage counts come from backend calculations.
27. Production Razorpay sync is GET-only, queued with a required idempotency key, leased to a worker, bounded by attempts/pages/records/bytes, and exposes no credential.
28. Replayed Razorpay jobs and identical source content do not duplicate jobs or evidence snapshots; normalized events retain source checksum, sync ID, and mapping version.
29. Optional Razorpay MCP output is non-authoritative evidence and still terminates in `PROVEN`, `REJECTED`, or `UNRESOLVED` after verification.
30. FastAPI repositories work unchanged with local PostgreSQL or Supabase Postgres through connection configuration.
31. Agreement/source/evidence objects use private Supabase Storage paths with metadata in Postgres.
32. OIDC roles, tenant filters, and Postgres RLS prevent one tenant from reading or mutating another tenant's records.
33. All three LangGraph workflows use durable production checkpoints, bounded retries, structured traces, and explicit human gates where required.
34. The browser receives no Supabase privileged credential, Groq key, or Razorpay secret.
35. The full deterministic run and all acceptance arithmetic work when no LLM configuration is present; AI-only actions degrade explicitly.

---

# Razorpay Read-Only Ingestion — Post-Core Integration

Do not build a parallel Razorpay domain model. All records must normalize into
the existing `FinancialEvent`, `EventEdge`, run and evaluation models.

## Direct API Plan

Primary bulk source:

```http
GET /v1/settlements/recon/combined?year=YYYY&month=MM&day=DD&count=1000&skip=0
```

Use this Settlement Reconciliation endpoint for payment, refund, transfer and
adjustment rows already associated with settlement IDs and UTRs.

Read-only enrichment sources:

```http
GET /v1/payments?from=...&to=...&count=100&skip=...
GET /v1/refunds?from=...&to=...&count=100&skip=...
GET /v1/settlements?from=...&to=...&count=100&skip=...
GET /v1/settlements/{settlement_id}
```

No create, capture, update, refund-initiation or instant-settlement endpoint is
allowed in the prototype.

## Domain Mapping

```text
Recon type=payment
  → FinancialEvent(source=PAYMENT)

Recon type=refund
  → FinancialEvent(source=REFUND)

Settlement record
  → FinancialEvent(source=SETTLEMENT)

settlement_utr
  → settlement normalized_payload and bank-link evidence

entity_id / payment_id / order_id / settlement_id
  → external IDs and exact EventEdges

fee / tax
  → FEE and TAX events or normalized monetary components

credit / debit / amount / currency
  → Decimal amounts after currency-subunit conversion

created_at / settled_at
  → UTC-aware event timestamps
```

Preserve the complete Razorpay response in `raw_payload`. Derived events must
retain source provenance, sync ID and mapping version.

Recommended connector layout:

```text
backend/app/integrations/razorpay/
├── client.py
├── recon.py
├── payments.py
├── refunds.py
├── settlements.py
├── schemas.py
└── mapper.py
```

Credentials are backend-only environment variables:

```env
RAZORPAY_KEY_ID=
RAZORPAY_KEY_SECRET=
RAZORPAY_MODE=test
```

They must never be returned by an API or embedded in frontend bundles.

## Optional MCP Evidence Layer

Only after direct ingestion is stable, use the official Razorpay MCP server in
read-only mode for bounded investigation with these tools:

```text
fetch_payment
fetch_all_payments
fetch_refund
fetch_all_refunds
fetch_multiple_refunds_for_payment
fetch_all_settlements
fetch_settlement_with_id
fetch_settlement_recon_details
```

MCP output is evidence, not truth. Any AI-derived conclusion still passes
through the deterministic verifier and ends in `PROVEN`, `REJECTED` or
`UNRESOLVED`.

Webhooks are P2. Do not add n8n without a concrete blocker.
