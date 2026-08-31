# sl3dge screen-by-screen UX audit

## Designated user and core journey

The primary user is a merchant finance-control operator: someone accountable for finding cash leakage, proving the cause, and moving an exception to resolution without overstating uncertain evidence. Secondary users are control owners and auditors who review agreement provenance, control coverage, and run reproducibility.

The intended journey is:

1. Connect or select a financial-data run.
2. Understand exposure and control health at a glance.
3. Triage the highest-impact exception or root cause.
4. Open transaction-level proof and verify the evidence chain.
5. Resolve or escalate the case.
6. Govern blind spots through coverage, mutation testing, agreements, and versioned controls.

## Cross-product audit

The former interface made most content equally prominent: repeated dark cards, green accents, uppercase micro-labels, pills, and monospace text flattened the hierarchy. It looked technically polished but made an operator work to answer three basic questions: what changed, what matters most, and what should I do next.

The revised system uses a warm evidence canvas, a stable ink navigation rail, restrained semantic color, sentence-case labels, tabular numbers, and fewer—but more purposeful—surfaces. Operational actions, deterministic evidence, and system diagnostics are visually distinct. Merchant names, run identifiers, metrics, recommendations, statuses, and evidence remain API-driven; loading, empty, failure, and permission states do not substitute demo values.

## Screen audit and redesign decisions

| Screen | How the previous experience felt | Revised UX decision | Acceptance signal |
| --- | --- | --- | --- |
| Overview | A wall of equally weighted cards; the demo-specific recommendation undermined trust. | Lead with current run context, exposure, unresolved work, and one dynamic next action. Keep methodology and throughput secondary. | An operator can state exposure, confidence, and the next investigation in under 10 seconds. |
| Data sources | Setup choices competed with credentials, counters, and MCP implementation details. | Make source selection and connector readiness primary; place support diagnostics and optional evidence capabilities in an advanced section. | A first-time user can start the demo, upload data, or identify a connector blocker without reading backend terminology. |
| Controls | Versioned rules looked like another card gallery and were difficult to compare. | Use a scannable control register with status, scope, effective period, source, and a clear detail affordance. | A control owner can find the governing version and its provenance without opening every item. |
| Control detail | Parameters, versions, and source evidence had similar emphasis. | Put current-version identity and status first, then separate version history, typed parameters, and contract provenance. | The effective rule, source clause, and supersession chain are unambiguous. |
| Exceptions | The inbox, selected case, workflow actions, audit trail, and unresolved matches competed for attention. | Treat this as an accountable work queue: filter/select on the left, evidence and status action on the right, unresolved items in a separate queue. | The user always knows which case is selected, its verified impact, available action, and evidence basis. |
| Payment proof | Dense panels obscured the actual proof sequence. | Present expected-versus-actual first, then the counterfactual cash result, then causal lineage and source evidence in reading order. | A reviewer can explain the difference and trace it to its source without inference. |
| Root causes | Ranking, search, impact, and technical context lacked a dominant investigation path. | Lead with the top dynamic cluster and its financial impact; make the remainder a sortable investigation list. | The highest-value systemic issue and affected population are immediately clear. |
| Root-cause detail | Hypothesis generation could appear as authoritative as deterministic verification. | Separate proposed hypothesis, verification state, supporting checks, affected transactions, and case workflow. | AI assistance never visually outranks deterministic proof, and unresolved remains visibly unresolved. |
| Agreements | Upload, manual entry, clauses, proposals, verification, and approval created one very long governance screen. | Use progressive disclosure and explicit governance stages: source record, clauses, proposed controls, backtest, approval. | A reviewer can tell what is source text, what is proposed, and what is approved at every step. |
| Agreement detail | Contract metadata and clause/control relationships were difficult to scan. | Use a contract summary followed by linked clause and approved-control registers. | Provenance from agreement to executable control is one continuous path. |
| Coverage | Runtime edge coverage and mutation-derived blind spots were easy to conflate. | Give each a distinct section and definition, with the dynamic blind spot as the next governance action. | Users do not interpret a capability gap as a runtime count. |
| Mutation testing | The screen over-emphasized the demo story and a fixed candidate control. | Show the test run, detection quality, missed fault types, and a candidate selected from returned evidence/control data. | Results and recommendations remain correct for any run, not only the seeded dataset. |
| Replay | Selecting a historical control version did not clearly communicate the counterfactual. | Frame replay as a comparison: selected approved version, execution state, changed outcomes, and link back to the source run. | The user can tell what was replayed and what changed before acting on it. |
| Operations | Stage timings and diagnostics looked like primary product metrics. | Present run health first, then stage timing and durable execution metadata for support users. | A support user can identify the failing/slow stage; a finance operator is not distracted by internals. |
| Authentication and system states | Sign-in, loading, error, and not-found states felt detached from the product identity. | Apply the same brand, plain-language recovery guidance, keyboard focus, and responsive layout to every state. | Every blocked state explains what happened and offers one safe recovery action. |

## Responsive and accessibility criteria

- Desktop uses grouped navigation and a persistent run context; mobile uses an explicit menu rather than a horizontally scrolling route strip.
- Tables preserve labels and actions at narrow widths through responsive wrapping or controlled horizontal overflow.
- Focus indicators, semantic headings, landmarks, labels, button names, and live loading/error states remain available to keyboard and assistive-technology users.
- Status never depends on color alone, financial values use tabular numerals, and reduced-motion preferences disable nonessential transitions.
- Generated imagery carries meaningful alternative text when informative and an empty alternative when decorative.
