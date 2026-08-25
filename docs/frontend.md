# sl3dge — Frontend Handoff for Codex

## 0. Mission

Build a frontend that makes sl3dge's core distinction visually obvious:

> A settlement can reconcile perfectly and still be financially wrong.

The demo must show the product doing real work. Avoid screens that depend on narration such as generic "AI insights", vague health scores, or chat-first interfaces.

The UI should make these things directly inspectable:

- source contract clause
- executable control
- expected value
- actual value
- calculation
- transaction lifecycle
- violated control
- root cause
- AI hypothesis
- verification result
- precision/recall
- unresolved cases

---

# 1. Frontend Stack

Use:

- Next.js 15+ App Router
- TypeScript
- Tailwind CSS
- shadcn/ui
- TanStack Query
- React Hook Form where useful
- Zod
- Recharts for metrics
- React Flow for the financial event graph
- Lucide icons

Do not add a global state library unless genuinely needed.

Server state belongs in TanStack Query.
Local interaction state stays component-local.

---

# 2. UX Principle

The product should feel like a **finance control console**, not an AI chatbot.

Default tone:
- precise
- auditable
- evidence-first
- restrained
- high information density

Avoid:
- giant gradients
- excessive glassmorphism
- meaningless AI sparkle effects
- "Finance health: 87/100"
- animated fake terminal output
- generic copilot drawer as the primary interaction

---

# 3. Demo-First Navigation

Recommended sidebar:

```text
sl3dge

Overview
Control Runs
Controls
Exceptions
Root Causes
Agreements
Data Sources
```

Optional P2:
```text
Drift
```

For the video, the core path should be:

```text
Agreement
   ↓
Controls
   ↓
Run
   ↓
Results
   ↓
Transaction Inspector
   ↓
Trace Money
   ↓
Root Cause
   ↓
Verify Hypothesis
   ↓
Unresolved Case
```

---

# 4. Route Structure

```text
/
 /runs
 /runs/[runId]
 /runs/[runId]/payments/[paymentId]
 /controls
 /controls/[controlId]
 /agreements
 /agreements/[agreementId]
 /exceptions
 /exceptions/[violationId]
 /root-causes
 /root-causes/[rootCauseId]
 /data
 /drift                  # P2
```

---

# 5. Global Shell

Desktop-first for hackathon demo.

Layout:

```text
┌──────────────┬────────────────────────────────────────┐
│ Sidebar      │ Top bar                                │
│              ├────────────────────────────────────────┤
│              │ Main content                           │
│              │                                        │
│              │                                        │
└──────────────┴────────────────────────────────────────┘
```

Top bar:
- current merchant
- current run selector
- demo dataset shortcut
- optional run status indicator

No wallet/login UI.

---

# 6. Screen: Overview

Purpose:
Give an immediate proof-oriented summary.

Cards:

```text
Latest Run
500 transactions

Controls Evaluated
1,215

Verified Leakage
₹12,638.40

Unresolved
3
```

Below:

## Root Cause Impact chart

Bar chart:
- MDR rate deviation
- duplicate refund deductions
- unsupported fees
- incorrect GST

## Recent violations table

Columns:
- Transaction
- Control
- Expected
- Actual
- Impact
- Confidence
- Status

Keep the table clickable.

---

# 7. Screen: Agreements

## Agreements list

Show:
- name
- effective date
- extracted controls
- status

Demo CTA:

```text
Import Agreement
```

For recorded demo, support a one-click seeded file:
```text
Load NovaCart Merchant Agreement
```

---

# 8. Screen: Agreement Import / Extraction

This is a major demo screen.

Layout:

```text
┌────────────────────────────┬────────────────────────────┐
│ Agreement document         │ Extracted controls         │
│                            │                            │
│ highlighted clause         │ Domestic Card MDR          │
│                            │ 1.55%                      │
│                            │ Source: Clause 4.2          │
│                            │ Confidence: 97%             │
└────────────────────────────┴────────────────────────────┘
```

Control proposal card:

```text
Domestic Card MDR
1.55%

Applies to:
Card / Domestic

Source:
Page 4 · Clause 4.2

Confidence:
97%

[Approve] [Edit] [Reject]
```

When selecting a control proposal:
- highlight its source clause
- show structured parameters
- show effective date

The user should be able to see provenance immediately.

---

# 9. Screen: Controls Library

Table/cards for approved controls.

Columns:

```text
Control
Type
Expected
Scope
Effective
Source
Status
```

Examples:

```text
Domestic Card MDR        MDR_RATE            1.55%
International Card MDR   MDR_RATE            2.90%
GST on Processing Fee    GST_ON_FEE          18%
Standard Settlement      SETTLEMENT_SLA      T+2
Refund Processing Fee    REFUND_INTEGRITY    ₹0
```

Clicking a row opens details.

---

# 10. Screen: Control Detail

Show:

```text
Domestic Card MDR

Status
APPROVED

Expected
1.55%

Applies when
payment_method = card
card_scope = domestic

Source
NovaCart Merchant Agreement
Page 4, Clause 4.2
```

Below:
- source clause
- recent pass/fail counts
- affected transactions
- effective period

Do not expose raw JSON by default, but optionally include a developer/debug accordion.

---

# 11. Screen: New Control Run

This must be fast in the demo.

Two paths:

## Demo path

Big button:

```text
Load Demo Dataset
```

Then show:

```text
500 Payments
500 Orders
84 Settlements
84 Bank Credits
47 Refunds
6 Chargebacks
```

CTA:

```text
Run 1,215 Controls
```

## Manual path

Upload:
- orders.csv
- payments.csv
- settlements.csv
- bank.csv
- refunds.csv
- chargebacks.csv

Show validation results before run.

---

# 12. Screen: Run Progress

Do not fake a long loading screen.

Use real stage updates:

```text
✓ Sources normalized
✓ 1,221 events created
✓ 1,170 relationships linked
✓ 1,215 controls evaluated
✓ Root causes generated
```

Show actual elapsed time.

If the deterministic run is very fast, a compact progress status is enough.

---

# 13. Screen: Run Results

This is the primary dashboard.

Hero metrics:

```text
500
Transactions

1,215
Controls Evaluated

98.9%
Precision

96.7%
Violation Recall

₹12,638.40
Verified Leakage

3
Unresolved
```

Secondary:

```text
PASS          1,173
VIOLATION        31
WARNING           8
UNRESOLVED        3
```

Show throughput:

```text
4.8 sec
253 evaluations/sec
```

---

# 14. Results: Root Cause Section

Table:

```text
Root Cause                    Affected   Impact
Domestic Visa MDR deviation       23     ₹8,421.70
Duplicate refund deductions        2     ₹2,000.00
Unsupported fees                   4     ₹1,748.00
Incorrect GST                      2       ₹468.70
```

Click opens root cause detail.

---

# 15. Results: Exceptions Table

Columns:

```text
Transaction
Category
Control
Expected
Actual
Difference
Impact
Confidence
Status
```

Filters:
- category
- impact range
- control type
- status
- confidence

Default sort:
highest verified impact first.

---

# 16. Screen: Transaction Inspector

This is one of the most important demo screens.

Header:

```text
PAY_82HD9
Domestic Visa · ₹10,000
```

Status badge:

```text
CONTROL VIOLATION
```

Main expected-vs-actual table:

```text
                    Expected        Actual        Status

Gross               ₹10,000.00      ₹10,000.00    ✓
MDR                 ₹155.00         ₹175.00       ✕
GST                  ₹27.90          ₹31.50       ✕
Refunds               ₹0.00           ₹0.00        ✓
Net                ₹9,817.10       ₹9,793.50      ✕
Bank Credit        ₹9,817.10       ₹9,793.50      ✕
```

Hero callout:

```text
Verified Leakage
₹23.60
```

---

# 17. Transaction Inspector: Why This Failed

Show a compact proof panel:

```text
Control
Domestic Card MDR

Expected
₹10,000 × 1.55% = ₹155.00

Actual
₹175.00

Difference
₹20.00

Source
Merchant Agreement · Page 4 · Clause 4.2
```

Separate GST proof:

```text
Expected GST
₹155 × 18% = ₹27.90

Actual GST
₹31.50

Excess GST
₹3.60
```

This should be understandable without AI prose.

---

# 18. Transaction Inspector: Critical Demo Comparison

Include a small banner/card:

```text
Traditional Reconciliation

Gateway net      ₹9,793.50
Bank credit      ₹9,793.50

MATCH ✓
```

Next to:

```text
sl3dge Control Verification

Expected net     ₹9,817.10
Actual net       ₹9,793.50

VIOLATION ✕
```

This directly communicates the moat.

---

# 19. Screen / Panel: Trace Money

Use React Flow.

Example nodes:

```text
ORDER
₹10,000
   ↓
PAYMENT
₹10,000
   ├────────► FEE
   │          Expected ₹155
   │          Actual ₹175
   │          VIOLATION
   │
   ├────────► GST
   │          Expected ₹27.90
   │          Actual ₹31.50
   │          VIOLATION
   │
   ▼
SETTLEMENT
₹9,793.50
   ↓
BANK CREDIT
₹9,793.50
```

Requirements:
- click nodes to inspect evidence
- violating edges/nodes visually differentiated
- avoid dense graph complexity
- fit a single transaction lifecycle on screen

Need a second demo graph for duplicate refund:

```text
REFUND_91
   ├──► SET_51 deduction ₹1,000
   └──► SET_59 deduction ₹1,000  VIOLATION
```

---

# 20. Screen: Exception Detail

Show:

```text
VIOLATION #V-1092

Category
MDR Rate Deviation

Transaction
PAY_82HD9

Verified Impact
₹23.60

Confidence
100%
```

Sections:
- expected
- actual
- calculation
- evidence
- source control
- source rows
- review state

Human actions:

```text
[Confirm] [Reject] [Keep Open]
```

Optional note.

---

# 21. Screen: Root Cause Detail

Critical demo screen.

Header:

```text
Domestic Visa MDR Deviation

23 affected transactions
₹8,421.70 verified impact
```

Show:

```text
Expected MDR
1.55%

Observed MDR
1.75%

First Seen
18 Aug 2026 · 14:03

Affected Segment
Visa · Domestic
```

Chart:
observed MDR rate over time

A simple line/step chart should show:
- 1.55%
- sudden 1.75% after Aug 18

Unaffected comparison:
- Mastercard domestic still at 1.55%
or
- international unchanged

---

# 22. Root Cause: AI Hypothesis

Card:

```text
AI Hypothesis

"Domestic Visa MDR may have changed
from 1.55% to 1.75% on 18 August."

[Verify Hypothesis]
```

Do not present as fact.

Label clearly:

```text
UNVERIFIED
```

---

# 23. Root Cause: Hypothesis Verification

After clicking:

```text
Agreement
1.55% ✓

Approved Amendments
No rate change found

Historical Behaviour
1.55%

Observed Behaviour
1.75%

Affected Transactions
37 / 37 reproduce deviation
```

Final state:

```text
HYPOTHESIS REJECTED

Observed behaviour changed.
Contractual expectation did not.

Classification:
Potential systemic overcharge
```

This interaction should be highly visible and demo-friendly.

---

# 24. Screen: Unresolved Case

Need at least one intentionally unresolved case.

Example:

```text
UNRESOLVED

Bank credit
₹18,420

Possible settlement matches
SET_921 · ₹18,420
SET_924 · ₹18,420

Timing difference
2 min

Unique reference
Unavailable
```

Message:

```text
sl3dge cannot safely determine
the correct settlement relationship.
```

Actions:

```text
[Link SET_921]
[Link SET_924]
[Keep Unresolved]
```

This is important for the challenge's "honest exception list" requirement.

---

# 25. Screen: Data Sources

Show ingestion status:

```text
Orders       500 rows   Healthy
Payments     500 rows   Healthy
Settlements   84 rows   Healthy
Bank          84 rows   Healthy
Refunds       47 rows   Healthy
Chargebacks    6 rows   Healthy
```

P2:
show schema versions / drift indicators.

---

# 26. Screen: Schema Drift — P2

Use only if backend is ready.

Show:

```text
SOURCE DRIFT DETECTED

Old                    New                  Confidence

payment_id      →      txn_reference        99.8%
settlement_id   →      settlement_ref       100%
fee             →      processing_charge    99.4%
tax             →      gst                  100%
```

CTA:

```text
Verify Mapping
```

Backtest:

```text
200 historical records
0 identifier collisions
0 broken relations
0 amount inconsistencies

PASS
```

---

# 27. Empty / Error States

Important.

## No run
```text
No control run yet.
Load the demo dataset or upload source files.
```

## API unavailable
Show a clear retry action.

## LLM unavailable
Core app should still work.
Display:
```text
AI explanation unavailable.
Deterministic control results are unaffected.
```

## Ingestion error
Show row count and exact missing columns.

---

# 28. API Client

Create one typed API layer.

Suggested:

```text
src/lib/api/
  client.ts
  runs.ts
  controls.ts
  agreements.ts
  violations.ts
  rootCauses.ts
  drift.ts
```

Do not scatter `fetch()` calls throughout components.

---

# 29. Type Strategy

Prefer generating or manually mirroring Pydantic schemas.

Core types:

```ts
ControlRun
RunSummary
Control
Agreement
FinancialEvent
EventEdge
ExpectedActualRow
Violation
RootCause
HypothesisVerification
EvaluationMetrics
```

Use Zod for responses where helpful.

---

# 30. Query Keys

Example:

```ts
['runs']
['run', runId]
['run-summary', runId]
['violations', runId, filters]
['payment', runId, paymentId]
['payment-graph', runId, paymentId]
['root-causes', runId]
['root-cause', rootCauseId]
['controls']
['agreements']
```

---

# 31. Component Structure

Suggested:

```text
src/
├── app/
├── components/
│   ├── layout/
│   ├── metrics/
│   ├── runs/
│   ├── controls/
│   ├── agreements/
│   ├── violations/
│   ├── root-causes/
│   ├── graph/
│   └── shared/
├── lib/
│   ├── api/
│   ├── format/
│   └── utils/
└── types/
```

---

# 32. High-Value Components

Build these carefully:

```text
MetricCard
RunStatusBreakdown
ViolationsTable
ExpectedActualTable
EvidencePanel
ControlSourcePanel
FinancialEventGraph
RootCauseSummary
HypothesisCard
VerificationResult
UnresolvedMatchCard
```

---

# 33. Formatting Rules

Money:
- Indian grouping where possible
- 2 decimal places for calculations
- preserve exact decimals from backend

Rates:
```text
1.55%
```

Dates:
```text
18 Aug 2026 · 14:03
```

Confidence:
Prefer:
```text
100%
97%
```

Avoid displaying 0.9738.

---

# 34. Accessibility

Minimum:
- keyboard-focusable controls
- meaningful button labels
- status not indicated by color alone
- table headers
- graph has textual alternative / event list
- dialog focus management
- loading states announced where appropriate

---

# 35. Responsive Scope

Desktop is P0 because the demo is desktop-recorded.

Still support:
- tablet reasonably
- mobile can stack panels

Do not spend disproportionate time perfecting mobile before the demo flow is complete.

---

# 36. Demo Seed UX

Add a deterministic demo button:

```text
Load NovaCart Demo
```

This should:
1. create/load seeded run
2. ensure the known demo records exist
3. make video recording repeatable

Known demo entities should include stable IDs, e.g.:

```text
PAY_82HD9    hidden MDR overcharge
REF_91       duplicate refund
SET_1042     SLA delay
RC_MDR_01    systemic MDR root cause
UNR_003      ambiguous unresolved case
```

Coordinate exact IDs with backend.

---

# 37. Demo Recording Flow

The UI must support this exact sequence with minimal clicking.

## 1. Agreement
Load synthetic merchant agreement.

## 2. Extract controls
Show 1.55% MDR + clause provenance.

## 3. Load demo data
Show 500 payments / 1,200+ events.

## 4. Run controls
Show real execution.

## 5. Results
Show precision, recall, leakage, unresolved.

## 6. Open hidden overcharge
Show bank and gateway matching but sl3dge failing it.

## 7. Expected vs actual
Show ₹23.60 leakage.

## 8. Trace money
Show graph.

## 9. Root cause
Show 23 similar violations.

## 10. Generate hypothesis
Show AI proposes rate change.

## 11. Verify hypothesis
Show contract rejects policy-change hypothesis.

## 12. Duplicate refund or SLA
Show a second control category.

## 13. Unresolved
Show safe refusal.

## 14. Return to scorecard
Finish with metrics.

---

# 38. Definition of Done — Frontend MVP

Frontend is demo-ready when:

- agreement import/extraction screen works
- clause provenance is visible
- control library works
- demo dataset can be loaded
- run execution can be triggered
- run summary renders real backend metrics
- violation table works
- hidden MDR overcharge inspector works
- traditional match vs sl3dge violation comparison is visible
- expected-vs-actual table is clear
- transaction event graph renders
- root-cause page renders
- hypothesis can be generated
- verification result can be shown
- second violation type can be inspected
- unresolved case is visible
- no core demo feature depends on placeholder data
- no core flow requires a generic chat interface

---

# 39. Explicit Non-Goals

Do not build:
- wallet connect
- blockchain screens
- generic AI chatbot
- dark/light theme switch unless trivial
- huge settings area
- user management
- billing
- marketplace
- mobile-first redesign
- decorative landing-page work before the app demo is solid

Focus on observable financial verification.


---

# Novelty Extension — Frontend Screens

These screens are core to the differentiated sl3dge demo. See `features.md`.

## Financial Mutation Testing — P0

Route:

```text
/runs/[runId]/mutation-test
```

Primary CTA:

```text
Test My Controls
```

Results must visibly show:

```text
50 mutations injected
47 detected
3 missed
Mutation Detection Rate: 94%
False Positives: 1
```

Coverage table example:

```text
MDR                       100%
GST                       100%
Refund Integrity           90%
Settlement Lifecycle       92%
Unsupported Fees           60%
```

A missed mutation must be clickable.

## Control Blind Spot — P0

Example detail:

```text
CONTROL BLIND SPOT

Injected fault:
Unexpected platform fee ₹49

Detected:
No

Why:
No approved control governs miscellaneous settlement fees.
```

CTA:

```text
Find Rule in Agreement
```

If AI finds supporting language, show a candidate control with clause provenance.

## Candidate Control Backtest — P1

Show before/after quality, not AI prose.

```text
BEFORE
47 / 50 mutations detected
1 false positive

AFTER CANDIDATE CONTROL
50 / 50 mutations detected
1 false positive
```

Show deltas:

```text
Detection Coverage +6%
False Positives No change
```

Actions:

```text
[Approve Control] [Reject]
```

Never display a candidate as active before explicit approval.

## Control Coverage Graph — P1

Route:

```text
/runs/[runId]/coverage
```

Overlay governance on the financial event graph.

Example:

```text
PAYMENT
  │ MDR_RATE ✓
  │ GST_ON_FEE ✓
  ▼
SETTLEMENT
  │ SETTLEMENT_ARITHMETIC ✓
  │ SETTLEMENT_SLA ✓
  ▼
BANK

CHARGEBACK
  │ NO ACTIVE CONTROL ⚠
  ▼
SETTLEMENT
```

Metrics:

```text
1,248 monetary relationships
1,181 governed
67 ungoverned
Coverage 94.6%
```

Ungoverned edges are clickable.

## Violation Lineage — P1

Violation and root-cause pages must distinguish primary failure from downstream symptoms.

```text
PRIMARY
MDR rate violation
1.55% → 1.75%
  ↓
DOWNSTREAM
GST difference
  ↓
DOWNSTREAM
Expected settlement difference
  ↓
DOWNSTREAM
Expected bank-credit difference
```

Summary:

```text
92 control failures
23 primary violations
69 downstream effects
```

## Counterfactual Settlement — P1

Add a `Counterfactual` tab to Transaction Inspector.

```text
                    Actual        Correct
Gross               ₹100,000      ₹100,000
MDR                 -₹1,750       -₹1,550
GST                   -₹315         -₹279
Refund              -₹5,000       -₹5,000
──────────────────────────────────────────
Settlement           ₹92,935       ₹93,171
```

Hero callout:

```text
Correct settlement should have been ₹93,171
Difference ₹236
```

Drivers:

```text
₹200 excess MDR
₹36 excess GST
```

## Time-Versioned Controls — P1

Control detail must show versions and effective periods.

```text
v1  1.55%  1 Jan – 31 Aug
v2  1.65%  Effective 1 Sep
```

Transaction inspector must show which version was applied and why.

## Temporal Replay — P1/P2

Route:

```text
/runs/[runId]/replay
```

Example UI:

```text
Replay August using:
[Original contract]
[September contract]
[Custom control set]
```

Results:

```text
Old expected fees ₹7,75,000
New expected fees ₹8,25,000
Difference ₹50,000
```

## Updated Recorded Demo Flow

```text
1. Load NovaCart agreement
2. Show clause → approved MDR control
3. Load 500-payment dataset
4. Run controls
5. Show gateway-bank match that still fails sl3dge
6. Expected vs Actual
7. Counterfactual Settlement
8. Trace Money
9. Violation Lineage
10. Systemic root cause
11. AI hypothesis
12. Independent verification rejects unsupported policy change
13. Test My Controls
14. Run 50 mutations
15. Show 47 detected / 3 missed
16. Open blind spot
17. AI proposes candidate control from agreement
18. Backtest candidate control
19. Show coverage improves without extra false positives
20. Explicitly approve candidate control
21. Show unresolved case
22. Finish on measurable scorecard
```

## New High-Value Components

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

## Additional Frontend Definition of Done

- mutation testing is a real backend-driven screen
- missed mutations can be inspected
- blind spots are visible
- candidate-control backtest shows before/after metrics
- candidate activation requires explicit approval
- violation lineage renders primary vs downstream effects
- counterfactual settlement renders actual vs correct cash flows
- control coverage can expose an ungoverned edge
- time-versioned controls are visible
