# sl3dge — Razorpay Judge Demo Script

## The one-line thesis

> Reconciliation asks whether systems agree. sl3dge independently calculates what should have happened under the merchant agreement, proves every exception from source evidence, and tests whether its own controls can catch realistic failures.

This is the story to repeat. The moat is not the dashboard or an LLM. It is the closed verification loop:

**source evidence → contract clauses → effective-dated controls → financial event graph → expected-versus-actual proof → causal lineage → mutation-tested blind spots → backtest → human approval**

## Non-negotiable demo setup

Use only this uploaded run:

- Selector label: `Uploaded CSV control run · 29 Aug 2026 08:53 UTC · CSV UPLOAD`
- Run ID: `RUN_CSV_089856EBA10302D36ADC`
- Status: `COMPLETE`

Never click `Open guided demo`. Do not select `NovaCart · August 2026 control run · DEMO`.

This is an uploaded synthetic, production-like test bundle—not live Razorpay merchant data. Say “the August 29 uploaded CSV bundle,” not “real production transactions.”

Before judges arrive, sign in, select the August 29 CSV run, and start at `http://localhost:3000/data`. Replay and Operations are both reachable from the Overview `Next action` panel, so the complete prototype can be shown without pre-opened deep links.

Do not pre-open Mutation testing: in the current app mode, opening that screen automatically starts an isolated suite.

Avoid these state-changing actions in the core pitch:

- `Open guided demo`
- `Export evidence pack`
- `Verify evidence`, `Escalate`, or `Resolve`
- `Approve control`
- agreement upload, extraction, or clause creation

`Run mutation suite`, `Backtest candidate`, and temporal replay are safe computations over derived/read-only data. They do not modify the canonical run. Stop before `Approve control`.

## The 7-minute live pitch

### 0:00–0:35 — Data Sources: establish trust before intelligence

**Screen:** Data sources  
**Click:** `Workspace` → `Data sources`  
**Click:** the `Control run` dropdown and confirm `Uploaded CSV control run · 29 Aug 2026 08:53 UTC · CSV UPLOAD` is selected.

**Say:**

> Finance teams do not start with one clean ledger. They start with payments, refunds, settlements, chargebacks, orders, and bank records that can agree with each other and still be contractually wrong. This is the six-file CSV bundle uploaded on August 29—not our guided demo dataset. sl3dge classifies every source before execution, stores immutable content hashes, and ingests read-only.

Point to `Read-only ingestion`, `Source classification before execution`, `Razorpay account`, and `Upload source files`.

**Technical line:**

> The production Razorpay path is backend-only and GET-only. The browser never receives credentials and this workspace cannot create, refund, or settle payments. This environment is not connected, so today I am using the uploaded CSV path through the same canonical evidence pipeline.

Do not dwell on the `SETUP REQUIRED` connector badge. Transparency is stronger than pretending it is connected.

### 0:35–1:25 — Overview: quantify value without inflating certainty

**Click:** `Monitor` → `Overview`.

**Say:**

> From 750 transactions, sl3dge built 1,764 financial events and executed 2,888 deterministic control evaluations in 1.03 seconds—2,795 evaluations per second. It found ₹23,663.17 of engine-attributed verified leakage and separately identified ₹32.28 lakh delayed beyond settlement SLA.

Point to:

- `₹23,663.17 Verified exposure`
- `693 Control violations`
- `3 Unresolved evaluations`
- `₹32,28,141 Cash delayed beyond SLA`
- `2,192 Passed`
- `693 Violation`
- `3 Unresolved`
- `95.6% Structural coverage`

**Say:**

> Those two money figures are deliberately separate. Proven excess deductions count as leakage; delayed cash is an operational exposure, not fabricated loss. And ambiguous evidence stays unresolved rather than being forced into a green dashboard.

**Moat line:**

> Most tools tell you that two exports reconcile. sl3dge calculates an independent contractual expectation and proves where observed behavior diverges.

### 1:25–2:20 — Payment Proof: show one transaction all the way down

**Click:** `Open payment proof` in the Overview `Next action` panel. This opens `PAY_CLAUSE_000174`, the highest-impact payment-scoped finding.

**Say:**

> Here is the difference between reconciliation and verification. This is a ₹12,499 domestic Mastercard payment. The gateway net and our expected net both show ₹7,256.05, so a traditional comparison appears consistent. But the contract says refund principal may be deducted only once. sl3dge proves a duplicate ₹4,999.60 refund deduction.

Point to:

- `Traditional reconciliation` → `UNRESOLVED`
- `Control verification` → `VIOLATION`
- MDR `₹206.23` → `PASS`
- GST `₹37.12` → `PASS`
- Refunds → `VIOLATION`
- Bank credit → `UNRESOLVED`

Scroll to `Violation lineage`.

**Say:**

> The duplicate refund is primary. The settlement arithmetic deviation is downstream and explicitly contributes zero additional verified leakage. That dependency graph prevents one root mistake from being counted twice.

Scroll to `Control evidence` and `Money trace`.

**Say:**

> Every verdict carries the formula, control version, clause and page, immutable evaluation ID, and lifecycle nodes from order to payment, fee, tax, refund, settlement, and bank. When the bank match is ambiguous, no EventEdge is created. The system refuses to invent certainty.

### 2:20–3:05 — Exceptions: turn hundreds of findings into seven actions

**Click:** `Monitor` → `Overview`.  
**Click:** `Review 693 exceptions`.  
**Click:** the case `Duplicate refund deductions`.

**Say:**

> We do not hand an operator 693 disconnected alerts. Deterministic causal grouping converts them into seven actionable cases. This highest-impact case represents ₹11,369.30 across 14 verified evidence records.

Point to:

- `7 All cases`
- status filters: `OPEN`, `VERIFIED`, `ESCALATED`, `RESOLVED`
- `₹11,369.30 Verified impact`
- `14/14 verified`
- `Audit trail`
- the two `Unresolved matches`

**Say:**

> Status changes are evidence-versioned and appended to the audit trail. The two ambiguous ₹15,210.64 settlements show the safety posture: three plausible bank records exist, so sl3dge stores “No EventEdge was created.”

Do not click `Verify evidence` during the core demo; it changes the persisted case state.

### 3:05–3:45 — Root Cause: separate cause from symptom

**Click:** `PAY_CLAUSE_000050 · open root cause`.

**Say:**

> This is the systemic cause, not just one bad row: seven primary duplicate-refund violations caused seven downstream settlement effects, with ₹11,369.30 counted once.

Point to:

- `DETERMINISTICALLY VERIFIED`
- `14 Affected payments`
- `7 Primary violations`
- `7 Downstream effects`

Point to `Start investigation`, but do not depend on it for the main pitch.

**Say:**

> AI is bounded here. It can collect evidence and propose hypotheses, but it cannot edit controls or financial truth. The execution trace is logged, hypotheses remain visually separate, and deterministic verification decides the verdict.

If judges specifically ask for the agent workflow, click `Start investigation` and narrate the trace while it runs. The deterministic fallback remains authoritative if the model provider is unavailable.

### 3:45–4:50 — Coverage and Mutation Testing: the moat moment

**Click:** `Monitor` → `Overview`.  
**Click:** `95.6% Structural coverage`.

**Say:**

> Coverage is measured over financial relationships, not a checklist of rule names. This run contains 2,351 material edges. 2,247 are governed, 104 are partially governed, and none are wholly ungoverned, producing 95.58% structural coverage.

Point to the five relationship families, especially:

- `SETTLEMENT → BANK` → `72/72 GOVERNED`
- `REFUND → SETTLEMENT` → `75/75 GOVERNED`
- the two `Mutation-derived capability gaps`

**Click:** `Open mutation testing`.

While it runs, say:

> Now sl3dge tests the tester. It injects isolated faults into a deep copy and verifies that canonical data remains unchanged.

When complete, point to:

- `50 Injected`
- `47 Detected`
- `3 Missed`
- `94% Detection rate`
- `0 False positives`
- `Canonical dataset unchanged`

**Say:**

> This is a better trust signal than claiming perfection. The suite exposes two unsupported-fee misses and one silent payment-method reclassification.

If the `Unlisted Settlement Fee` candidate is visible, **click:** `Backtest candidate`.

**Say:**

> The candidate is grounded in a contract clause, then tested before activation. It improves detection from 47 of 50 to 49 of 50—four percentage points—with zero false-positive delta. We stop before approval because policy activation is a human governance decision.

Do not click `Approve control`.

### 4:50–5:40 — Agreements: show where controls come from

**Click:** `Governance` → `Agreements`.  
**Select if needed:** `new agreement · novacart` in `Active agreement`.

This is the uploaded PDF extraction record. Do not switch to `Merchant Services Agreement · 2026`, which is the seeded reference record.

**Say:**

> A verifier is only defensible if every rule has authority. This uploaded test agreement was PDF-extracted into 40 page-addressable clauses and nine typed control proposals. Source text, proposal, deterministic verification, backtest, and approval remain separate objects.

Point to:

- `Source` → `PDF_TEXT_EXTRACTION`
- `Clauses indexed` → `40`
- `Content fingerprint`
- Clause `4.6 Unlisted Settlement Fees`
- `Structured control proposals`
- typed `Parameters`, `Applicability`, effective dates, and `DRAFT`

**Say:**

> The compiler does not pretend to understand arbitrary legal prose. It extracts supported numbered financial clauses into typed candidates, preserves page provenance and source offsets, and requires deterministic verification plus human approval.

### 5:40–6:20 — Controls: prove effective-dated governance

**Click:** `Governance` → `Controls`.  
**Click:** `Domestic Card MDR`.

**Say:**

> The registry has seven immutable versions across six logical controls; six versions are approved. This MDR rule is executable, typed, sourced to Clause 4.2, and bounded to domestic captured card payments.

Point to:

- `rate 0.0155`
- `tolerance 0.01`
- applicability conditions
- `Source and approval`
- `Immutable version history`
- v1: `1.55%`, 1 Jan–31 Aug 2026
- v2: `1.65%`, from 1 Sep 2026

**Say:**

> Amendments create versions; they never rewrite history. The evaluator selects the control using the transaction timestamp and records the exact version used.

### 6:20–6:45 — Replay: demonstrate safe financial time travel

**Click:** `Monitor` → `Overview`.  
**Click:** `Replay controls` in the `Next action` panel.  
**Click:** the v1 `Domestic Card MDR` version.

Point to `Replay result`.

**Say:**

> Replay applies one approved version across the historical run without changing canonical events or persisted evaluations. The effective-dated baseline expected fees are ₹65,173.72. Applying v1 everywhere produces ₹63,368.22—a ₹1,805.50 decrease—and lists every changed payment as evidence.

Optional: click v2 to show ₹67,457.12, a ₹2,283.40 increase versus baseline.

### 6:45–7:05 — Operations and close

**Click:** `Monitor` → `Overview`.  
**Click:** `Run operations` in the `Next action` panel.

Point to:

- `Complete`
- `7 of 7 stages`
- `0 Failed stages`
- `1,764 Events created`
- `2,888 Evaluations`
- the persisted stage timings

**Say:**

> The complete durable pipeline is observable stage by stage: validation, canonicalization, immutable snapshots, canonical persistence, control evaluation, outcome persistence, and finalization. It completed all seven stages with zero failures. OIDC protects the UI, FastAPI is the only data boundary, Postgres transactions are tenant-scoped with RLS policies, and secrets remain backend-only.

**Close with:**

> sl3dge is not another reconciliation dashboard and not an LLM wrapper. It is a verification control plane for payment money movement: it knows what should have happened, proves what did happen, refuses unsupported certainty, explains the systemic cause, and continuously tests whether its own controls deserve trust.

## If only five minutes are available

Keep these screens:

1. Data Sources — 25 seconds
2. Overview — 45 seconds
3. Payment Proof — 60 seconds
4. Exceptions + Root Cause — 65 seconds
5. Coverage + Mutation Test + Backtest — 90 seconds
6. Agreement clause + MDR version history — 55 seconds
7. Close — 20 seconds

Move Replay and Operations to judge Q&A.

## The moat, in judge language

### 1. Independent financial truth

Payment, settlement, and bank records can agree and still all encode the same wrong deduction. sl3dge derives expected values from approved contract semantics instead of treating source agreement as correctness.

### 2. Evidence graph with explicit uncertainty

Orders, payments, fees, taxes, refunds, chargebacks, settlements, and bank credits become typed nodes and relationships. Exact identifiers or bounded matching rules create edges; ambiguous candidates remain unresolved.

### 3. Causal lineage without leakage inflation

Control dependencies classify violations as primary or downstream. Downstream settlement symptoms remain visible but do not double-count the originating fee, tax, or refund error.

### 4. Contract-to-control provenance

Typed parameters, applicability, effective windows, clause/page/source offsets, content hashes, verification, approval, and immutable versions stay linked.

### 5. The verifier verifies itself

Mutation tests expose what the current control suite misses. Agreement-grounded candidates are backtested on clean history and mutations before a human can approve them.

### 6. Bounded AI, deterministic authority

AI proposes structured hypotheses and candidates. Deterministic calculations, stored evidence, and human governance decide financial truth and policy activation.

## Technical architecture answer (30 seconds)

> The Next.js frontend performs OIDC sign-in and calls only FastAPI. FastAPI verifies JWT issuer, audience, signature, and roles. Every Postgres transaction receives tenant context, with tenant-scoped keys and RLS policies. Uploads are stored privately and content-hashed; the server rechecks the uploaded bytes before execution to prevent classify-then-swap. CSV canonicalization, matching, Decimal-safe calculations, control evaluation, lineage, and mutation scoring are deterministic. Optional Groq/LangGraph workflows use strict structured output, while the deterministic engine remains authoritative.

## Razorpay integration answer (20 seconds)

> The Razorpay adapter is backend-only, read-only, HTTPS-only, endpoint-allowlisted, bounded in retries and payload size, and rejects redirects. It imports payments, refunds, settlements, and reconciliation records into the same canonical model as CSV. This local environment is not credentialed, so the judge demo uses the August 29 uploaded bundle rather than pretending the connector is live.

## Fast judge Q&A

**“Is this real merchant data?”**  
No. It is a synthetic production-like six-file bundle uploaded on August 29 through the real CSV path. The guided demo run is not used.

**“Why are there 693 violations but only seven cases?”**  
693 is the raw control-finding count. Deterministic causal grouping turns those findings into seven systemic cases. The run has 658 primary and 35 downstream findings; downstream leakage is not counted twice.

**“Why is coverage 95.58% if zero edges are ungoverned?”**  
Because 104 relationships are only partially governed. The denominator is observed material relationships, not a checkbox list of controls.

**“Why not claim 100% accuracy?”**  
This uploaded operational run has no user-supplied ground-truth labels, so the UI intentionally does not score precision or recall. Mutation testing reports 94% detection and openly shows the three misses.

**“What does AI decide?”**  
It does not decide money or approve controls. It proposes bounded hypotheses or typed candidates. Deterministic verification and human approval remain authoritative.

**“What is the business value for Razorpay?”**  
Merchants get evidence-backed assurance over fees, taxes, refunds, settlement arithmetic, settlement timing, and bank receipt. Razorpay gets a scalable, auditable control layer that can reduce dispute investigation time, surface systemic issues early, and make every conclusion reproducible.

**“What is hardest to copy?”**  
Not the UI. The defensible asset is the accumulated contract semantics, typed financial graph, causal control-dependency model, verified mutation corpus, and provenance-rich outcomes across merchants and payment lifecycles.

## Claims to avoid

- Do not say the CSV is live production data.
- Do not say the connector is currently connected.
- Do not call ₹23,663.17 recovered cash; call it verified leakage or engine-attributed verified impact.
- Do not combine ₹23,663.17 leakage with ₹32.28 lakh delayed cash.
- Do not claim 100% accuracy for this run.
- Do not claim the agreement compiler understands arbitrary contracts.
- Do not claim mutation testing is exhaustive fuzzing; it is a curated finite fault suite.
- Do not claim AI discovers root causes; the root grouping and causal lineage are deterministic.
- Do not claim controls visible in the registry were created by the August 29 CSV upload. The registry is tenant-global.

## Final memory aid

If you forget the script, remember five words:

**Calculate. Prove. Explain. Challenge. Govern.**

- Calculate what should have happened.
- Prove what actually happened.
- Explain primary cause versus downstream symptom.
- Challenge the verifier with mutations.
- Govern every change through source, backtest, and human approval.
