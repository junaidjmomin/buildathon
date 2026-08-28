# sl3dge — Product Features & Novelty Handoff

## Specification Authority

Authority order:

1. `features.md` defines product scope and priority.
2. `backend.md` defines backend behavior, API, and domain contracts.
3. `frontend.md` defines UI behavior and the recorded demo flow.
4. `techstack.md` defines engineering implementation choices.

If two sections conflict, the later section explicitly marked **authoritative**
wins. This document contains one product-priority definition; the other handoff
documents must implement it without introducing competing scope.

## 0. Why This Document Exists

This document separates:

- table-stakes functionality,
- useful product differentiation,
- and the features that should actually define **sl3dge**.

Do not treat every feature in the product as equally novel.

The core product thesis remains:

> Reconciliation asks whether records match. sl3dge asks whether they should.

The stronger product thesis is now:

> sl3dge verifies both financial transactions **and the controls meant to catch financial failures**.

This is the main novelty.

---

# 1. Feature Classification

## Table Stakes — Necessary, But Not Novel

These are required to make the product credible, but they must not be pitched as the moat.

### Multi-source ingestion
- Orders
- Payments
- Settlements
- Bank statements
- Refunds
- Chargebacks

### Deterministic matching
- exact IDs
- amount relationships
- timing windows
- many-to-one settlement relationships

### Exception inbox
- violations
- warnings
- unresolved cases
- human review

### MDR / fee validation
- contractual fee vs actual fee

### GST validation
- expected tax vs actual tax

### Refund validation
- duplicate deduction
- over-refund
- invalid refund lifecycle

### Settlement SLA verification
- contractual T+N vs actual settlement date

### AI explanations
Useful for UX, but never the headline innovation.

### Schema mapping
Useful, but already common in reconciliation tools.

---

# 2. Product Differentiators

These features make sl3dge meaningfully stronger.

## Financial Control Compiler

Turn commercial agreements into structured, executable controls.

```text
Agreement clause
    ↓
Candidate structured rule
    ↓
Human review
    ↓
Approved executable control
```

Requirements:
- source provenance
- effective date
- version history
- conditions
- structured parameters
- approval state

Example:

```text
Clause 4.2

Domestic Visa / Mastercard MDR
1.55%

Effective:
1 Jan 2026
```

becomes:

```text
MDR_RATE

scope:
card_scope = domestic

rate:
1.55%
```

---

## Financial Event Graph

Represent the lifecycle of money as events and relationships.

Example:

```text
ORDER
  ↓
PAYMENT
  ├── FEE
  ├── GST
  ├── REFUND
  ↓
SETTLEMENT
  ↓
BANK CREDIT
```

The graph is not merely a visual feature.

Controls operate over graph nodes and edges.

Each relationship should answer:

> What control governs this transition?

---

## Expected-vs-Actual Verification

For every financial lifecycle:

```text
What should have happened?
        vs
What actually happened?
```

This must reconstruct the expected financial outcome independently of actual settlement values.

Example:

```text
                    Expected      Actual

Gross               ₹10,000       ₹10,000
MDR                 ₹155          ₹175
GST                 ₹27.90        ₹31.50
Settlement          ₹9,817.10     ₹9,793.50
Bank Credit         ₹9,817.10     ₹9,793.50
```

Verified leakage:

```text
₹23.60
```

---

# 3. Headline Novelty #1 — Financial Mutation Testing

This must become a first-class product feature.

## Concept

Traditional controls are evaluated against observed data.

sl3dge also tests whether the controls themselves are capable of catching failures.

It deliberately injects realistic financial faults into known-good transactions.

Examples:

```text
MDR 1.55% → 1.75%

Duplicate refund deduction

Settlement delayed 3 business days

Incorrect GST base

Unknown ₹49 platform fee

Failed payment included in settlement

Refund amount exceeds captured amount

Payment instrument silently reclassified
```

Then sl3dge re-runs the control suite.

---

## Mutation Test Output

Example:

```text
FINANCIAL CONTROL TEST

50 mutations injected

Detected                    47
Missed                       3

Mutation Detection Rate     94%

False Positives               0
```

Coverage by control:

```text
MDR                         100%
GST                         100%
Refund Integrity             90%
Settlement Lifecycle         92%
Unsupported Fees             60%
```

---

## Why It Matters

A control system saying:

> 98% of transactions passed

does not prove the controls are good.

Mutation testing asks:

> If the money were wrong, would our controls actually catch it?

This is one of sl3dge's strongest novelty claims.

---

## Mutation Testing Requirements

System must support:
- seeded mutations
- mutation type
- target event
- expected detection control
- detected / missed status
- false-positive accounting
- coverage metrics
- control blind-spot reporting

Mutation tests must never modify the canonical original dataset.

Use an isolated derived test run.

---

# 4. Headline Novelty #2 — Control Blind-Spot Detection

Mutation testing should expose control gaps.

Example:

```text
MISSED MUTATION

Unexpected platform fee
₹49
```

sl3dge identifies:

```text
CONTROL BLIND SPOT

No approved control currently governs
miscellaneous settlement fees.
```

Then the AI may search the agreement and propose:

```text
UNSUPPORTED_FEE

Any settlement fee not explicitly
listed in the approved rate schedule
must be flagged.
```

The proposed control must be tested before activation.

---

# 5. Headline Novelty #3 — Test a New Control Before Approval

AI-generated controls are not accepted because they sound correct.

Workflow:

```text
Blind spot detected
      ↓
AI proposes control
      ↓
Run historical backtest
      ↓
Run mutation test suite
      ↓
Compare detection coverage
      ↓
Measure false positives
      ↓
Approve / Reject
```

Example:

```text
Before

47 / 50 mutations detected

After candidate control

49 / 50 mutations detected

New false positives:
0
```

Only then:

```text
APPROVE CONTROL
```

This is critical.

The AI does not just create rules.

sl3dge proves whether those rules improve financial verification.

---

# 6. Headline Novelty #4 — AI Hypothesis + Independent Verifier

AI is allowed to discover patterns.

It is not allowed to define truth.

Example:

```text
AI Hypothesis

Domestic Visa MDR changed from
1.55% to 1.75% on 18 August.
```

Verifier checks:
- approved agreement
- approved amendments
- effective dates
- historical behavior
- affected segment
- unaffected comparison segment

Result:

```text
HYPOTHESIS REJECTED

Observed behaviour changed.
Contractual expectation did not.

Classification:
Potential systemic overcharge
```

Every hypothesis ends in:

```text
PROVEN
REJECTED
UNRESOLVED
```

Never:
```text
PROBABLY TRUE, AUTO-APPLY
```

---

# 7. Headline Novelty #5 — Control Coverage Graph

Every financial relationship should be mapped to the control that governs it.

Example:

```text
PAYMENT
   │
   │ MDR_RATE ✓
   │ GST_ON_FEE ✓
   ▼
SETTLEMENT
   │
   │ SETTLEMENT_ARITHMETIC ✓
   │ SETTLEMENT_SLA ✓
   ▼
BANK

REFUND
   │
   │ REFUND_INTEGRITY ✓
   ▼
SETTLEMENT

CHARGEBACK
   │
   │ ??? ⚠
   ▼
SETTLEMENT
```

Then compute:

```text
CONTROL COVERAGE

2,009 material relationships

2,000 governed
9 ungoverned

Coverage
99.55%
```

The system should highlight ungoverned lifecycle edges.

This turns the event graph into a control-audit surface.

---

# 8. Headline Novelty #6 — Time-Versioned Financial Controls

Financial truth changes over time.

Controls must have effective dates.

Example:

```text
Contract v1
1 Jan – 31 Aug
Domestic Visa MDR = 1.55%

Contract v2
Effective 1 Sep
Domestic Visa MDR = 1.65%
```

A transaction on 30 Aug must use 1.55%.

A transaction on 1 Sep must use 1.65%.

---

# 9. Temporal Replay / What-If Verification

The user should be able to replay historical data under another control version.

Example:

```text
WHAT-IF REPLAY

500 August transactions

Illustrative P2 replay output, not seeded manifest values:

Old contract expected fees
₹7,75,000

New contract expected fees
₹8,25,000

Difference
₹50,000
```

Use cases:
- pricing amendment impact
- fee schedule change
- what-if scenario
- historical policy audit

This is a strong demo feature if time permits.

---

# 10. Headline Novelty #7 — Violation Lineage

Do not treat every downstream failure as an independent problem.

Example:

One incorrect MDR rate causes:

```text
MDR violation
    ↓
GST violation
    ↓
Expected settlement mismatch
    ↓
Expected bank credit mismatch
```

A naive system shows four independent failures per transaction.

sl3dge should identify the upstream primary violation.

Example:

```text
131 LINEAGE NODES

collapsed into

1 SYSTEMIC ROOT CAUSE
56 primary violations
75 downstream effects
```

This feature should be called:

# Violation Lineage

Each downstream violation stores:
- parent violation
- root violation
- causal relationship
- evidence

---

# 11. Counterfactual Settlement Reconstruction

For every provable violation, reconstruct the expected cash movement.

Example:

```text
ACTUAL

Gross                    ₹10,000
MDR                        -₹175
GST                      -₹31.50
Refund                     ₹0.00
────────────────────────────────
Settlement              ₹9,793.50
```

vs:

```text
EXPECTED

Gross                    ₹10,000
MDR                        -₹155
GST                      -₹27.90
Refund                     ₹0.00
────────────────────────────────
Settlement              ₹9,817.10
```

Difference:

```text
₹23.60
```

Breakdown:

```text
₹20.00 excess MDR
₹3.60 excess GST
```

This makes control violations operationally understandable.

---

# 12. Root-Cause Clustering

Group structurally similar violations.

Example:

```text
Domestic Visa
Expected MDR: 1.55%
Observed MDR: 1.75%
First seen: 18 Aug
Affected: 25
Impact: ₹2,042.82
```

Root-cause clustering is not enough by itself.

It becomes stronger when combined with:
- Violation Lineage
- Hypothesis Verification
- Temporal control versions

---

# 13. Honest Unresolved State

This is required.

Example:

```text
UNRESOLVED

Bank credit
₹18,420

Possible matches:
SET_921
SET_924

Insufficient evidence exists
to safely choose one.
```

The system must preserve uncertainty rather than force a match.

Unresolved cases are not failures of the product.

They prove the product has a confidence boundary.

---

# 14. Feature Priority

## P0 — Must Build

- Multi-source ingestion
- Synthetic dataset + ground truth
- Financial Control Compiler
- Approved control model
- Financial Event Graph
- Expected-vs-Actual Verification
- MDR control
- GST control
- Settlement SLA
- Refund integrity
- Settlement arithmetic
- Exception inbox
- Honest unresolved state
- Precision / recall / false-positive rate
- Root-cause clustering
- AI hypothesis generation
- Independent hypothesis verifier
- Financial Mutation Testing
- Mutation Detection Rate
- Control blind-spot reporting

---

## P1 — Strong Differentiation

- Test candidate control before approval
- Control Coverage Graph
- Violation Lineage
- Counterfactual settlement reconstruction
- Time-versioned controls
- Temporal replay

---

## P2 — If Time Permits

- Schema drift
- Automatic control suggestion from blind spots
- What-if fee schedule comparison
- Evidence pack export
- Natural-language finance queries

---

# 15. Features That Must NOT Be Pitched as Novel

Do not headline:

- AI reconciliation
- deterministic matching
- generic exception queues
- AI-generated rules
- contract parsing
- schema mapping
- MDR auditing
- refund auditing
- generic dashboards
- AI summaries
- generic chat

These can exist in the product.

They are supporting capabilities.

---

# 16. Product Novelty Statement

Best concise explanation:

> sl3dge treats financial controls like software: it compiles agreements into executable rules, tests those controls by injecting realistic financial failures, runs them across the complete money lifecycle, and independently verifies AI-generated root-cause hypotheses.

---

# 17. Strongest One-Line Differentiation

> **sl3dge verifies the transactions — and then verifies whether the controls meant to catch bad transactions actually work.**

---

# 18. Demo Features That Truly Distinguish sl3dge

If the video has limited time, show these:

## 1. Apparently reconciled transaction fails
Gateway net equals bank credit, but sl3dge proves a contractual fee violation.

## 2. Contract becomes an executable control
Show exact source clause.

## 3. Financial Mutation Testing
Inject 50 known financial failures and show which controls catch them.

## 4. Blind spot detected
A mutation passes because no control governs it.

## 5. Candidate control tested
AI proposes a new control, then sl3dge proves that coverage improves without adding false positives.

## 6. Violation Lineage
Show one upstream MDR error causing several downstream failures.

## 7. AI hypothesis rejected by verifier
Observed behavior changed; contract did not.

## 8. Unresolved case
Show sl3dge refusing to guess.

These features should define the recorded demo.

---

# 19. Final Product Loop

```text
FINANCIAL AGREEMENT
        ↓
CONTROL COMPILER
        ↓
APPROVED CONTROL SUITE
        ↓
        ├───────────────┐
        ▼               ▼
MUTATION TESTING    REAL FINANCIAL EVENTS
        │               │
        ▼               ▼
CONTROL COVERAGE    EVENT GRAPH
        │               │
        └───────┬───────┘
                ▼
        CONTROL EXECUTION
                │
        ┌───────┴────────┐
        ▼                ▼
       PASS          VIOLATION
                        │
                        ▼
                VIOLATION LINEAGE
                        │
                        ▼
                  ROOT CAUSE
                        │
                        ▼
                 AI HYPOTHESIS
                        │
                        ▼
                    VERIFIER
              ┌─────────┼─────────┐
              ▼         ▼         ▼
            PROVEN   REJECTED  UNRESOLVED
```

This is the version of sl3dge that should guide implementation.

---

# Razorpay Integration Layer — After Core Verification

Razorpay strengthens the real-data demo, but does not become the source of
financial truth. The seeded NovaCart dataset and hidden ground truth remain the
primary evaluation path.

Product flow:

```text
Razorpay read-only APIs
        ↓
bulk deterministic ingestion
        ↓
existing Financial Event Graph
        ↓
approved sl3dge controls
        ↓
expected vs actual verification
```

Data-source options:

```text
NovaCart Demo Dataset
Razorpay Test Account
Upload Files
```

The Razorpay sync UI must report payments, refunds, settlements and
reconciliation records imported, plus last-sync status. The connector is
read-only: it must not capture payments, create refunds, initiate settlements or
perform any other money-moving action.

Implementation order remains:

```text
PAY_82HD9 deterministic slice
→ mutation testing and blind spots
→ violation lineage and hypothesis verifier
→ direct Razorpay reconciliation ingestion
→ optional Razorpay MCP evidence retrieval
→ optional webhooks
```

Razorpay tells sl3dge what happened. The approved merchant agreement tells
sl3dge what should have happened. sl3dge independently compares the two.
