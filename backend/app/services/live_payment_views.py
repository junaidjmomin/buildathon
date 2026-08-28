"""Payment-level views for live (persisted) runs.

The seeded demo store answers the payment drill-down endpoints from an
in-memory dataset. Uploaded CSV runs only persist canonical events, edges,
control evaluations and violations, so these builders reconstruct the same
views deterministically from Postgres. No LLM participates in any step.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.money import money
from app.domain.models import (
    CashFlow,
    CounterfactualDriver,
    CounterfactualSettlement,
    EvaluationStatus,
    Evidence,
    ExpectedActualResponse,
    ExpectedActualRow,
    GraphEdge,
    GraphNode,
    LineageType,
    PaymentGraph,
    ViolationLineageNode,
    ViolationLineageResponse,
)
from app.persistence.orm import (
    ControlEvaluationRecord,
    ControlRecord,
    EventEdgeRecord,
    EventRecord,
    RunRecord,
    ViolationRecord,
)

_DECIMAL_ZERO = Decimal("0")


def _payload_decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = Decimal(str(value))
    except InvalidOperation:
        return None
    return parsed if parsed.is_finite() else None


def _outcome(evaluation: ControlEvaluationRecord) -> EvaluationStatus:
    return EvaluationStatus(evaluation.outcome)


def _worst_status(statuses: list[EvaluationStatus]) -> EvaluationStatus:
    for status in (EvaluationStatus.UNRESOLVED, EvaluationStatus.VIOLATION):
        if status in statuses:
            return status
    return statuses[0] if statuses else EvaluationStatus.PASS


class _PaymentContext:
    """Everything the live views need for one payment of one run."""

    def __init__(self, session: Session, *, tenant_id: str, run_id: str, payment_id: str) -> None:
        self.session = session
        self.payment_id = payment_id
        self.event = session.scalar(
            select(EventRecord).where(
                EventRecord.tenant_id == tenant_id,
                EventRecord.run_id == run_id,
                EventRecord.event_type == "PAYMENT",
                EventRecord.external_id == payment_id,
            )
        )
        if self.event is None:
            return
        self.evaluations = list(
            session.scalars(
                select(ControlEvaluationRecord)
                .where(
                    ControlEvaluationRecord.tenant_id == tenant_id,
                    ControlEvaluationRecord.run_id == run_id,
                    ControlEvaluationRecord.target_type == "PAYMENT",
                    ControlEvaluationRecord.target_id == payment_id,
                )
                .order_by(ControlEvaluationRecord.evaluated_at, ControlEvaluationRecord.id)
            )
        )
        self.controls: dict[str, ControlRecord] = {
            record.id: record
            for record in session.scalars(
                select(ControlRecord).where(
                    ControlRecord.tenant_id == tenant_id,
                    ControlRecord.id.in_(
                        {evaluation.control_id for evaluation in self.evaluations}
                    ),
                )
            )
        }
        self.edges = list(
            session.scalars(
                select(EventEdgeRecord)
                .where(
                    EventEdgeRecord.tenant_id == tenant_id,
                    EventEdgeRecord.run_id == run_id,
                    (EventEdgeRecord.from_event_id == self.event.id)
                    | (EventEdgeRecord.to_event_id == self.event.id),
                )
                .order_by(EventEdgeRecord.id)
            )
        )
        self.neighbour_events: dict[str, EventRecord] = {
            record.id: record
            for record in session.scalars(
                select(EventRecord).where(
                    EventRecord.tenant_id == tenant_id,
                    EventRecord.run_id == run_id,
                    EventRecord.id.in_(
                        {
                            edge.to_event_id
                            if edge.from_event_id == self.event.id
                            else edge.from_event_id
                            for edge in self.edges
                        }
                    ),
                )
            )
        }

    @property
    def payload(self) -> dict[str, Any]:
        return self.event.normalized_payload or {}

    def evaluation_for(self, control_type: str) -> ControlEvaluationRecord | None:
        for evaluation in self.evaluations:
            control = self.controls.get(evaluation.control_id)
            if control is not None and control.control_type == control_type:
                return evaluation
        return None

    def settlement_events(self) -> list[EventRecord]:
        settlements = [
            self.neighbour_events[edge.to_event_id]
            for edge in self.edges
            if edge.from_event_id == self.event.id
            and edge.relationship == "INCLUDED_IN"
            and edge.to_event_id in self.neighbour_events
        ]
        return sorted(settlements, key=lambda record: (record.occurred_at, record.id))

    def bank_credit(self) -> tuple[Decimal, str] | None:
        """Bank credit and its settlement external id for the earliest settlement."""

        for settlement in self.settlement_events():
            edge = self.session.scalar(
                select(EventEdgeRecord).where(
                    EventEdgeRecord.tenant_id == settlement.tenant_id,
                    EventEdgeRecord.run_id == settlement.run_id,
                    EventEdgeRecord.from_event_id == settlement.id,
                    EventEdgeRecord.relationship == "CREDITED_AS",
                )
            )
            if edge is None:
                continue
            bank = self.session.scalar(
                select(EventRecord).where(
                    EventRecord.tenant_id == settlement.tenant_id,
                    EventRecord.run_id == settlement.run_id,
                    EventRecord.id == edge.to_event_id,
                )
            )
            if bank is not None:
                return bank.amount, settlement.external_id
        return None

    def settlement_evaluation(self, settlement_id: str) -> ControlEvaluationRecord | None:
        return self.session.scalar(
            select(ControlEvaluationRecord)
            .where(
                ControlEvaluationRecord.tenant_id == self.event.tenant_id,
                ControlEvaluationRecord.run_id == self.event.run_id,
                ControlEvaluationRecord.target_type == "SETTLEMENT",
                ControlEvaluationRecord.target_id == settlement_id,
            )
            .order_by(ControlEvaluationRecord.evaluated_at.desc())
            .limit(1)
        )


def _context(
    session: Session, *, tenant_id: str, run_id: str, payment_id: str
) -> _PaymentContext | None:
    run = session.get(RunRecord, (tenant_id, run_id))
    if run is None:
        return None
    context = _PaymentContext(session, tenant_id=tenant_id, run_id=run_id, payment_id=payment_id)
    return context if context.event is not None else None


def _descriptor(payload: dict[str, Any]) -> str:
    scope = str(payload.get("card_scope") or "").strip().lower()
    network = str(payload.get("card_network") or "").strip().lower()
    method = str(payload.get("method") or "").strip().lower()
    parts = [
        f"{scope.title()} {network.title()}".strip(),
        method,
    ]
    return " · ".join(part for part in parts if part)


def _control_evidence(evaluation: ControlEvaluationRecord, control: ControlRecord) -> Evidence:
    definition = control.definition or {}
    return Evidence(
        title=str(definition.get("name") or control.id),
        control=control.id,
        calculation=str(evaluation.evidence.get("calculation", "")),
        expected=evaluation.expected_amount,
        actual=evaluation.actual_amount,
        difference=evaluation.difference_amount,
        source=str(definition.get("source", "")),
        source_clause=str(definition.get("source_clause", "")),
    )


def _applied_control(
    context: _PaymentContext,
) -> tuple[ControlEvaluationRecord, ControlRecord] | None:
    preferred = ("MDR_RATE", "GST_ON_FEE", "REFUND_INTEGRITY", "SETTLEMENT_SLA")
    for control_type in preferred:
        evaluation = context.evaluation_for(control_type)
        if evaluation is not None:
            control = context.controls.get(evaluation.control_id)
            if control is not None:
                return evaluation, control
    return None


def expected_actual(
    session: Session, *, tenant_id: str, run_id: str, payment_id: str
) -> ExpectedActualResponse | None:
    context = _context(session, tenant_id=tenant_id, run_id=run_id, payment_id=payment_id)
    if context is None:
        return None

    payload = context.payload
    amount = context.event.amount
    fee = _payload_decimal(payload.get("fee"))
    tax = _payload_decimal(payload.get("tax"))
    declared_refunds = _payload_decimal(payload.get("amount_refunded")) or _DECIMAL_ZERO

    mdr = context.evaluation_for("MDR_RATE")
    gst = context.evaluation_for("GST_ON_FEE")
    refund = context.evaluation_for("REFUND_INTEGRITY")

    expected_fee = mdr.expected_amount if mdr is not None else None
    expected_tax = gst.expected_amount if gst is not None else None
    refund_deduction = refund.actual_amount if refund is not None else declared_refunds
    expected_refunds = refund.expected_amount if refund is not None else declared_refunds

    rows = [
        ExpectedActualRow(
            label="Gross",
            expected=amount,
            actual=amount,
            status=EvaluationStatus.PASS,
            difference=_DECIMAL_ZERO,
        )
    ]
    if mdr is not None:
        rows.append(
            ExpectedActualRow(
                label="MDR",
                expected=expected_fee or _DECIMAL_ZERO,
                actual=mdr.actual_amount,
                status=_outcome(mdr),
                difference=mdr.difference_amount or _DECIMAL_ZERO,
            )
        )
    if gst is not None:
        rows.append(
            ExpectedActualRow(
                label="GST",
                expected=expected_tax or _DECIMAL_ZERO,
                actual=gst.actual_amount,
                status=_outcome(gst),
                difference=gst.difference_amount or _DECIMAL_ZERO,
            )
        )
    if refund is not None:
        rows.append(
            ExpectedActualRow(
                label="Refunds",
                expected=expected_refunds or _DECIMAL_ZERO,
                actual=refund.actual_amount,
                status=_outcome(refund),
                difference=refund.difference_amount or _DECIMAL_ZERO,
            )
        )

    expected_net = money(
        amount
        - (expected_fee or _DECIMAL_ZERO)
        - (expected_tax or _DECIMAL_ZERO)
        - (expected_refunds or _DECIMAL_ZERO)
    )
    gateway_net = money(
        amount
        - (fee or _DECIMAL_ZERO)
        - (tax or _DECIMAL_ZERO)
        - (refund_deduction or _DECIMAL_ZERO)
    )
    rows.append(
        ExpectedActualRow(
            label="Net",
            expected=expected_net,
            actual=gateway_net,
            status=_worst_status([_outcome(item) for item in context.evaluations]),
            difference=money(expected_net - gateway_net),
        )
    )

    bank = context.bank_credit()
    bank_difference = None if bank is None else money(expected_net - bank[0])
    bank_status = (
        EvaluationStatus.UNRESOLVED
        if bank is None
        else (
            EvaluationStatus.PASS
            if abs(bank_difference or _DECIMAL_ZERO) <= Decimal("0.01")
            else EvaluationStatus.VIOLATION
        )
    )
    rows.append(
        ExpectedActualRow(
            label="Bank credit",
            expected=expected_net,
            actual=bank[0] if bank is not None else None,
            status=bank_status,
            difference=bank_difference or _DECIMAL_ZERO,
        )
    )

    applied = _applied_control(context)
    if applied is not None:
        _, control = applied
        applied_control_id = control.id
        applied_control_version = control.version
        effective_to = control.effective_to.date().isoformat() if control.effective_to else "open"
        applied_period = f"{control.effective_from.date().isoformat()} → {effective_to}"
    else:
        applied_control_id = ""
        applied_control_version = 0
        applied_period = "no control evaluation recorded"

    return ExpectedActualResponse(
        payment_id=payment_id,
        descriptor=_descriptor(payload),
        amount=amount,
        status=_worst_status([_outcome(item) for item in context.evaluations]),
        rows=rows,
        verified_leakage=money(
            sum(
                (evaluation.financial_impact or _DECIMAL_ZERO) for evaluation in context.evaluations
            )
        ),
        gateway_net=gateway_net,
        bank_credit=bank[0] if bank is not None else None,
        expected_net=expected_net,
        evidence=[
            _control_evidence(evaluation, context.controls[evaluation.control_id])
            for evaluation in context.evaluations
            if evaluation.control_id in context.controls
        ],
        applied_control_id=applied_control_id,
        applied_control_version=applied_control_version,
        applied_control_effective_period=applied_period,
    )


_KIND_LABELS = {
    "ORDER": "Order",
    "PAYMENT": "Payment",
    "REFUND": "Refund",
    "SETTLEMENT": "Settlement",
    "CHARGEBACK": "Chargeback",
    "BANK_CREDIT": "Bank credit",
    "BANK_DEBIT": "Bank debit",
    "UNRESOLVED_MATCH": "Unresolved match",
}


def graph(session: Session, *, tenant_id: str, run_id: str, payment_id: str) -> PaymentGraph | None:
    context = _context(session, tenant_id=tenant_id, run_id=run_id, payment_id=payment_id)
    if context is None:
        return None

    payload = context.payload
    mdr = context.evaluation_for("MDR_RATE")
    gst = context.evaluation_for("GST_ON_FEE")
    fee = _payload_decimal(payload.get("fee")) or _DECIMAL_ZERO
    tax = _payload_decimal(payload.get("tax")) or _DECIMAL_ZERO

    nodes = [
        GraphNode(
            id=payment_id,
            kind="PAYMENT",
            label="Payment",
            amount=context.event.amount,
            status=_worst_status([_outcome(item) for item in context.evaluations]),
            detail=_descriptor(payload) or None,
        )
    ]
    edges: list[GraphEdge] = []

    for edge in context.edges:
        neighbour_id = (
            edge.to_event_id if edge.from_event_id == context.event.id else edge.from_event_id
        )
        neighbour = context.neighbour_events[neighbour_id]
        status = EvaluationStatus.PASS
        if neighbour.event_type == "SETTLEMENT":
            evaluation = context.settlement_evaluation(neighbour.external_id)
            if evaluation is not None:
                status = _outcome(evaluation)
        nodes.append(
            GraphNode(
                id=neighbour.external_id,
                kind=neighbour.event_type,
                label=_KIND_LABELS.get(neighbour.event_type, neighbour.event_type.title()),
                amount=neighbour.amount,
                status=status,
            )
        )
        if edge.from_event_id == context.event.id:
            source, target = payment_id, neighbour.external_id
        else:
            source, target = neighbour.external_id, payment_id
        edges.append(
            GraphEdge(
                id=edge.id,
                source=source,
                target=target,
                relationship=edge.relationship,
                confidence=edge.confidence,
                method=edge.method,
            )
        )

    nodes.append(
        GraphNode(
            id=f"FEE_{payment_id}",
            kind="FEE",
            label="Processing fee",
            amount=fee,
            status=_outcome(mdr) if mdr is not None else EvaluationStatus.UNRESOLVED,
            detail=f"Expected ₹{(mdr.expected_amount or _DECIMAL_ZERO):.2f}"
            if mdr is not None
            else None,
        )
    )
    nodes.append(
        GraphNode(
            id=f"TAX_{payment_id}",
            kind="TAX",
            label="GST",
            amount=tax,
            status=_outcome(gst) if gst is not None else EvaluationStatus.UNRESOLVED,
            detail=f"Expected ₹{(gst.expected_amount or _DECIMAL_ZERO):.2f}"
            if gst is not None
            else None,
        )
    )
    edges.append(
        GraphEdge(
            id=f"edge-fee-{payment_id}",
            source=payment_id,
            target=f"FEE_{payment_id}",
            relationship="CHARGED_FEE",
            confidence=Decimal("1"),
            method="RULE",
        )
    )
    edges.append(
        GraphEdge(
            id=f"edge-tax-{payment_id}",
            source=payment_id,
            target=f"TAX_{payment_id}",
            relationship="CHARGED_TAX",
            confidence=Decimal("1"),
            method="RULE",
        )
    )

    return PaymentGraph(payment_id=payment_id, nodes=nodes, edges=edges)


def lineage(
    session: Session, *, tenant_id: str, run_id: str, payment_id: str
) -> ViolationLineageResponse | None:
    context = _context(session, tenant_id=tenant_id, run_id=run_id, payment_id=payment_id)
    if context is None:
        return None

    records = list(
        context.session.scalars(
            select(ViolationRecord)
            .where(ViolationRecord.tenant_id == tenant_id, ViolationRecord.run_id == run_id)
            .order_by(ViolationRecord.occurred_at, ViolationRecord.id)
        )
    )
    primary = [
        record
        for record in records
        if record.payment_id == payment_id and (record.lineage_type or "PRIMARY") == "PRIMARY"
    ]
    primary_ids = {record.id for record in primary}
    root_ids = {record.root_violation_id or record.id for record in primary}
    downstream = [
        record
        for record in records
        if (record.lineage_type or "PRIMARY") == "DOWNSTREAM"
        and ((record.root_violation_id in root_ids) or (record.parent_violation_id in primary_ids))
    ]

    def node(record: ViolationRecord) -> ViolationLineageNode:
        evidence = record.evidence or {}
        return ViolationLineageNode(
            id=record.id,
            category=record.category,
            lineage_type=LineageType(record.lineage_type or "PRIMARY"),
            parent_violation_id=record.parent_violation_id,
            root_violation_id=record.root_violation_id or record.id,
            expected=_payload_decimal(evidence.get("expected")) or _DECIMAL_ZERO,
            actual=_payload_decimal(evidence.get("actual")) or _DECIMAL_ZERO,
            difference=record.difference,
            financial_impact=record.financial_impact,
            causal_evidence=record.causal_evidence or {},
        )

    nodes = [node(record) for record in primary + downstream]

    return ViolationLineageResponse(
        payment_id=payment_id,
        primary_violation_count=len(primary),
        downstream_effect_count=len(downstream),
        nodes=nodes,
    )


def counterfactual(
    session: Session, *, tenant_id: str, run_id: str, payment_id: str
) -> CounterfactualSettlement | None:
    context = _context(session, tenant_id=tenant_id, run_id=run_id, payment_id=payment_id)
    if context is None:
        return None

    payload = context.payload
    amount = context.event.amount
    fee = _payload_decimal(payload.get("fee")) or _DECIMAL_ZERO
    tax = _payload_decimal(payload.get("tax")) or _DECIMAL_ZERO
    declared_refunds = _payload_decimal(payload.get("amount_refunded")) or _DECIMAL_ZERO

    mdr = context.evaluation_for("MDR_RATE")
    gst = context.evaluation_for("GST_ON_FEE")
    refund = context.evaluation_for("REFUND_INTEGRITY")

    expected_fee = (mdr.expected_amount if mdr is not None else None) or fee
    expected_tax = (gst.expected_amount if gst is not None else None) or tax
    expected_refunds = (refund.expected_amount if refund is not None else None) or declared_refunds
    refund_deduction = (refund.actual_amount if refund is not None else None) or declared_refunds

    actual = CashFlow(
        gross=amount,
        mdr=money(fee),
        gst=money(tax),
        refunds=money(refund_deduction),
        other_fees=_DECIMAL_ZERO,
        net=money(amount - fee - tax - refund_deduction),
    )
    expected = CashFlow(
        gross=amount,
        mdr=money(expected_fee),
        gst=money(expected_tax),
        refunds=money(expected_refunds),
        other_fees=_DECIMAL_ZERO,
        net=money(amount - expected_fee - expected_tax - expected_refunds),
    )

    drivers = []
    if fee > expected_fee:
        drivers.append(CounterfactualDriver(type="EXCESS_MDR", amount=money(fee - expected_fee)))
    if tax > expected_tax:
        drivers.append(CounterfactualDriver(type="EXCESS_GST", amount=money(tax - expected_tax)))
    if refund_deduction > expected_refunds:
        drivers.append(
            CounterfactualDriver(
                type="EXCESS_REFUND_DEDUCTION",
                amount=money(refund_deduction - expected_refunds),
            )
        )

    return CounterfactualSettlement(
        payment_id=payment_id,
        actual=actual,
        expected=expected,
        difference=money(expected.net - actual.net),
        drivers=drivers,
    )
