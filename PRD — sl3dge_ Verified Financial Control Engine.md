# sl3dge — Product Requirements Document

## 1. Product Summary

**Product:** sl3dge  
**Track:** Razorpay Buildathon — AI Finance Controller  
**Category:** Financial controls / reconciliation intelligence  
**Core thesis:** Reconciliation proves that two records agree. **sl3dge proves that the money behaved correctly.**

sl3dge converts financial agreements and operational policies into executable controls, reconstructs the lifecycle of transactions across multiple financial systems, and verifies whether actual money movement follows those controls.

Instead of merely asking:

> “Does the gateway settlement match the bank credit?”

sl3dge asks:

> “Given the merchant agreement, settlement terms, fee schedules, refunds and transaction lifecycle, is this settlement actually correct?”

The system must be able to process a batch of **50+ records**, report measurable accuracy and throughput, explain verified violations, group related exceptions into root causes, and explicitly identify cases it cannot safely resolve.

---

# 2. Problem

Businesses receive financial information from multiple systems:

- Order management systems
- Payment gateways
- Settlement reports
- Bank statements
- Refund systems
- Chargeback reports
- Commercial agreements and rate cards

Traditional reconciliation primarily validates whether records from different systems agree.

Example:

```text
Gateway settlement: ₹9,793.50
Bank credit:        ₹9,793.50

Result: MATCHED
```

However, both records may reflect the same incorrect deduction.

Merchant agreement:

```text
Transaction value:       ₹10,000
Contracted MDR:          1.55%
Expected MDR:            ₹155
Expected GST on MDR:     ₹27.90
Expected net settlement: ₹9,817.10
```

Actual gateway deduction:

```text
Actual MDR:              ₹175
Actual GST:              ₹31.50
Actual net settlement:   ₹9,793.50
```

The gateway and bank agree perfectly.

A normal reconciliation system reports:

**MATCHED**

sl3dge reports:

```text
CONTROL VIOLATION

Excess MDR: ₹20.00
Excess GST: ₹3.60
Total verified leakage: ₹23.60
```

This is the core problem sl3dge solves.

---

# 3. Product Vision

Build a **verification layer for financial operations**.

sl3dge should create an executable representation of:

> **What should have happened**

and continuously compare it with:

> **What actually happened**

across the complete lifecycle of every transaction.

The system should be:

- Evidence-driven
- Deterministic where possible
- AI-assisted where useful
- Explicit about uncertainty
- Auditable
- Quantitatively measurable
- Highly visual and demoable

---

# 4. Product Principle

## Automate what can be proven.

## Investigate what can be tested.

## Escalate what cannot be trusted.

AI may generate hypotheses.

**AI may not redefine financial truth.**

---

# 5. Target User

## Primary User: Finance Operations Analyst

Responsible for:

- Settlement reconciliation
- Fee verification
- Refund reconciliation
- Identifying unexplained deductions
- Investigating discrepancies
- Following up on financial leakage

### Current workflow

The analyst frequently has to:

1. Open a payment report.
2. Locate the settlement.
3. Search the bank statement.
4. Calculate deductions manually.
5. Check the merchant rate card.
6. Search refund records.
7. Determine whether the discrepancy is legitimate.
8. Record the explanation somewhere.

sl3dge should collapse most of this investigation into a single traceable workflow.

---

## Secondary User: Finance Controller

Needs visibility into:

- Money at risk
- Verified financial leakage
- Settlement SLA violations
- Root causes
- Control pass/fail rates
- Exceptions requiring human review
- Changes in financial behaviour over time

---

# 6. Jobs To Be Done

### JTBD 1

When money is settled, tell me whether the settlement is **actually financially correct**, not merely whether records agree.

### JTBD 2

When something is wrong, show me exactly:

- what happened,
- what should have happened,
- the difference,
- the underlying evidence,
- the violated control.

### JTBD 3

When many failures occur, determine whether they represent many independent problems or one systemic root cause.

### JTBD 4

When data or financial behaviour changes, determine whether:

- the underlying policy changed,
- the upstream schema changed,
- or an actual financial violation occurred.

### JTBD 5

When the system cannot prove the answer, tell me instead of inventing one.

---

# 7. Product Architecture Concept

sl3dge consists of five core systems.

```text
                    ┌─────────────────────┐
                    │ Contracts / Policies│
                    │ Rate Cards / SLAs   │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │ Financial Control   │
                    │ Compiler            │
                    └──────────┬──────────┘
                               │
                    Executable Controls
                               │
                               ▼
Orders ─┐
Payments│
Refunds ├──────────────► Financial Event Graph
Settle. │                        │
Bank ───┘                        │
                                ▼
                    ┌─────────────────────┐
                    │ Deterministic       │
                    │ Verification Engine │
                    └──────────┬──────────┘
                               │
                ┌──────────────┴─────────────┐
                │                            │
              PASS                       VIOLATION
                                             │
                                             ▼
                                   AI Investigator
                                             │
                                      Hypothesis
                                             │
                                             ▼
                                        Verifier
                                             │
                              ┌──────────────┴──────────┐
                              │                         │
                           PROVEN                   UNRESOLVED
```

---

# 8. Core Product Components

## 8.1 Financial Control Compiler

### Purpose

Convert human-readable commercial agreements into structured financial controls.

Input examples:

- Merchant agreements
- Rate cards
- Settlement SLAs
- Refund policies
- Fee schedules

For the Buildathon MVP, these may be synthetic documents.

### Example clause

> Domestic Visa and Mastercard transactions shall be charged an MDR of 1.55%. Applicable GST shall be charged at 18% on the processing fee.

sl3dge extracts:

```text
Control ID: MDR_DOMESTIC_CARD

Applies when:
payment_method = card
AND card_type = domestic

Expected:
mdr_rate = 1.55%

Source:
Merchant Agreement §4.2

Confidence:
97%
```

Separate control:

```text
Control ID: GST_PROCESSING_FEE

Expected:
GST = processing_fee × 18%

Source:
Merchant Agreement §4.3
```

---

## 8.2 Control Review

AI-generated controls must not become active automatically.

The UI should show:

```text
Detected Control

Domestic Card MDR
1.55%

Applies to:
Visa / Mastercard Domestic

Source:
Merchant Agreement
Page 4, Clause 4.2

[Approve] [Modify] [Reject]
```

For the demo, controls may already be approved after extraction.

### Requirement

Every control must preserve provenance back to its source clause.

---

# 9. Financial Event Graph

The event graph reconstructs the complete lifecycle of money.

Instead of treating records as unrelated spreadsheet rows:

```text
PAY_391
SET_82
REF_29
BANK_392
```

sl3dge connects them.

Example:

```text
ORDER_12
   │
   ▼
PAY_391
₹10,000
   │
   ├──── MDR ──── ₹175
   │
   ├──── GST ──── ₹31.50
   │
   └──── REFUND ─► ₹2,000
   │
   ▼
SET_82
₹7,793.50
   │
   ▼
BANK_392
₹7,793.50
```

Relationships become first-class objects.

Examples:

```text
ORDER ──paid_by──────► PAYMENT

PAYMENT ──included_in► SETTLEMENT

PAYMENT ──refunded_by► REFUND

SETTLEMENT ──credited_as► BANK_ENTRY

PAYMENT ──charged_fee► FEE
```

---

# 10. Control Engine

Controls operate over nodes and edges in the financial event graph.

## Control Type A — Fee Controls

Example:

```text
Expected MDR:
transaction_amount × contracted_rate
```

Verify:

```text
Expected = ₹10,000 × 1.55%
         = ₹155

Actual = ₹175

FAIL
Difference = ₹20
```

---

## Control Type B — Tax Controls

```text
Expected GST:
processing_fee × 18%
```

---

## Control Type C — Settlement SLA

```text
Payment captured:
17 August

Contract:
T+2

Expected settlement:
≤ 19 August

Actual:
22 August

FAIL

Delay:
3 days
```

---

## Control Type D — Refund Integrity

Rule:

> A refund principal should not be deducted more than once.

Event graph:

```text
             ┌─ SET_103: -₹1,000
REF_39 ──────┤
             └─ SET_109: -₹1,000
```

Result:

```text
DUPLICATE REFUND DEDUCTION

Verified exposure:
₹1,000
```

---

## Control Type E — Settlement Arithmetic

Verify:

```text
Gross
− valid fees
− GST
− refunds
± adjustments
=
expected settlement
```

---

## Control Type F — Lifecycle Validity

Examples:

- Refund exists without captured payment
- Settlement references unknown payment
- Chargeback deduction appears twice
- Failed payment appears in settlement
- Refund exceeds original payment amount

---

# 11. Expected-vs-Actual Engine

This should be the principal product surface.

Every inspected transaction shows two parallel states.

## EXPECTED

Calculated using:

- Contract controls
- Event history
- Fee schedule
- Refund state
- Settlement SLA

## ACTUAL

Derived from:

- Gateway
- Settlement
- Bank
- Refund
- Order data

Example:

```text
                EXPECTED        ACTUAL

Gross           ₹10,000         ₹10,000
MDR             ₹155            ₹175       ❌
GST             ₹27.90          ₹31.50     ❌
Refund          ₹0              ₹0
Net             ₹9,817.10       ₹9,793.50  ❌
Bank Credit     ₹9,817.10       ₹9,793.50
```

### Result

```text
Verified Leakage
₹23.60
```

---

# 12. Root Cause Investigator

The agent should not merely summarize exceptions individually.

It should identify shared structure across violations.

Example:

```text
31 total violations found.

23 have the same pattern.
```

Agent output:

```text
ROOT CAUSE CLUSTER RC-04

Affected transactions:
23

Payment type:
Domestic Visa

Expected MDR:
1.55%

Observed MDR:
1.75%

First occurrence:
18 August 2026 14:03

Other payment methods:
Unaffected

Total verified impact:
₹8,421.70
```

---

# 13. Hypothesis Verification

This is a key differentiator.

The AI investigator can propose:

> The Visa Domestic MDR may have changed from 1.55% to 1.75% beginning on August 18.

But sl3dge must **not accept this as truth**.

The hypothesis enters the verifier.

### Verification Process

Check:

1. Merchant agreement
2. Approved amendments
3. Rate cards
4. Historical behaviour
5. Affected transactions
6. Unaffected control groups

Result:

```text
HYPOTHESIS TEST

Observed:
1.75%

Contract:
1.55%

Amendments:
No change found

Historical:
1.55%

Transactions reproducing change:
37 / 37

RESULT:
HYPOTHESIS REJECTED AS VALID POLICY CHANGE

Classification:
Potential systemic overcharge
```

This provides visible evidence that sl3dge uses AI for discovery but deterministic evidence for decisions.

---

# 14. Rule Drift vs Financial Violation

sl3dge must distinguish:

### Scenario A — Legitimate policy change

New agreement:

```text
MDR changes:
1.55% → 1.65%
effective 01 September
```

Then observed 1.65% after that date is valid.

---

### Scenario B — Behaviour changed without policy change

Observed:

```text
1.55% → 1.75%
```

Contract:

```text
still 1.55%
```

Result:

**Financial violation**

---

# 15. Source Schema Drift Detection

Financial operations frequently break because upstream report formats change.

Example old gateway schema:

```text
payment_id
settlement_id
fee
tax
```

New version:

```text
txn_reference
settlement_ref
processing_charge
gst
```

sl3dge detects:

```text
SOURCE DRIFT DETECTED

payment_id       → txn_reference
settlement_id    → settlement_ref
fee              → processing_charge
tax              → gst
```

Suggested mapping receives confidence scores.

Example:

```text
payment_id → txn_reference
Confidence: 99.8%
```

---

# 16. Mapping Backtest

AI-suggested mappings cannot be accepted directly.

Click:

**Verify Mapping**

System runs old and proposed mappings across historical data.

Example:

```text
BACKTEST

Records:
200

Identifier collisions:
0

Broken relations:
0

Amount inconsistencies:
0

Previously reconciled records retained:
200 / 200

RESULT:
PASS
```

Only then can the mapping become active.

---

# 17. Exception Inbox

All issues requiring attention appear here.

Categories:

- Fee violation
- Tax violation
- Settlement delay
- Duplicate deduction
- Missing record
- Lifecycle violation
- Schema drift
- Unsupported fee
- Ambiguous match
- Unresolved

Example card:

```text
VIOLATION #V-1092

PAY_82HD9

Expected MDR:
₹155

Actual MDR:
₹175

Verified loss:
₹20

Confidence:
100%

Control:
MDR_DOMESTIC_CARD

Source:
Merchant Agreement §4.2
```

---

# 18. Evidence View

Every violation must contain independently understandable evidence.

### Evidence panel

```text
Violation:
Domestic Card MDR

Transaction:
PAY_82HD9

Transaction Value:
₹10,000

Expected:
₹155

Actual:
₹175

Difference:
₹20

Calculation:
₹10,000 × 1.55% = ₹155

Contract source:
Merchant Agreement §4.2

Gateway record:
ROW 289

Settlement:
SET_381

Bank record:
BANK_919
```

This is critical for demo credibility.

---

# 19. Evidence Pack

User can generate a structured case package for a violation or root-cause cluster.

Contents:

```text
CASE SUMMARY

23 affected transactions

Control violated:
Domestic Card MDR

Contracted:
1.55%

Observed:
1.75%

Verified financial impact:
₹8,421.70
```

Attach:

- Source clause
- Affected transaction IDs
- Expected calculations
- Actual charges
- Settlement references
- Root-cause analysis

MVP output may be displayed in-app rather than requiring a polished PDF.

---

# 20. Batch Control Run

The Buildathon explicitly requires a complete finance loop across a batch.

Recommended demo dataset:

## 500 payment transactions

Generating approximately:

- 500 order events
- 500 payment events
- ~90 settlement events
- ~90 bank entries
- 40–60 refund events
- 5–10 chargebacks

Total:

**1,200–1,500+ financial events**

---

# 21. Planted Dataset Scenarios

The synthetic data generator should deliberately include known ground-truth abnormalities.

Suggested scenarios:

### Normal transactions

~400 transactions.

---

### MDR overcharge

25 transactions.

Expected:

```text
1.55%
```

Actual:

```text
1.75%
```

---

### Duplicate refund deductions

5 cases.

---

### Settlement SLA violations

10 cases.

---

### Unsupported flat fees

8 cases.

---

### Incorrect GST

8 cases.

---

### Missing bank settlement

5 cases.

---

### Schema drift

Second batch changes column structure.

---

### Ambiguous relationships

3–5 intentionally unresolved cases.

These ensure the product can be quantitatively evaluated.

---

# 22. Ground Truth

The synthetic generator must produce a separate ground-truth file that the application itself does not use for inference.

Example:

```text
PAY_001
expected_status = PASS

PAY_002
expected_status = MDR_VIOLATION
expected_loss = 23.60

PAY_003
expected_status = DUPLICATE_REFUND
expected_loss = 1000

PAY_004
expected_status = UNRESOLVED
```

Evaluation compares sl3dge's results against this ground truth.

---

# 23. Metrics

The main results screen must show real metrics.

## Control Precision

Of all violations sl3dge raised:

> How many were genuinely violations?

Target:

**>98%**

---

## Violation Recall

Of all planted violations:

> How many did sl3dge detect?

Target:

**>95%**

---

## False Positive Rate

Must be shown explicitly.

Target:

**<2%**

---

## Throughput

Example:

```text
500 transactions
1,250 controls
4.8 seconds
```

Exact target depends on implementation.

---

## Verified Leakage

Sum only deviations that sl3dge can mathematically establish.

Do not include ambiguous cases.

---

## Unresolved Exceptions

Must be reported rather than hidden.

---

# 24. Results Dashboard

Example:

```text
AUGUST CONTROL RUN

500 transactions
1,215 controls evaluated

PASS                    1,173
VIOLATION                  31
WARNING                     8
UNRESOLVED                  3

Control precision          98.9%
Violation recall           96.7%

Verified cash leakage      ₹12,638.40
Cash delayed beyond SLA    ₹3,84,290

Processing time            4.8 sec
```

Root causes:

```text
MDR rate deviation             ₹8,421
Duplicate refund deductions    ₹2,000
Unsupported fees               ₹1,748
Incorrect fee taxation           ₹469
```

---

# 25. Human Review

For unresolved cases:

```text
UNRESOLVED

Possible matches:

SET_921
SET_924

Both transactions have:
same amount
similar timestamp
insufficient identifiers

sl3dge cannot safely determine
the correct relationship.
```

Actions:

- Confirm relationship
- Reject proposed relationships
- Keep unresolved
- Add note

Human decisions should become part of the audit trail.

---

# 26. AI Responsibilities

AI may:

- Parse contracts
- Propose structured controls
- Categorize unusual exceptions
- Identify root-cause clusters
- Generate hypotheses
- Suggest schema mappings
- Produce human-readable explanations

AI may **not**:

- Invent missing financial records
- Override deterministic arithmetic
- Declare an unsupported control valid
- Force ambiguous matches
- Modify ground truth
- Automatically redefine approved contractual expectations

---

# 27. Deterministic Responsibilities

Non-AI components must perform:

- Arithmetic validation
- Identifier matching
- Fee calculations
- Tax calculations
- Date/SLA calculations
- Event relationship validation
- Control execution
- Ground-truth evaluation
- Backtesting
- Metric calculation

This separation is central to product credibility.

---

# 28. Main Screens

## Screen 1 — Home / Control Runs

Displays previous verification runs.

---

## Screen 2 — Control Library

```text
12 ACTIVE CONTROLS

Domestic Card MDR          1.55%
International Card MDR     2.90%
GST on Processing Fee      18%
Settlement SLA             T+2
Refund Fee                 ₹0
...
```

---

## Screen 3 — Agreement Import

Upload agreement.

Display extracted controls side-by-side with contract clauses.

---

## Screen 4 — New Control Run

Upload/select:

- Orders
- Payments
- Settlements
- Refunds
- Bank statement

Click:

**Run sl3dge**

---

## Screen 5 — Results Dashboard

Metrics + root causes.

---

## Screen 6 — Transaction Inspector

Expected vs actual.

---

## Screen 7 — Trace Money

Interactive event graph.

---

## Screen 8 — Exception Inbox

Filter violations by:

- category,
- monetary impact,
- confidence,
- status.

---

## Screen 9 — Root Cause

Shows clustered abnormalities and affected population.

---

## Screen 10 — Hypothesis Verification

AI hypothesis + deterministic backtest result.

---

## Screen 11 — Drift Review

Schema change and mapping validation.

---

# 29. MVP Priority

## P0 — Absolutely required

### 1. Synthetic dataset generator

Without ground truth we cannot prove accuracy.

### 2. Control model

At least:

- MDR
- GST
- Settlement SLA
- Refund integrity

### 3. Event graph

Must link payment lifecycle records.

### 4. Deterministic verification engine

Core product.

### 5. Expected-vs-actual inspector

Core demo interface.

### 6. Batch run

At least 50 records; target 500.

### 7. Exception inbox

### 8. Measured precision / recall

### 9. Unresolved exceptions

### 10. Root cause clustering

### 11. AI explanation grounded in evidence

---

# 30. P1 — Strong differentiators

### Agreement → Control Compiler

Highly valuable for demo.

### Hypothesis → Backtest

One of the strongest differentiation features.

### Financial Event Graph Visualization

Extremely valuable for video.

### Evidence Pack

Useful operational endpoint.

---

# 31. P2 — Only if time permits

### Schema drift detection

Excellent demo feature but secondary to controls.

### Natural-language queries

Example:

> Show every settlement where the merchant was overcharged.

Useful, but not fundamental.

### Historical control trends

### Multiple contract versions

---

# 32. Explicit Non-Goals

Do **not** spend Buildathon time building:

- Blockchain
- Tokens
- Wallet connectivity
- Full accounting software
- ERP integrations
- Actual Razorpay production integrations
- Generic finance chatbot
- Generic forecasting
- Accounts payable
- Invoice OCR system
- Tax filing
- Autonomous bank transfers
- Beautiful but shallow analytics
- Hundreds of configurable control types

Depth of one complete loop matters more than breadth.

---

# 33. Recommended Technology Stack

## Frontend

**Next.js + TypeScript**

Responsibilities:

- Dashboard
- Event graph
- Expected-vs-actual view
- Control library
- Exception inbox

---

## Backend

**FastAPI + Python**

Responsibilities:

- Data ingestion
- Control execution
- Event graph construction
- Evaluation
- Agent endpoints

---

## Database

**PostgreSQL**

Store:

- Runs
- Transactions
- Events
- Controls
- Relationships
- Violations
- Evidence
- Agent hypotheses

---

## Data Processing

Prefer:

**Polars**

or Pandas if development speed is more important.

---

## AI Layer

Use an LLM for:

- Contract parsing
- Root-cause descriptions
- Hypothesis generation
- Schema mapping suggestions

Agent orchestration can use **LangGraph** if it genuinely improves the implementation.

Do not introduce it solely to advertise an "agentic architecture."

---

# 34. Simplified Data Model

## Control

```text
id
name
control_type
conditions
expected_formula
effective_from
effective_to
source_document
source_clause
status
```

---

## Event

```text
id
source
external_id
event_type
amount
timestamp
metadata
```

---

## EventEdge

```text
id
from_event
to_event
relationship
confidence
```

---

## ControlEvaluation

```text
id
control_id
event_id
expected_value
actual_value
difference
status
evidence
```

---

## Violation

```text
id
evaluation_id
category
financial_impact
confidence
root_cause_id
review_status
```

---

## RootCause

```text
id
description
affected_transactions
total_impact
hypothesis
verification_status
```

---

# 35. Functional Requirements

### FR-01
The system shall process batches containing at least 50 synthetic financial records.

### FR-02
The system shall evaluate merchant-defined financial controls against transactions.

### FR-03
The system shall preserve provenance between controls and source clauses.

### FR-04
The system shall reconstruct transaction lifecycle relationships.

### FR-05
The system shall calculate expected financial behaviour independently of actual settlement values.

### FR-06
The system shall identify violations where actual behaviour differs from expected behaviour.

### FR-07
The system shall calculate monetary impact for provable violations.

### FR-08
The system shall expose evidence supporting every violation.

### FR-09
The system shall identify unresolved cases where evidence is insufficient.

### FR-10
The system shall calculate precision, recall and false-positive rate against ground truth.

### FR-11
The system shall group structurally similar violations.

### FR-12
The agent shall propose likely explanations for grouped anomalies.

### FR-13
AI-generated hypotheses shall be verified before being accepted.

### FR-14
Users shall be able to visually trace a transaction through its lifecycle.

### FR-15
The system shall report processing throughput.

---

# 36. Non-Functional Requirements

## Explainability

Every financial conclusion must be understandable without reading model reasoning.

---

## Safety

When confidence or evidence is insufficient:

**UNRESOLVED**

must be preferred over a guessed answer.

---

## Reproducibility

Identical source data and controls should produce identical deterministic results.

---

## Performance

Target:

**500 transactions in under 10 seconds excluding optional LLM investigation.**

The core verifier must not depend on LLM latency.

---

## Auditability

Every decision should expose:

- source records,
- control,
- calculation,
- status,
- timestamp.

---

# 37. Demo Narrative

The final video should show the product working rather than explaining architecture.

## Scene 1 — Establish the problem

Show a transaction where:

```text
Gateway settlement = Bank credit
```

Therefore normal reconciliation passes.

---

## Scene 2 — Import agreement

Drop merchant agreement.

sl3dge identifies:

```text
Domestic Card MDR: 1.55%
GST: 18%
Settlement: T+2
Refund Fee: ₹0
```

Show clause provenance.

---

## Scene 3 — Run 500 transactions

Click:

**Run Controls**

Show actual processing and results.

---

## Scene 4 — Reveal hidden leakage

Open the apparently reconciled ₹10,000 transaction.

Show:

```text
Expected MDR: ₹155
Actual MDR: ₹175

Expected GST: ₹27.90
Actual GST: ₹31.50

Verified leakage:
₹23.60
```

---

## Scene 5 — Trace the money

Show interactive lifecycle graph.

---

## Scene 6 — Systemic root cause

23 similar violations collapse into:

```text
Domestic Visa MDR changed from
1.55% → 1.75%

Affected:
23 transactions

Impact:
₹8,421.70
```

---

## Scene 7 — Challenge the AI

Agent suggests:

> Perhaps the contracted rate changed.

Click:

**Verify Hypothesis**

System finds no supporting contract amendment.

```text
HYPOTHESIS REJECTED

Observed behaviour changed.
Contractual expectation did not.
```

---

## Scene 8 — Different violation type

Show duplicate refund deduction or settlement SLA breach.

This demonstrates that sl3dge is a **financial control engine**, not merely an MDR calculator.

---

## Scene 9 — Honest failure

Show one ambiguous case.

```text
UNRESOLVED

Insufficient evidence to determine
the correct settlement relationship.
```

---

## Scene 10 — Final scorecard

End with measurable results.

```text
500 transactions
1,215 controls

98.9% precision
96.7% violation recall
3 unresolved cases

₹12,638 verified leakage
₹3,84,290 delayed beyond SLA
```

---

# 38. Demo Acceptance Criteria

We should not consider the MVP ready until the video can visibly prove all of these:

- [ ] Agreement clause becomes an executable control.
- [ ] Judge can see where the control came from.
- [ ] At least 500 synthetic transactions can be processed.
- [ ] An apparently reconciled transaction is proven financially incorrect.
- [ ] Expected and actual calculations are visible.
- [ ] Complete transaction lifecycle can be traced.
- [ ] Multiple violations are grouped into one root cause.
- [ ] AI produces a hypothesis.
- [ ] Hypothesis is independently verified.
- [ ] At least one different control category is demonstrated.
- [ ] At least one case remains intentionally unresolved.
- [ ] Precision and recall are computed from hidden ground truth.
- [ ] Monetary impact is calculated only for verified violations.
- [ ] The entire core demo works without relying on narration to explain what happened.

---

# 39. Product Moat

The moat is **not**:

- Reconciliation
- AI
- Contract extraction
- Fuzzy matching
- Dashboards
- Finance chatbots

Those individually already exist.

sl3dge's differentiation is the closed verification loop:

```text
FINANCIAL AGREEMENT
        ↓
EXECUTABLE CONTROLS
        ↓
EXPECTED FINANCIAL STATE
        ↓
ACTUAL EVENT GRAPH
        ↓
DETERMINISTIC VERIFICATION
        ↓
VIOLATION
        ↓
AI ROOT-CAUSE HYPOTHESIS
        ↓
BACKTEST / EVIDENCE CHECK
        ↓
PROVEN / REJECTED / UNRESOLVED
```

The system therefore separates:

**what appears consistent**

from

**what is actually correct.**

---

# 40. Positioning

### Bad positioning

> AI-powered reconciliation platform.

Too generic.

### Better

> AI Finance Controller that detects financial behaviour your reconciliation system thinks is correct.

### Strongest concise positioning

> **sl3dge proves whether your money moved the way it was supposed to.**

### Product contrast

> **Reconciliation asks whether the records match. sl3dge asks whether they should.**

---

# 41. MVP Success Definition

sl3dge succeeds if a judge can watch the demo and independently conclude:

1. The system processed a meaningful batch.
2. It found problems that simple record matching would miss.
3. Its expected values came from explicit financial controls.
4. Its arithmetic can be inspected.
5. The AI is useful but not blindly trusted.
6. Root causes can be demonstrated rather than merely described.
7. Accuracy is objectively measured.
8. Uncertainty is visible.
9. The product closes a real finance-operations verification loop.
10. The product clearly goes beyond an LLM wrapped around spreadsheets.

**That is the version of sl3dge we should build.**