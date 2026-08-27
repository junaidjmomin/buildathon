from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from threading import RLock
from time import perf_counter

from app.controls.engine import evaluate_payment
from app.core.config import get_settings
from app.core.money import money
from app.domain.models import (
    CaseAuditEntry,
    CaseEvidence,
    ConfusionMatrix,
    ControlType,
    CounterfactualDriver,
    CounterfactualSettlement,
    DemoLoadResponse,
    EvaluationStatus,
    Evidence,
    ExceptionCase,
    ExceptionCaseStatus,
    ExpectedActualResponse,
    ExpectedActualRow,
    GraphEdge,
    GraphNode,
    HypothesisResponse,
    HypothesisVerification,
    LineageType,
    PaymentGraph,
    PaymentLifecycle,
    RootCause,
    RunSummary,
    StatusBreakdown,
    UnresolvedMatch,
    Violation,
    ViolationLineageNode,
    ViolationLineageResponse,
)
from app.persistence.database import session_scope
from app.persistence.repository import RunRepository
from app.services.governance import CONTROLS, governance
from app.synthetic.generator import (
    DEMO_SEED,
    KNOWN_PAYMENT_ID,
    KNOWN_REFUND_ID,
    KNOWN_ROOT_CAUSE_ID,
    KNOWN_SETTLEMENT_ID,
    KNOWN_UNRESOLVED_ID,
    SyntheticDataset,
    generate_dataset,
)

DEMO_RUN_ID = "RUN_NOVACART_AUG_2026"


class DemoStore:
    def __init__(self) -> None:
        self._load_lock = RLock()
        self.dataset: SyntheticDataset | None = None
        self.summary: RunSummary | None = None
        self.violations: list[Violation] = []
        self.root_causes: list[RootCause] = []
        self.cases: list[ExceptionCase] = []
        self.persistence_status = "IN_MEMORY"

    def load(self) -> DemoLoadResponse:
        with self._load_lock:
            return self._load_unlocked()

    def _load_unlocked(self) -> DemoLoadResponse:
        started = perf_counter()
        governance.reset()
        self.dataset = generate_dataset(DEMO_SEED)
        self.violations = self._build_violations(self.dataset)
        self.root_causes = self._build_root_causes(self.violations)
        self.cases = self._build_cases()
        self.summary = self._build_summary(self.dataset, started)
        settings = get_settings()
        if settings.database_url:
            with session_scope(tenant_id="novacart_demo") as session:
                persisted_events, persisted_edges = RunRepository(session).replace_demo_run(
                    run_id=DEMO_RUN_ID,
                    dataset=self.dataset,
                    summary=self.summary,
                    violations=self.violations,
                    root_causes=self.root_causes,
                    controls=CONTROLS,
                    tenant_id="novacart_demo",
                )
            if (
                persisted_events != self.summary.event_count
                or persisted_edges != self.summary.relationship_count
            ):
                raise RuntimeError("Persisted canonical graph does not match the seeded manifest")
            self.persistence_status = "POSTGRES"
        else:
            self.persistence_status = "IN_MEMORY"
        return DemoLoadResponse(
            run_id=DEMO_RUN_ID,
            name="NovaCart · August 2026",
            counts=self.dataset.counts,
            known_demo_ids={
                "mdr_violation": KNOWN_PAYMENT_ID,
                "duplicate_refund": KNOWN_REFUND_ID,
                "sla_violation": KNOWN_SETTLEMENT_ID,
                "root_cause": KNOWN_ROOT_CAUSE_ID,
                "unresolved": KNOWN_UNRESOLVED_ID,
            },
            persistence_status=self.persistence_status,
        )

    def ensure_loaded(self) -> None:
        if self.dataset is None:
            with self._load_lock:
                if self.dataset is None:
                    self._load_unlocked()

    def _payment(self, payment_id: str) -> PaymentLifecycle:
        self.ensure_loaded()
        assert self.dataset is not None
        for payment in self.dataset.payments:
            if payment.payment_id == payment_id:
                return payment
        raise KeyError(payment_id)

    def _build_violations(self, dataset: SyntheticDataset) -> list[Violation]:
        violations: list[Violation] = []
        root_ids = {
            "MDR_RATE_DEVIATION": "RC_MDR_01",
            "INCORRECT_GST": "RC_GST_01",
            "DUPLICATE_REFUND": "RC_REFUND_01",
            "SETTLEMENT_SLA": "RC_SLA_01",
            "UNSUPPORTED_FEE": "RC_FEE_01",
        }
        config = {
            "MDR_RATE_DEVIATION": (ControlType.MDR_RATE, "MDR rate deviation"),
            "INCORRECT_GST": (ControlType.GST_ON_FEE, "Incorrect GST"),
            "DUPLICATE_REFUND": (ControlType.REFUND_INTEGRITY, "Duplicate refund deduction"),
            "SETTLEMENT_SLA": (ControlType.SETTLEMENT_SLA, "Settlement SLA breach"),
            "UNSUPPORTED_FEE": (ControlType.UNSUPPORTED_FEE, "Unsupported fee"),
        }
        for payment in dataset.payments:
            scenario = dataset.ground_truth[payment.payment_id]
            if scenario not in config:
                continue
            evaluation = evaluate_payment(payment)
            control_type, category = config[scenario]
            if scenario == "MDR_RATE_DEVIATION":
                expected = "1.55%"
                actual = f"{(payment.actual_fee / payment.amount * 100):.2f}%"
                difference = evaluation.leakage
                impact = evaluation.leakage
            elif scenario == "INCORRECT_GST":
                expected = f"₹{evaluation.expected_tax:.2f}"
                actual = f"₹{payment.actual_tax:.2f}"
                difference = money(payment.actual_tax - evaluation.expected_tax)
                impact = max(difference, Decimal("0"))
            elif scenario == "DUPLICATE_REFUND":
                expected = f"₹{payment.refund_amount:.2f} once"
                actual = f"₹{payment.refund_deduction:.2f} deducted"
                difference = money(payment.refund_deduction - payment.refund_amount)
                impact = difference
            elif scenario == "SETTLEMENT_SLA":
                expected = "T+2 business days"
                actual = f"T+{evaluation.delay_days + 2} business days"
                difference = Decimal("0")
                impact = Decimal("0")
            else:
                expected = "₹0.00"
                actual = f"₹{payment.unsupported_fee:.2f}"
                difference = payment.unsupported_fee
                impact = payment.unsupported_fee
            violations.append(
                Violation(
                    id=f"V_{len(violations) + 1:04d}",
                    payment_id=payment.payment_id,
                    category=category,
                    control_type=control_type,
                    expected=expected,
                    actual=actual,
                    difference=difference,
                    financial_impact=impact,
                    root_cause_id=root_ids[scenario],
                    occurred_at=payment.captured_at,
                )
            )
        return violations

    def _build_root_causes(self, violations: list[Violation]) -> list[RootCause]:
        groups: dict[str, list[Violation]] = defaultdict(list)
        for violation in violations:
            assert violation.root_cause_id is not None
            groups[violation.root_cause_id].append(violation)
        labels = {
            "RC_MDR_01": ("Domestic card MDR deviation", "1.55%", "1.75%"),
            "RC_GST_01": ("GST calculated above contract", "18%", "20%"),
            "RC_REFUND_01": ("Duplicate refund deductions", "1 deduction", "2 deductions"),
            "RC_SLA_01": ("Settlement SLA breaches", "T+2", "T+5"),
            "RC_FEE_01": ("Unsupported platform fees", "₹0", "₹49"),
        }
        roots: list[RootCause] = []
        for root_id, items in groups.items():
            title, expected, observed = labels[root_id]
            roots.append(
                RootCause(
                    id=root_id,
                    title=title,
                    category=items[0].category,
                    affected_count=len(items),
                    verified_impact=money(sum(item.financial_impact for item in items)),
                    expected_value=expected,
                    observed_value=observed,
                    first_seen=min(item.occurred_at for item in items),
                    last_seen=max(item.occurred_at for item in items),
                    primary_violation_count=len(items),
                    downstream_effect_count=(len(items) * 3 if root_id == "RC_MDR_01" else 0),
                )
            )
        return sorted(roots, key=lambda root: root.verified_impact, reverse=True)

    def _build_cases(self) -> list[ExceptionCase]:
        primary = next(
            violation for violation in self.violations if violation.payment_id == KNOWN_PAYMENT_ID
        )
        now = datetime.now(timezone.utc)
        return [
            ExceptionCase(
                id="CASE_PAY_82HD9",
                run_id=DEMO_RUN_ID,
                title="Domestic card MDR overcharge",
                payment_id=KNOWN_PAYMENT_ID,
                primary_violation_id=primary.id,
                violation_ids=[primary.id],
                status=ExceptionCaseStatus.OPEN,
                verified_impact=primary.financial_impact,
                evidence=[
                    CaseEvidence(
                        id="EVIDENCE_AGREEMENT_4_2",
                        kind="APPROVED_CONTROL",
                        title="Approved domestic MDR control",
                        summary=(
                            "Clause 4.2 fixes domestic-card MDR at 1.55% for this capture date."
                        ),
                        source_id="CTRL_MDR_DOMESTIC",
                        verified=True,
                    ),
                    CaseEvidence(
                        id="EVIDENCE_RAZORPAY_ACTUAL",
                        kind="OBSERVED_EVENT",
                        title="Observed fee and tax",
                        summary="Gateway records show ₹175.00 MDR and ₹31.50 GST.",
                        source_id=KNOWN_PAYMENT_ID,
                        verified=True,
                    ),
                    CaseEvidence(
                        id="EVIDENCE_COUNTERFACTUAL",
                        kind="DETERMINISTIC_CALCULATION",
                        title="Counterfactual settlement",
                        summary="Approved controls reconstruct ₹9,817.10 instead of ₹9,793.50.",
                        source_id=f"CF_{KNOWN_PAYMENT_ID}",
                        verified=True,
                    ),
                    CaseEvidence(
                        id="EVIDENCE_LINEAGE",
                        kind="VIOLATION_LINEAGE",
                        title="Primary and downstream lineage",
                        summary=(
                            "Excess MDR is primary; GST, settlement and bank differences "
                            "are downstream."
                        ),
                        source_id=f"LIN_{KNOWN_PAYMENT_ID}_MDR",
                        verified=True,
                    ),
                ],
                audit_trail=[
                    CaseAuditEntry(
                        from_status=None,
                        to_status=ExceptionCaseStatus.OPEN,
                        actor="sl3dge-control-engine",
                        note="Case opened from a deterministic primary violation.",
                        occurred_at=now,
                    )
                ],
                created_at=now,
                updated_at=now,
            )
        ]

    def _build_summary(self, dataset: SyntheticDataset, started: float) -> RunSummary:
        unresolved = sum(1 for value in dataset.ground_truth.values() if value == "UNRESOLVED")
        predicted_ids = {violation.payment_id for violation in self.violations}
        truth_ids = {
            payment_id
            for payment_id, status in dataset.ground_truth.items()
            if status not in {"PASS", "UNRESOLVED"}
        }
        tp = len(predicted_ids & truth_ids)
        fp = len(predicted_ids - truth_ids)
        fn = len(truth_ids - predicted_ids)
        tn = len(dataset.payments) - tp - fp - fn - unresolved
        precision = Decimal(tp) / Decimal(tp + fp) if tp + fp else Decimal("1")
        recall = Decimal(tp) / Decimal(tp + fn) if tp + fn else Decimal("1")
        fpr = Decimal(fp) / Decimal(fp + tn) if fp + tn else Decimal("0")
        processing_ms = max(1, int((perf_counter() - started) * 1000))
        evaluations = len(dataset.payments) * 4 + 18
        delayed = money(
            sum(
                payment.amount
                for payment in dataset.payments
                if dataset.ground_truth[payment.payment_id] == "SETTLEMENT_SLA"
            )
        )
        return RunSummary(
            id=DEMO_RUN_ID,
            name="NovaCart · August 2026 control run",
            status="COMPLETE",
            transaction_count=len(dataset.payments),
            event_count=(
                dataset.counts["orders"]
                + dataset.counts["payments"]
                + dataset.counts["settlements"]
                + dataset.counts["bank_entries"]
                + dataset.counts["refunds"]
                + dataset.counts["chargebacks"]
            ),
            relationship_count=len(dataset.payments) * 3 - unresolved,
            control_evaluation_count=evaluations,
            breakdown=StatusBreakdown(
                passed=len(dataset.payments) - len(truth_ids) - unresolved,
                violation=len(truth_ids),
                warning=0,
                unresolved=unresolved,
            ),
            precision=precision,
            recall=recall,
            false_positive_rate=fpr,
            verified_leakage=money(sum(v.financial_impact for v in self.violations)),
            cash_delayed=delayed,
            unresolved_count=unresolved,
            processing_ms=processing_ms,
            evaluations_per_second=int(evaluations / (processing_ms / 1000)),
            confusion_matrix=ConfusionMatrix(
                true_positive=tp,
                false_positive=fp,
                true_negative=tn,
                false_negative=fn,
            ),
            completed_at=datetime.now(timezone.utc),
        )

    def expected_actual(self, payment_id: str) -> ExpectedActualResponse:
        payment = self._payment(payment_id)
        result = evaluate_payment(payment)
        applied_mdr = governance.effective_control("DOMESTIC_CARD_MDR", payment.captured_at.date())
        refund_status = (
            EvaluationStatus.PASS
            if payment.refund_amount == payment.refund_deduction
            else EvaluationStatus.VIOLATION
        )
        overall = EvaluationStatus.PASS
        statuses = [result.fee_status, result.tax_status, result.net_status, result.bank_status]
        if EvaluationStatus.UNRESOLVED in statuses:
            overall = EvaluationStatus.UNRESOLVED
        elif EvaluationStatus.VIOLATION in statuses:
            overall = EvaluationStatus.VIOLATION
        rows = [
            ExpectedActualRow(
                label="Gross",
                expected=payment.amount,
                actual=payment.amount,
                status=EvaluationStatus.PASS,
                difference=Decimal("0"),
            ),
            ExpectedActualRow(
                label="MDR",
                expected=result.expected_fee,
                actual=payment.actual_fee,
                status=result.fee_status,
                difference=money(payment.actual_fee - result.expected_fee),
            ),
            ExpectedActualRow(
                label="GST",
                expected=result.expected_tax,
                actual=payment.actual_tax,
                status=result.tax_status,
                difference=money(payment.actual_tax - result.expected_tax),
            ),
            ExpectedActualRow(
                label="Refunds",
                expected=result.expected_refund,
                actual=payment.refund_deduction,
                status=refund_status,
                difference=money(payment.refund_deduction - result.expected_refund),
            ),
            ExpectedActualRow(
                label="Net",
                expected=result.expected_net,
                actual=payment.actual_net,
                status=result.net_status,
                difference=money(result.expected_net - payment.actual_net),
            ),
            ExpectedActualRow(
                label="Bank credit",
                expected=result.expected_net,
                actual=payment.bank_credit,
                status=result.bank_status,
                difference=(
                    Decimal("0")
                    if payment.bank_credit is None
                    else money(result.expected_net - payment.bank_credit)
                ),
            ),
        ]
        evidence = [
            Evidence(
                title="Domestic card MDR",
                control=applied_mdr.id,
                calculation=f"₹{payment.amount:.2f} × 1.55% = ₹{result.expected_fee:.2f}",
                expected=result.expected_fee,
                actual=payment.actual_fee,
                difference=money(payment.actual_fee - result.expected_fee),
                source=applied_mdr.source,
                source_clause=applied_mdr.source_clause,
            ),
            Evidence(
                title="GST on valid processing fee",
                control="CTRL_GST_FEE",
                calculation=f"₹{result.expected_fee:.2f} × 18% = ₹{result.expected_tax:.2f}",
                expected=result.expected_tax,
                actual=payment.actual_tax,
                difference=money(payment.actual_tax - result.expected_tax),
                source="NovaCart Merchant Agreement",
                source_clause="Page 4 · Clause 4.3",
            ),
        ]
        return ExpectedActualResponse(
            payment_id=payment.payment_id,
            descriptor=f"{payment.card_scope.title()} {payment.card_network} · card",
            amount=payment.amount,
            status=overall,
            rows=rows,
            verified_leakage=result.leakage,
            gateway_net=payment.actual_net,
            bank_credit=payment.bank_credit,
            expected_net=result.expected_net,
            evidence=evidence,
            applied_control_id=applied_mdr.id,
            applied_control_version=applied_mdr.version,
            applied_control_effective_period=(
                f"{applied_mdr.effective_from.isoformat()} → "
                f"{applied_mdr.effective_to.isoformat() if applied_mdr.effective_to else 'open'}"
            ),
        )

    def graph(self, payment_id: str) -> PaymentGraph:
        payment = self._payment(payment_id)
        result = evaluate_payment(payment)
        nodes = [
            GraphNode(id=payment.order_id, kind="ORDER", label="Order", amount=payment.amount),
            GraphNode(
                id=payment.payment_id, kind="PAYMENT", label="Payment", amount=payment.amount
            ),
            GraphNode(
                id=f"FEE_{payment.payment_id}",
                kind="FEE",
                label="Processing fee",
                amount=payment.actual_fee,
                status=result.fee_status,
                detail=f"Expected ₹{result.expected_fee:.2f}",
            ),
            GraphNode(
                id=f"TAX_{payment.payment_id}",
                kind="TAX",
                label="GST",
                amount=payment.actual_tax,
                status=result.tax_status,
                detail=f"Expected ₹{result.expected_tax:.2f}",
            ),
            GraphNode(
                id=payment.settlement_id,
                kind="SETTLEMENT",
                label="Settlement",
                amount=payment.actual_net,
                status=result.net_status,
            ),
        ]
        edges = [
            GraphEdge(
                id="E1",
                source=payment.order_id,
                target=payment.payment_id,
                relationship="PAID_BY",
                confidence=Decimal("1"),
                method="EXACT",
            ),
            GraphEdge(
                id="E2",
                source=payment.payment_id,
                target=f"FEE_{payment.payment_id}",
                relationship="CHARGED_FEE",
                confidence=Decimal("1"),
                method="RULE",
            ),
            GraphEdge(
                id="E3",
                source=payment.payment_id,
                target=f"TAX_{payment.payment_id}",
                relationship="CHARGED_TAX",
                confidence=Decimal("1"),
                method="RULE",
            ),
            GraphEdge(
                id="E4",
                source=payment.payment_id,
                target=payment.settlement_id,
                relationship="INCLUDED_IN",
                confidence=Decimal("1"),
                method="EXACT",
            ),
        ]
        if payment.bank_txn_id and payment.bank_credit is not None:
            nodes.append(
                GraphNode(
                    id=payment.bank_txn_id,
                    kind="BANK_ENTRY",
                    label="Bank credit",
                    amount=payment.bank_credit,
                    status=result.bank_status,
                )
            )
            edges.append(
                GraphEdge(
                    id="E5",
                    source=payment.settlement_id,
                    target=payment.bank_txn_id,
                    relationship="CREDITED_AS",
                    confidence=Decimal("1"),
                    method="EXACT",
                )
            )
        return PaymentGraph(payment_id=payment_id, nodes=nodes, edges=edges)

    def lineage(self, payment_id: str) -> ViolationLineageResponse:
        payment = self._payment(payment_id)
        result = evaluate_payment(payment)
        nodes: list[ViolationLineageNode] = []
        fee_difference = money(payment.actual_fee - result.expected_fee)
        tax_difference = money(payment.actual_tax - result.expected_tax)
        net_difference = money(result.expected_net - payment.actual_net)
        if fee_difference > 0:
            root_id = f"LIN_{payment_id}_MDR"
            nodes.append(
                ViolationLineageNode(
                    id=root_id,
                    category="MDR rate violation",
                    lineage_type=LineageType.PRIMARY,
                    parent_violation_id=None,
                    root_violation_id=root_id,
                    expected=result.expected_fee,
                    actual=payment.actual_fee,
                    difference=fee_difference,
                    financial_impact=fee_difference,
                    causal_evidence="Actual MDR exceeds the approved 1.55% contractual rate.",
                )
            )
            parent_id = root_id
            if tax_difference > 0:
                tax_id = f"LIN_{payment_id}_GST"
                nodes.append(
                    ViolationLineageNode(
                        id=tax_id,
                        category="GST downstream difference",
                        lineage_type=LineageType.DOWNSTREAM,
                        parent_violation_id=parent_id,
                        root_violation_id=root_id,
                        expected=result.expected_tax,
                        actual=payment.actual_tax,
                        difference=tax_difference,
                        financial_impact=tax_difference,
                        causal_evidence="GST was charged on the overcharged processing fee.",
                    )
                )
                parent_id = tax_id
            settlement_id = f"LIN_{payment_id}_SETTLEMENT"
            nodes.append(
                ViolationLineageNode(
                    id=settlement_id,
                    category="Expected settlement difference",
                    lineage_type=LineageType.DOWNSTREAM,
                    parent_violation_id=parent_id,
                    root_violation_id=root_id,
                    expected=result.expected_net,
                    actual=payment.actual_net,
                    difference=net_difference,
                    financial_impact=Decimal("0"),
                    causal_evidence="Excess MDR and GST reduce the resulting settlement net.",
                )
            )
            if payment.bank_credit is not None:
                nodes.append(
                    ViolationLineageNode(
                        id=f"LIN_{payment_id}_BANK",
                        category="Expected bank-credit difference",
                        lineage_type=LineageType.DOWNSTREAM,
                        parent_violation_id=settlement_id,
                        root_violation_id=root_id,
                        expected=result.expected_net,
                        actual=payment.bank_credit,
                        difference=money(result.expected_net - payment.bank_credit),
                        financial_impact=Decimal("0"),
                        causal_evidence="The bank correctly mirrors the already-wrong settlement.",
                    )
                )
        return ViolationLineageResponse(
            payment_id=payment_id,
            primary_violation_count=sum(node.lineage_type == LineageType.PRIMARY for node in nodes),
            downstream_effect_count=sum(
                node.lineage_type == LineageType.DOWNSTREAM for node in nodes
            ),
            nodes=nodes,
        )

    def counterfactual(self, payment_id: str) -> CounterfactualSettlement:
        payment = self._payment(payment_id)
        result = evaluate_payment(payment)
        drivers: list[CounterfactualDriver] = []
        excess_fee = money(max(payment.actual_fee - result.expected_fee, Decimal("0")))
        excess_tax = money(max(payment.actual_tax - result.expected_tax, Decimal("0")))
        excess_refund = money(max(payment.refund_deduction - result.expected_refund, Decimal("0")))
        if excess_fee:
            drivers.append(CounterfactualDriver(type="EXCESS_MDR", amount=excess_fee))
        if excess_tax:
            drivers.append(CounterfactualDriver(type="EXCESS_GST", amount=excess_tax))
        if excess_refund:
            drivers.append(
                CounterfactualDriver(type="EXCESS_REFUND_DEDUCTION", amount=excess_refund)
            )
        if payment.unsupported_fee:
            drivers.append(
                CounterfactualDriver(type="UNSUPPORTED_FEE", amount=payment.unsupported_fee)
            )
        return CounterfactualSettlement(
            payment_id=payment_id,
            actual={
                "gross": payment.amount,
                "mdr": payment.actual_fee,
                "gst": payment.actual_tax,
                "refunds": payment.refund_deduction,
                "other_fees": payment.unsupported_fee,
                "net": payment.actual_net,
            },
            expected={
                "gross": payment.amount,
                "mdr": result.expected_fee,
                "gst": result.expected_tax,
                "refunds": result.expected_refund,
                "other_fees": Decimal("0"),
                "net": result.expected_net,
            },
            difference=money(result.expected_net - payment.actual_net),
            drivers=drivers,
        )

    def generate_hypothesis(self, root_cause_id: str) -> HypothesisResponse:
        root = self.get_root_cause(root_cause_id)
        hypothesis = (
            "Domestic card MDR may have changed from 1.55% to 1.75% beginning on 18 August 2026."
            if root.id == "RC_MDR_01"
            else f"A common upstream policy change may explain {root.title.lower()}."
        )
        root.hypothesis = hypothesis
        return HypothesisResponse(root_cause_id=root.id, hypothesis=hypothesis, status="UNVERIFIED")

    def verify_hypothesis(self, root_cause_id: str) -> HypothesisVerification:
        root = self.get_root_cause(root_cause_id)
        root.verification_status = "REJECTED"
        checks = [
            {"label": "Approved agreement", "value": "1.55%", "result": "MATCH"},
            {
                "label": "Approved amendments",
                "value": "Next approved change is 1.65% from 1 September",
                "result": "NOT_EFFECTIVE",
            },
            {"label": "Historical behaviour", "value": "1.55%", "result": "MATCH"},
            {"label": "Observed behaviour", "value": root.observed_value, "result": "DEVIATION"},
            {
                "label": "Affected transactions",
                "value": f"{root.affected_count} / {root.affected_count}",
                "result": "REPRODUCED",
            },
        ]
        root.verification_evidence = {"checks": checks}
        return HypothesisVerification(
            root_cause_id=root.id,
            status="REJECTED",
            classification="POTENTIAL_SYSTEMIC_OVERCHARGE",
            checks=checks,
            conclusion="Observed behaviour changed. Contractual expectation did not.",
        )

    def list_cases(self) -> list[ExceptionCase]:
        self.ensure_loaded()
        return self.cases

    def get_case(self, case_id: str) -> ExceptionCase:
        self.ensure_loaded()
        for case in self.cases:
            if case.id == case_id:
                return case
        raise KeyError(case_id)

    def transition_case(
        self,
        case_id: str,
        target: ExceptionCaseStatus,
        note: str,
        *,
        actor: str = "demo-reviewer",
    ) -> ExceptionCase:
        case = self.get_case(case_id)
        allowed = {
            ExceptionCaseStatus.OPEN: {ExceptionCaseStatus.VERIFIED},
            ExceptionCaseStatus.VERIFIED: {
                ExceptionCaseStatus.ESCALATED,
                ExceptionCaseStatus.RESOLVED,
            },
            ExceptionCaseStatus.ESCALATED: {ExceptionCaseStatus.RESOLVED},
            ExceptionCaseStatus.RESOLVED: set(),
        }
        if target not in allowed[case.status]:
            raise RuntimeError(f"Cannot transition {case.status.value} to {target.value}")
        if target == ExceptionCaseStatus.VERIFIED:
            if not case.evidence or not all(item.verified for item in case.evidence):
                raise RuntimeError("Every evidence item must be deterministically verified")
            payment = self._payment(case.payment_id)
            applied = governance.effective_control("DOMESTIC_CARD_MDR", payment.captured_at.date())
            if applied.id != "CTRL_MDR_DOMESTIC":
                raise RuntimeError("The expected historical control version was not selected")
            note = note or (
                "Evidence pack verified: approved v1 control, observed fee, "
                "calculation and lineage."
            )
        elif not note.strip():
            raise RuntimeError("A note is required for escalation or resolution")
        previous = case.status
        occurred_at = datetime.now(timezone.utc)
        case.status = target
        case.updated_at = occurred_at
        case.version += 1
        if target == ExceptionCaseStatus.RESOLVED:
            case.resolution_note = note
        case.audit_trail.append(
            CaseAuditEntry(
                from_status=previous,
                to_status=target,
                actor=actor,
                note=note,
                occurred_at=occurred_at,
            )
        )
        return case

    def unresolved_matches(self) -> list[UnresolvedMatch]:
        self.ensure_loaded()
        assert self.dataset is not None
        unresolved: list[UnresolvedMatch] = []
        for payment in self.dataset.payments:
            if self.dataset.ground_truth[payment.payment_id] != "UNRESOLVED":
                continue
            unresolved.append(
                UnresolvedMatch(
                    id=payment.unresolved_case_id or f"UNR_{payment.payment_id}",
                    payment_id=payment.payment_id,
                    amount=payment.actual_net,
                    settlement_id=payment.settlement_id,
                    missing_evidence="No unique bank transaction reference was supplied.",
                    candidate_bank_references=[
                        f"BANK_CANDIDATE_{payment.payment_id}_A",
                        f"BANK_CANDIDATE_{payment.payment_id}_B",
                    ],
                    safe_conclusion=(
                        "Insufficient evidence exists to select a bank match without guessing."
                    ),
                )
            )
        return unresolved

    def get_root_cause(self, root_cause_id: str) -> RootCause:
        self.ensure_loaded()
        for root in self.root_causes:
            if root.id == root_cause_id:
                return root
        raise KeyError(root_cause_id)


store = DemoStore()
