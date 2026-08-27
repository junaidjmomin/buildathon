from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from typing import Any

from app.controls.dsl import (
    GstFeeParameters,
    MdrRateParameters,
    RefundIntegrityParameters,
    SettlementArithmeticParameters,
)
from app.core.money import add_business_days, business_days_late, expected_fee, expected_gst, money
from app.domain.models import (
    CanonicalEventEdge,
    Control,
    EvaluationStatus,
    FinancialEvent,
    LineageType,
    Violation,
)


@dataclass(frozen=True)
class LiveControlEvaluation:
    evaluation_id: str
    event: FinancialEvent
    control: Control
    target_type: str
    target_id: str
    outcome: EvaluationStatus
    expected_amount: Decimal | None
    actual_amount: Decimal | None
    tolerance_amount: Decimal | None
    difference_amount: Decimal | None
    financial_impact: Decimal
    input_fingerprint: str
    evidence: dict[str, Any]
    source_snapshot_ids: list[str]
    violation: Violation | None


def build_live_control_evaluations(
    events: list[FinancialEvent],
    edges: list[CanonicalEventEdge],
    controls: list[Control],
) -> list[LiveControlEvaluation]:
    """Evaluate the supported live controls without inferring missing evidence.

    Source values are accepted only from the canonical model. Monetary JSON fields
    must be decimal strings; invalid or absent values produce ``UNRESOLVED``.
    """

    event_by_id = {event.id: event for event in events}
    outgoing: dict[tuple[str, str], list[CanonicalEventEdge]] = {}
    incoming: dict[tuple[str, str], list[CanonicalEventEdge]] = {}
    for edge in edges:
        outgoing.setdefault((edge.from_event_id, edge.relationship), []).append(edge)
        incoming.setdefault((edge.to_event_id, edge.relationship), []).append(edge)

    evaluations: list[LiveControlEvaluation] = []
    payments = sorted(
        (event for event in events if event.event_type == "PAYMENT"),
        key=lambda event: event.id,
    )
    for payment in payments:
        mdr = _effective_control(controls, "DOMESTIC_CARD_MDR", payment.timestamp.date())
        gst = _effective_control(controls, "GST_ON_VALID_FEE", payment.timestamp.date())
        sla = _effective_control(controls, "CAPTURE_TO_SETTLEMENT_SLA", payment.timestamp.date())
        refund = _effective_control(
            controls,
            "REFUND_PRINCIPAL_INTEGRITY",
            payment.timestamp.date(),
        )
        if mdr is not None and _is_card_payment(payment):
            evaluations.append(_evaluate_mdr(payment, mdr))
        if gst is not None and _is_card_payment(payment):
            evaluations.append(_evaluate_gst(payment, gst, mdr))
        if sla is not None and _is_captured_payment(payment):
            evaluations.append(
                _evaluate_sla(
                    payment,
                    sla,
                    outgoing=outgoing,
                    event_by_id=event_by_id,
                )
            )
        if refund is not None:
            evaluations.append(
                _evaluate_refunds(
                    payment,
                    refund,
                    outgoing=outgoing,
                    event_by_id=event_by_id,
                )
            )

    settlements = sorted(
        (event for event in events if event.event_type == "SETTLEMENT"),
        key=lambda event: event.id,
    )
    for settlement in settlements:
        arithmetic = _effective_control(
            controls,
            "SETTLEMENT_BANK_ARITHMETIC",
            settlement.timestamp.date(),
        )
        if arithmetic is not None:
            evaluations.append(
                _evaluate_settlement_arithmetic(
                    settlement,
                    arithmetic,
                    controls=controls,
                    incoming=incoming,
                    event_by_id=event_by_id,
                )
            )
    return evaluations


def _effective_control(controls: list[Control], logical_key: str, at: date) -> Control | None:
    matches = [
        control
        for control in controls
        if control.logical_control_key == logical_key
        and control.status == "APPROVED"
        and control.effective_from <= at
        and (control.effective_to is None or at <= control.effective_to)
    ]
    if len(matches) != 1:
        return None
    return matches[0]


def _is_card_payment(event: FinancialEvent) -> bool:
    normalized = event.normalized_payload
    return (normalized.get("method") or normalized.get("payment_method")) == "card"


def _is_captured_payment(event: FinancialEvent) -> bool:
    return bool(event.normalized_payload.get("captured")) or event.status in {
        "captured",
        "settled",
    }


def _decimal_string(value: Any) -> Decimal | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = Decimal(value)
    except InvalidOperation:
        return None
    return parsed if parsed.is_finite() else None


def _snapshot_ids(*events: FinancialEvent) -> list[str]:
    result: set[str] = set()
    for event in events:
        raw = event.normalized_payload.get("source_snapshot_ids", [])
        if isinstance(raw, list):
            result.update(item for item in raw if isinstance(item, str))
    return sorted(result)


def _fingerprint(*parts: object) -> str:
    return sha256("|".join(str(part) for part in parts).encode()).hexdigest()


def _result(
    *,
    prefix: str,
    event: FinancialEvent,
    control: Control,
    target_type: str,
    target_id: str,
    outcome: EvaluationStatus,
    expected: Decimal | None,
    actual: Decimal | None,
    tolerance: Decimal | None,
    difference: Decimal | None,
    impact: Decimal,
    evidence: dict[str, Any],
    snapshots: list[str],
    violation_category: str,
    violation_expected: str,
    violation_actual: str,
    fingerprint_parts: tuple[object, ...],
) -> LiveControlEvaluation:
    fingerprint = _fingerprint(
        event.id,
        control.id,
        control.version,
        target_type,
        target_id,
        *fingerprint_parts,
    )
    violation = None
    if outcome == EvaluationStatus.VIOLATION:
        violation = Violation(
            id=f"V_{prefix}_{fingerprint[:24].upper()}",
            payment_id=target_id,
            category=violation_category,
            control_type=control.control_type,
            expected=violation_expected,
            actual=violation_actual,
            difference=difference or Decimal("0"),
            financial_impact=impact,
            confidence=Decimal("1"),
            status=EvaluationStatus.VIOLATION,
            occurred_at=event.timestamp,
        )
    return LiveControlEvaluation(
        evaluation_id=f"EVAL_{prefix}_{fingerprint[:24].upper()}",
        event=event,
        control=control,
        target_type=target_type,
        target_id=target_id,
        outcome=outcome,
        expected_amount=expected,
        actual_amount=actual,
        tolerance_amount=tolerance,
        difference_amount=difference,
        financial_impact=impact,
        input_fingerprint=fingerprint,
        evidence=evidence,
        source_snapshot_ids=snapshots,
        violation=violation,
    )


def _evaluate_mdr(event: FinancialEvent, control: Control) -> LiveControlEvaluation:
    parameters = MdrRateParameters.model_validate(control.parameters)
    expected = expected_fee(event.amount, parameters.rate)
    actual = _decimal_string(event.normalized_payload.get("fee"))
    international = event.normalized_payload.get("international")
    difference = money(actual - expected) if actual is not None else None
    unresolved = international is not False or actual is None or event.status == "unresolved"
    if unresolved:
        outcome = EvaluationStatus.UNRESOLVED
    elif abs(difference or Decimal("0")) > parameters.tolerance:
        outcome = EvaluationStatus.VIOLATION
    else:
        outcome = EvaluationStatus.PASS
    impact = (
        max(difference or Decimal("0"), Decimal("0"))
        if outcome == EvaluationStatus.VIOLATION
        else Decimal("0")
    )
    return _result(
        prefix="MDR",
        event=event,
        control=control,
        target_type="PAYMENT",
        target_id=event.external_id,
        outcome=outcome,
        expected=expected,
        actual=actual,
        tolerance=parameters.tolerance,
        difference=difference,
        impact=impact,
        evidence={
            "event_id": event.id,
            "calculation": f"{event.amount} * {control.parameters['rate']}",
            "authority": "DETERMINISTIC",
            "decision_reason": "MISSING_OR_AMBIGUOUS_INPUT" if unresolved else "DECIMAL_COMPARE",
        },
        snapshots=_snapshot_ids(event),
        violation_category="MDR rate deviation",
        violation_expected=str(expected),
        violation_actual=str(actual) if actual is not None else "UNRESOLVED",
        fingerprint_parts=(event.amount, actual, parameters.rate, parameters.tolerance),
    )


def _evaluate_gst(
    event: FinancialEvent,
    control: Control,
    mdr_control: Control | None,
) -> LiveControlEvaluation:
    parameters = GstFeeParameters.model_validate(control.parameters)
    expected: Decimal | None = None
    approved_fee: Decimal | None = None
    if mdr_control is not None and event.normalized_payload.get("international") is False:
        mdr = MdrRateParameters.model_validate(mdr_control.parameters)
        approved_fee = expected_fee(event.amount, mdr.rate)
        expected = expected_gst(approved_fee, parameters.rate)
    actual = _decimal_string(event.normalized_payload.get("tax"))
    difference = money(actual - expected) if actual is not None and expected is not None else None
    unresolved = expected is None or actual is None or event.status == "unresolved"
    if unresolved:
        outcome = EvaluationStatus.UNRESOLVED
    elif abs(difference or Decimal("0")) > parameters.tolerance:
        outcome = EvaluationStatus.VIOLATION
    else:
        outcome = EvaluationStatus.PASS
    impact = (
        max(difference or Decimal("0"), Decimal("0"))
        if outcome == EvaluationStatus.VIOLATION
        else Decimal("0")
    )
    return _result(
        prefix="GST",
        event=event,
        control=control,
        target_type="PAYMENT",
        target_id=event.external_id,
        outcome=outcome,
        expected=expected,
        actual=actual,
        tolerance=parameters.tolerance,
        difference=difference,
        impact=impact,
        evidence={
            "event_id": event.id,
            "approved_fee": str(approved_fee) if approved_fee is not None else None,
            "calculation": (
                f"{approved_fee} * {control.parameters['rate']}"
                if approved_fee is not None
                else "UNRESOLVED_APPROVED_FEE_BASE"
            ),
            "authority": "DETERMINISTIC",
            "decision_reason": "MISSING_OR_AMBIGUOUS_INPUT" if unresolved else "DECIMAL_COMPARE",
        },
        snapshots=_snapshot_ids(event),
        violation_category="GST on approved fee deviation",
        violation_expected=str(expected) if expected is not None else "UNRESOLVED",
        violation_actual=str(actual) if actual is not None else "UNRESOLVED",
        fingerprint_parts=(
            event.amount,
            approved_fee,
            actual,
            parameters.rate,
            parameters.tolerance,
        ),
    )


def _evaluate_sla(
    event: FinancialEvent,
    control: Control,
    *,
    outgoing: dict[tuple[str, str], list[CanonicalEventEdge]],
    event_by_id: dict[str, FinancialEvent],
) -> LiveControlEvaluation:
    business_days = control.parameters.get("business_days")
    days = business_days if isinstance(business_days, int) and business_days >= 0 else None
    related_edges = outgoing.get((event.id, "INCLUDED_IN"), [])
    settlements = [
        event_by_id[edge.to_event_id]
        for edge in related_edges
        if edge.to_event_id in event_by_id
        and event_by_id[edge.to_event_id].event_type == "SETTLEMENT"
    ]
    settlement = min(settlements, key=lambda item: item.timestamp) if settlements else None
    due_at = add_business_days(event.timestamp, days) if days is not None else None
    delay_days = (
        business_days_late(due_at, settlement.timestamp)
        if due_at is not None and settlement is not None
        else None
    )
    unresolved = days is None or settlement is None or event.status == "unresolved"
    if unresolved:
        outcome = EvaluationStatus.UNRESOLVED
    elif delay_days and delay_days > 0:
        outcome = EvaluationStatus.VIOLATION
    else:
        outcome = EvaluationStatus.PASS
    difference = Decimal(delay_days) if delay_days is not None else None
    return _result(
        prefix="SLA",
        event=event,
        control=control,
        target_type="PAYMENT",
        target_id=event.external_id,
        outcome=outcome,
        expected=event.amount,
        actual=event.amount if settlement is not None else None,
        tolerance=None,
        difference=difference,
        impact=Decimal("0"),
        evidence={
            "payment_event_id": event.id,
            "settlement_event_id": settlement.id if settlement is not None else None,
            "captured_at": event.timestamp.isoformat(),
            "due_at": due_at.isoformat() if due_at is not None else None,
            "settled_at": settlement.timestamp.isoformat() if settlement is not None else None,
            "business_days_late": delay_days,
            "cash_exposure": str(event.amount),
            "authority": "DETERMINISTIC",
            "decision_reason": (
                "MISSING_SETTLEMENT_EVIDENCE" if unresolved else "BUSINESS_DAY_COMPARE"
            ),
        },
        snapshots=_snapshot_ids(event, *settlements),
        violation_category="Settlement SLA deviation",
        violation_expected=due_at.isoformat() if due_at is not None else "UNRESOLVED",
        violation_actual=(
            settlement.timestamp.isoformat() if settlement is not None else "UNRESOLVED"
        ),
        fingerprint_parts=(event.timestamp, due_at, settlement.timestamp if settlement else None),
    )


def _evaluate_refunds(
    event: FinancialEvent,
    control: Control,
    *,
    outgoing: dict[tuple[str, str], list[CanonicalEventEdge]],
    event_by_id: dict[str, FinancialEvent],
) -> LiveControlEvaluation:
    parameters = RefundIntegrityParameters.model_validate(control.parameters)
    tolerance = parameters.tolerance
    declared = _decimal_string(event.normalized_payload.get("amount_refunded"))
    related_edges = outgoing.get((event.id, "REFUNDED_BY"), [])
    refunds = [
        event_by_id[edge.to_event_id]
        for edge in related_edges
        if edge.to_event_id in event_by_id and event_by_id[edge.to_event_id].event_type == "REFUND"
    ]
    linked_total = money(sum((refund.amount for refund in refunds), Decimal("0")))
    fees: list[Decimal] = []
    invalid_fee = False
    for refund in refunds:
        raw_fee = refund.normalized_payload.get("fee")
        if raw_fee is None:
            continue
        parsed = _decimal_string(raw_fee)
        if parsed is None:
            invalid_fee = True
        else:
            fees.append(parsed)
    total_fee = money(sum(fees, Decimal("0")))
    over_declared = money(linked_total - declared) if declared is not None else None
    difference = (
        money(max(over_declared, Decimal("0")) + total_fee) if over_declared is not None else None
    )
    unresolved = (
        declared is None
        or invalid_fee
        or event.status == "unresolved"
        or (declared > linked_total and declared > 0)
    )
    violated = declared is not None and (
        linked_total - declared > tolerance
        or linked_total - event.amount > tolerance
        or total_fee - parameters.refund_fee > tolerance
    )
    if unresolved:
        outcome = EvaluationStatus.UNRESOLVED
    elif violated:
        outcome = EvaluationStatus.VIOLATION
    else:
        outcome = EvaluationStatus.PASS
    impact = difference if outcome == EvaluationStatus.VIOLATION and difference else Decimal("0")
    return _result(
        prefix="REFUND",
        event=event,
        control=control,
        target_type="PAYMENT",
        target_id=event.external_id,
        outcome=outcome,
        expected=declared,
        actual=money(linked_total + total_fee),
        tolerance=tolerance,
        difference=difference,
        impact=impact,
        evidence={
            "payment_event_id": event.id,
            "refund_event_ids": [refund.id for refund in refunds],
            "declared_refund_total": str(declared) if declared is not None else None,
            "linked_refund_total": str(linked_total),
            "refund_fee_total": str(total_fee),
            "authority": "DETERMINISTIC",
            "decision_reason": (
                "INCOMPLETE_REFUND_EVIDENCE" if unresolved else "REFUND_PRINCIPAL_AND_FEE_COMPARE"
            ),
        },
        snapshots=_snapshot_ids(event, *refunds),
        violation_category="Refund principal integrity deviation",
        violation_expected=str(declared) if declared is not None else "UNRESOLVED",
        violation_actual=str(money(linked_total + total_fee)),
        fingerprint_parts=(
            declared,
            linked_total,
            total_fee,
            parameters.refund_fee,
            tolerance,
        ),
    )


def _evaluate_settlement_arithmetic(
    event: FinancialEvent,
    control: Control,
    *,
    controls: list[Control],
    incoming: dict[tuple[str, str], list[CanonicalEventEdge]],
    event_by_id: dict[str, FinancialEvent],
) -> LiveControlEvaluation:
    parameters = SettlementArithmeticParameters.model_validate(control.parameters)
    related_edges = incoming.get((event.id, "INCLUDED_IN"), [])
    contributors = [
        event_by_id[edge.from_event_id]
        for edge in related_edges
        if edge.from_event_id in event_by_id
    ]
    expected = Decimal("0")
    complete = bool(contributors)
    components: list[dict[str, str]] = []
    for contributor in contributors:
        if contributor.event_type == "REFUND":
            expected -= contributor.amount
            components.append(
                {"event_id": contributor.id, "type": "REFUND", "amount": str(-contributor.amount)}
            )
            continue
        if contributor.event_type != "PAYMENT":
            complete = False
            continue
        mdr = _effective_control(controls, "DOMESTIC_CARD_MDR", contributor.timestamp.date())
        gst = _effective_control(controls, "GST_ON_VALID_FEE", contributor.timestamp.date())
        domestic_card = (
            _is_card_payment(contributor)
            and contributor.normalized_payload.get("international") is False
        )
        if mdr is None or gst is None or not domestic_card:
            complete = False
            continue
        mdr_parameters = MdrRateParameters.model_validate(mdr.parameters)
        gst_parameters = GstFeeParameters.model_validate(gst.parameters)
        approved_fee = expected_fee(contributor.amount, mdr_parameters.rate)
        approved_tax = expected_gst(approved_fee, gst_parameters.rate)
        net = money(contributor.amount - approved_fee - approved_tax)
        expected += net
        components.append(
            {
                "event_id": contributor.id,
                "type": "PAYMENT_NET",
                "amount": str(net),
            }
        )
    expected = money(expected) if complete else None
    actual = event.amount
    difference = money(actual - expected) if expected is not None else None
    unresolved = not complete or event.status == "unresolved"
    if unresolved:
        outcome = EvaluationStatus.UNRESOLVED
    elif abs(difference or Decimal("0")) > parameters.tolerance:
        outcome = EvaluationStatus.VIOLATION
    else:
        outcome = EvaluationStatus.PASS
    # Settlement arithmetic is a downstream reconciliation result. Its delta is
    # evidence, but contributes zero additional leakage to avoid double-counting
    # primary fee and tax violations.
    return _result(
        prefix="SETTLEMENT",
        event=event,
        control=control,
        target_type="SETTLEMENT",
        target_id=event.external_id,
        outcome=outcome,
        expected=expected,
        actual=actual,
        tolerance=parameters.tolerance,
        difference=difference,
        impact=Decimal("0"),
        evidence={
            "settlement_event_id": event.id,
            "components": components,
            "calculation": "SUM(APPROVED_PAYMENT_NETS) - SUM(REFUND_PRINCIPALS)",
            "authority": "DETERMINISTIC",
            "lineage": LineageType.DOWNSTREAM.value,
            "counts_toward_verified_leakage": False,
            "financial_impact_policy": "EXCLUDE_DOWNSTREAM_DUPLICATE",
            "decision_reason": (
                "INCOMPLETE_SETTLEMENT_EVIDENCE" if unresolved else "DECIMAL_COMPARE"
            ),
        },
        snapshots=_snapshot_ids(event, *contributors),
        violation_category="Settlement arithmetic deviation",
        violation_expected=str(expected) if expected is not None else "UNRESOLVED",
        violation_actual=str(actual),
        fingerprint_parts=(
            expected,
            actual,
            parameters.tolerance,
            tuple(sorted(item.id for item in contributors)),
        ),
    )
