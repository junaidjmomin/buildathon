from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from time import perf_counter

from app.controls.engine import DOMESTIC_MDR_RATE, evaluate_payment
from app.core.money import money
from app.domain.models import (
    ConfusionMatrix,
    Control,
    ControlType,
    DemoLoadResponse,
    EvaluationStatus,
    Evidence,
    ExpectedActualResponse,
    ExpectedActualRow,
    GraphEdge,
    GraphNode,
    HypothesisResponse,
    HypothesisVerification,
    PaymentGraph,
    PaymentLifecycle,
    RootCause,
    RunSummary,
    StatusBreakdown,
    Violation,
)
from app.synthetic.generator import DEMO_SEED, KNOWN_PAYMENT_ID, SyntheticDataset, generate_dataset

DEMO_RUN_ID = "RUN_NOVACART_AUG_2026"

CONTROLS = [
    Control(
        id="CTRL_MDR_DOMESTIC",
        name="Domestic Card MDR",
        control_type=ControlType.MDR_RATE,
        expected="1.55%",
        scope="Card · Domestic",
        source="NovaCart Merchant Agreement",
        source_clause="Page 4 · Clause 4.2",
    ),
    Control(
        id="CTRL_GST_FEE",
        name="GST on Processing Fee",
        control_type=ControlType.GST_ON_FEE,
        expected="18%",
        scope="Processing fee",
        source="NovaCart Merchant Agreement",
        source_clause="Page 4 · Clause 4.3",
    ),
    Control(
        id="CTRL_SETTLEMENT_SLA",
        name="Standard Settlement SLA",
        control_type=ControlType.SETTLEMENT_SLA,
        expected="T+2 business days",
        scope="Captured payments",
        source="NovaCart Merchant Agreement",
        source_clause="Page 6 · Clause 6.1",
    ),
    Control(
        id="CTRL_REFUND",
        name="Refund Principal Integrity",
        control_type=ControlType.REFUND_INTEGRITY,
        expected="Deduct once",
        scope="Successful refunds",
        source="NovaCart Merchant Agreement",
        source_clause="Page 7 · Clause 7.2",
    ),
]


class DemoStore:
    def __init__(self) -> None:
        self.dataset: SyntheticDataset | None = None
        self.summary: RunSummary | None = None
        self.violations: list[Violation] = []
        self.root_causes: list[RootCause] = []

    def load(self) -> DemoLoadResponse:
        started = perf_counter()
        self.dataset = generate_dataset(DEMO_SEED)
        self.violations = self._build_violations(self.dataset)
        self.root_causes = self._build_root_causes(self.violations)
        self.summary = self._build_summary(self.dataset, started)
        return DemoLoadResponse(
            run_id=DEMO_RUN_ID,
            name="NovaCart · August 2026",
            counts=self.dataset.counts,
            known_demo_ids={
                "mdr_violation": KNOWN_PAYMENT_ID,
                "duplicate_refund": "PAY_0033",
                "sla_violation": "PAY_0038",
                "root_cause": "RC_MDR_01",
                "unresolved": "PAY_0056",
            },
        )

    def ensure_loaded(self) -> None:
        if self.dataset is None:
            self.load()

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
                )
            )
        return sorted(roots, key=lambda root: root.verified_impact, reverse=True)

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
                control="CTRL_MDR_DOMESTIC",
                calculation=f"₹{payment.amount:.2f} × 1.55% = ₹{result.expected_fee:.2f}",
                expected=result.expected_fee,
                actual=payment.actual_fee,
                difference=money(payment.actual_fee - result.expected_fee),
                source="NovaCart Merchant Agreement",
                source_clause="Page 4 · Clause 4.2",
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
        )

    def graph(self, payment_id: str) -> PaymentGraph:
        payment = self._payment(payment_id)
        result = evaluate_payment(payment)
        nodes = [
            GraphNode(id=payment.order_id, kind="ORDER", label="Order", amount=payment.amount),
            GraphNode(id=payment.payment_id, kind="PAYMENT", label="Payment", amount=payment.amount),
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
            GraphEdge(id="E1", source=payment.order_id, target=payment.payment_id, relationship="PAID_BY", confidence=Decimal("1"), method="EXACT"),
            GraphEdge(id="E2", source=payment.payment_id, target=f"FEE_{payment.payment_id}", relationship="CHARGED_FEE", confidence=Decimal("1"), method="RULE"),
            GraphEdge(id="E3", source=payment.payment_id, target=f"TAX_{payment.payment_id}", relationship="CHARGED_TAX", confidence=Decimal("1"), method="RULE"),
            GraphEdge(id="E4", source=payment.payment_id, target=payment.settlement_id, relationship="INCLUDED_IN", confidence=Decimal("1"), method="EXACT"),
        ]
        if payment.bank_txn_id and payment.bank_credit is not None:
            nodes.append(GraphNode(id=payment.bank_txn_id, kind="BANK_ENTRY", label="Bank credit", amount=payment.bank_credit, status=result.bank_status))
            edges.append(GraphEdge(id="E5", source=payment.settlement_id, target=payment.bank_txn_id, relationship="CREDITED_AS", confidence=Decimal("1"), method="EXACT"))
        return PaymentGraph(payment_id=payment_id, nodes=nodes, edges=edges)

    def generate_hypothesis(self, root_cause_id: str) -> HypothesisResponse:
        root = self.get_root_cause(root_cause_id)
        hypothesis = (
            "Domestic card MDR may have changed from 1.55% to 1.75% "
            "beginning on 18 August 2026."
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
            {"label": "Approved amendments", "value": "No rate change found", "result": "NONE"},
            {"label": "Historical behaviour", "value": "1.55%", "result": "MATCH"},
            {"label": "Observed behaviour", "value": root.observed_value, "result": "DEVIATION"},
            {"label": "Affected transactions", "value": f"{root.affected_count} / {root.affected_count}", "result": "REPRODUCED"},
        ]
        root.verification_evidence = {"checks": checks}
        return HypothesisVerification(
            root_cause_id=root.id,
            status="REJECTED",
            classification="POTENTIAL_SYSTEMIC_OVERCHARGE",
            checks=checks,
            conclusion="Observed behaviour changed. Contractual expectation did not.",
        )

    def get_root_cause(self, root_cause_id: str) -> RootCause:
        self.ensure_loaded()
        for root in self.root_causes:
            if root.id == root_cause_id:
                return root
        raise KeyError(root_cause_id)


store = DemoStore()

