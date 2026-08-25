# sl3dge — Backend Handoff for Codex

## 0. Mission

Build the backend for **sl3dge**, an AI Finance Controller for the Razorpay Buildathon.

Core product distinction:

> Reconciliation asks whether records match. sl3dge asks whether they should.

The backend must convert approved financial controls into deterministic checks over a transaction lifecycle graph, detect provable violations, calculate verified monetary impact, cluster related failures, and use AI only for bounded tasks such as contract-control extraction, root-cause hypotheses, and schema-mapping suggestions.

The system must be able to process at least **50 records**. Target the demo around **500 payment transactions / 1,200+ financial events**.

The backend must never require an LLM to produce the core reconciliation/control result.

---

# 1. Backend Priorities

Implement in this order:

1. Synthetic dataset generator + hidden ground truth
2. Core domain models
3. Data ingestion and normalization
4. Financial event graph construction
5. Deterministic control engine
6. Expected-vs-actual evaluation
7. Batch run metrics
8. Exception/violation APIs
9. Root-cause clustering
10. Agreement-to-control extraction
11. Hypothesis verification
12. Schema drift detection
13. Optional evidence-pack export

Do not begin with chat or generalized agent infrastructure.

---

# 2. Core Architecture

```text
Source Files / Synthetic Data
            │
            ▼
     Ingestion Layer
            │
            ▼
     Normalization Layer
            │
            ▼
    Financial Event Graph
            │
            ├──────────────┐
            ▼              │
   Deterministic           │
   Control Engine          │
            │              │
            ▼              │
 Expected vs Actual        │
            │              │
      ┌─────┴─────┐        │
      ▼           ▼        │
    PASS      VIOLATION    │
                  │        │
                  ▼        │
          Root Cause Layer │
                  │        │
                  ▼        │
          AI Investigator  │
                  │        │
                  ▼        │
              Hypothesis   │
                  │        │
                  ▼        │
              Verifier ◄───┘
```

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
- PostgreSQL
- Polars preferred for batch processing
- pytest
- httpx for API tests
- Optional LangGraph only if orchestration genuinely needs it

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

Recommended planted abnormalities:

- ~25 MDR overcharges
- ~8 incorrect GST cases
- ~5 duplicate refund deductions
- ~10 settlement SLA violations
- ~8 unsupported fees
- ~5 missing bank settlements
- ~3-5 intentionally ambiguous cases
- second-day schema drift file

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

API response should include:

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
2. exact net amount + expected timing window
3. grouped evidence
4. otherwise unresolved

Do not force ambiguous matches.

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
    "rate": 0.0155
  }
}
```

GST control:

```json
{
  "type": "GST_ON_FEE",
  "parameters": {
    "rate": 0.18
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

Allow a configurable tolerance, e.g. ₹0.01.

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
  "affected_count": 23,
  "expected_rate": 0.0155,
  "observed_rate": 0.0175,
  "first_seen": "...",
  "last_seen": "...",
  "verified_impact": "8421.70"
}
```

---

# 16. AI Contract-Control Extraction

Input:
- agreement text or parsed PDF text

Output candidate structured controls.

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

User approval moves it to `APPROVED`.

Do not execute unapproved controls.

For the demo, support a synthetic merchant agreement with:
- domestic MDR
- international MDR
- GST
- T+2 settlement
- refund fee = ₹0

---

# 17. Hypothesis Verification

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
  "proposed_value": 0.0175,
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
- hypothesis is rejected as a legitimate policy change
- classify as potential systemic overcharge

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
GET /api/v1/agreements/{agreement_id}/control-proposals
```

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
POST /api/v1/root-causes/{root_cause_id}/generate-hypothesis
POST /api/v1/root-causes/{root_cause_id}/verify-hypothesis
```

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

# 21. Demo Seed

Support a known deterministic demo seed.

Example:

```text
DEMO_SEED=20260825
```

The demo run should always contain:
- one clear hidden MDR overcharge
- one duplicate refund deduction
- one SLA violation
- one systemic cluster of MDR rate drift
- 3 intentionally unresolved cases
- one schema-drift sample

This enables a reliable recorded demo.

---

# 22. Persistence Strategy

Use PostgreSQL for:
- controls
- runs
- events
- edges
- evaluations
- violations
- root causes
- human review states

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

## Integration
- ingest demo files
- build graph
- execute controls
- compare against ground truth
- retrieve run summary

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
- failures

Never log full sensitive raw payloads in normal logs.

---

# 25. Security / Safety

For Buildathon:
- synthetic data only
- file size limits
- MIME validation
- sanitize filenames
- do not execute uploaded content
- contract extraction treats document text as untrusted input
- structured AI outputs only
- secrets via environment variables

---

# 26. Environment Variables

Example:

```env
DATABASE_URL=postgresql+psycopg://...
LLM_PROVIDER=openai
LLM_API_KEY=
LLM_MODEL=
DEMO_SEED=20260825
CORS_ORIGINS=http://localhost:3000
```

Core deterministic pipeline must run even if no LLM key is present.

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
│   ├── ai/
│   │   ├── contract_extractor.py
│   │   ├── hypothesis.py
│   │   └── explanation.py
│   ├── drift/
│   └── synthetic/
├── tests/
├── alembic/
├── pyproject.toml
└── Dockerfile
```

---

# 28. Definition of Done — Backend MVP

Backend is demo-ready when:

- seeded 500-payment dataset can be generated
- all sources can be ingested
- event graph is created
- at least 5 control types execute
- expected-vs-actual endpoint works
- hidden fee overcharge is detected even when settlement equals bank credit
- verified leakage is calculated
- duplicate refund deduction is detected
- SLA violation is detected
- similar violations cluster into a root cause
- hypothesis can be generated and deterministically verified/rejected
- 3 ambiguous cases remain unresolved
- precision/recall are computed from hidden ground truth
- core run works without an LLM
- API tests pass

---

# 29. Explicit Non-Goals

Do not implement:
- blockchain
- wallets
- production Razorpay APIs
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

## Candidate Control Backtesting — P1

AI-generated controls must be tested before approval.

Workflow:

```text
candidate control
→ historical backtest
→ mutation suite
→ precision/recall delta
→ false-positive delta
→ explicit user approval/rejection
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
POST /api/v1/runs/{run_id}/replay
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
  "actual": {"gross":"100000.00","mdr":"1750.00","gst":"315.00","refunds":"5000.00","net":"92935.00"},
  "expected": {"gross":"100000.00","mdr":"1550.00","gst":"279.00","refunds":"5000.00","net":"93171.00"},
  "difference":"236.00",
  "drivers":[
    {"type":"EXCESS_MDR","amount":"200.00"},
    {"type":"EXCESS_GST","amount":"36.00"}
  ]
}
```

## Updated Backend Build Order

```text
1. Synthetic dataset + ground truth
2. Domain models
3. Ingestion / normalization
4. Financial Event Graph
5. Deterministic controls
6. Expected-vs-Actual
7. Batch metrics
8. Financial Mutation Testing
9. Mutation coverage + blind spots
10. Exception APIs
11. Violation Lineage
12. Root-cause clustering
13. Agreement → candidate controls
14. Candidate-control backtest
15. AI hypothesis generation
16. Independent hypothesis verifier
17. Control Coverage Graph
18. Time-versioned controls
19. Temporal replay
20. Schema drift
```

Mutation testing must be built before generalized agent features.

## Additional Backend Definition of Done

The differentiated MVP is not backend-complete until:

- at least 8 deterministic mutation types work
- Mutation Detection Rate is computed
- at least one deliberate blind spot is demonstrable
- candidate controls can be backtested before approval
- canonical data is unchanged by mutation tests
- violation lineage separates primary failures from downstream effects
- control coverage identifies governed vs ungoverned edges
- time-versioned controls select the correct rule at a date boundary
- counterfactual settlement reconstruction works
