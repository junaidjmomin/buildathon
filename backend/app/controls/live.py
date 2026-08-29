from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
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
    ControlType,
    EvaluationStatus,
    FinancialEvent,
    LineageType,
    Violation,
)

#: Canonical violation taxonomy, derived from control semantics. Each entry
#: maps a deterministic check to its published violation type and native
#: entity. Never keyed on identifiers or dataset-specific values.
VIOLATION_TYPES: dict[str, tuple[str, str]] = {
    "MDR_RATE": ("MDR_RATE", "PAYMENT"),
    "GST_ON_FEE": ("GST_ON_FEE", "PAYMENT"),
    "SETTLEMENT_SLA": ("SETTLEMENT_SLA", "PAYMENT"),
    "REFUND_EXCEEDS_PAYMENT": ("REFUND_EXCEEDS_PAYMENT", "PAYMENT"),
    "DUPLICATE_REFUND_DEDUCTION": ("DUPLICATE_REFUND_DEDUCTION", "PAYMENT"),
    "UNSUPPORTED_REFUND_FEE": ("UNSUPPORTED_REFUND_FEE", "PAYMENT"),
    "UNDECLARED_REFUND": ("UNDECLARED_REFUND", "PAYMENT"),
    "SETTLEMENT_ARITHMETIC": ("SETTLEMENT_ARITHMETIC", "SETTLEMENT"),
    "MISSING_BANK_SETTLEMENT": ("MISSING_BANK_SETTLEMENT", "SETTLEMENT"),
}

#: The deterministic claim surface of each control family: the canonical
#: violation types a control of that type is able to raise. Accountability for
#: a failure mode follows from this map plus the control's registry status —
#: a mode claimed by an APPROVED control is one the live suite must catch, a
#: mode claimed only by a DRAFT candidate is a governed-but-unapproved blind
#: spot, and a mode claimed by no control at all is a registry gap. None of
#: these are execution failures of the approved suite.
CLAIMED_VIOLATION_TYPES: dict[ControlType, frozenset[str]] = {
    ControlType.MDR_RATE: frozenset({"MDR_RATE"}),
    ControlType.GST_ON_FEE: frozenset({"GST_ON_FEE"}),
    ControlType.SETTLEMENT_SLA: frozenset({"SETTLEMENT_SLA"}),
    ControlType.REFUND_INTEGRITY: frozenset(
        {
            "REFUND_EXCEEDS_PAYMENT",
            "DUPLICATE_REFUND_DEDUCTION",
            "UNSUPPORTED_REFUND_FEE",
            "UNDECLARED_REFUND",
        }
    ),
    ControlType.SETTLEMENT_ARITHMETIC: frozenset(
        {"SETTLEMENT_ARITHMETIC", "MISSING_BANK_SETTLEMENT"}
    ),
    ControlType.UNSUPPORTED_FEE: frozenset({"UNSUPPORTED_FEE"}),
}


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
    #: Discriminates distinct deterministic checks executed by the same
    #: control on the same target (settlement arithmetic vs missing-bank
    #: evidence). Defaults to the canonical violation type.
    check_name: str = ""


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
        # The approved controls' conditions require ``status == captured``:
        # processing fees and GST are only contracted for captured payments,
        # so non-captured payments are out of the controls' applicability.
        captured = _is_captured_payment(payment)
        if mdr is not None and _is_card_payment(payment) and captured:
            evaluations.append(_evaluate_mdr(payment, mdr))
        if gst is not None and _is_card_payment(payment) and captured:
            evaluations.append(_evaluate_gst(payment, gst, mdr))
        if sla is not None and captured:
            evaluations.append(
                _evaluate_sla(
                    payment,
                    sla,
                    outgoing=outgoing,
                    event_by_id=event_by_id,
                )
            )
        if refund is not None and captured:
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
    bank_credits = sorted(
        (event for event in events if event.event_type == "BANK_CREDIT"),
        key=lambda event: event.id,
    )
    statement_window_end = max((bank.timestamp for bank in bank_credits), default=None)
    # Banks already credited to a settlement are resolved evidence; only the
    # unmatched ones can be ambiguity candidates for an unmatched settlement.
    credited_bank_ids = {edge.to_event_id for edge in edges if edge.relationship == "CREDITED_AS"}
    unmatched_banks = [bank for bank in bank_credits if bank.id not in credited_bank_ids]
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
                    outgoing=outgoing,
                    event_by_id=event_by_id,
                )
            )
        # Clause 6.2: the settlement "and corresponding bank credit" must
        # reconcile. A settlement with no bank-credit evidence at all, after
        # deterministic matching, is a missing bank settlement — but only
        # when the bank statement window proves the credit had time to post
        # and no unmatched bank credit could plausibly correspond to it
        # (an amount-compatible unmatched credit means matching ambiguity,
        # not absence).
        if arithmetic is not None and not _has_bank_evidence(settlement, outgoing, event_by_id):
            evaluations.append(
                _evaluate_missing_bank(
                    settlement,
                    arithmetic,
                    controls=controls,
                    bank_credits=unmatched_banks,
                    statement_window_end=statement_window_end,
                )
            )
    return evaluations


def _has_bank_evidence(
    settlement: FinancialEvent,
    outgoing: dict[tuple[str, str], list[CanonicalEventEdge]],
    event_by_id: dict[str, FinancialEvent],
) -> bool:
    """True when a CREDITED_AS edge from this settlement exists.

    The CREDITED_AS edge runs settlement -> bank credit, so evidence is found
    in the settlement's outgoing edges.
    """

    for edge in outgoing.get((settlement.id, "CREDITED_AS"), []):
        bank = event_by_id.get(edge.to_event_id)
        if bank is not None and bank.event_type == "BANK_CREDIT":
            return True
    return False


def _effective_sla_days(controls: list[Control], at: date) -> int | None:
    sla = _effective_control(controls, "CAPTURE_TO_SETTLEMENT_SLA", at)
    if sla is None:
        return None
    days = sla.parameters.get("business_days")
    return days if isinstance(days, int) and days >= 0 else None


def _evaluate_missing_bank(
    settlement: FinancialEvent,
    control: Control,
    *,
    controls: list[Control],
    bank_credits: list[FinancialEvent],
    statement_window_end: datetime | None,
) -> LiveControlEvaluation:
    """A settlement whose corresponding bank credit is entirely absent.

    Two evidence guards must both hold before absence is concluded:

    1. The bank statement window extends beyond the settlement date plus the
       SLA business days, proving the credit had time to post.
    2. No unmatched bank credit carries an amount compatible with the
       settlement — a compatible unmatched credit means deterministic
       matching could not resolve the pairing (ambiguity), not that the
       credit is missing.
    """

    parameters = SettlementArithmeticParameters.model_validate(control.parameters)
    guard_days = _effective_sla_days(controls, settlement.timestamp.date())
    if guard_days is None:
        guard_days = 0
    latest_expected = add_business_days(settlement.timestamp, guard_days)
    # No bank statement at all means no evidence either way: absence of a
    # credit cannot be concluded from an empty statement.
    within_window = statement_window_end is not None and statement_window_end >= latest_expected
    compatible = [
        bank
        for bank in bank_credits
        if abs(bank.amount - settlement.amount) <= parameters.tolerance
    ]
    ambiguous = bool(compatible)
    unresolved = not within_window or ambiguous or settlement.status == "unresolved"
    if unresolved:
        outcome = EvaluationStatus.UNRESOLVED
    else:
        outcome = EvaluationStatus.VIOLATION
    exposure = settlement.amount
    return _result(
        prefix="MISSINGBANK",
        event=settlement,
        control=control,
        target_type="SETTLEMENT",
        target_id=settlement.external_id,
        outcome=outcome,
        expected=exposure,
        actual=Decimal("0"),
        tolerance=Decimal("0"),
        difference=exposure if outcome == EvaluationStatus.VIOLATION else None,
        impact=Decimal("0"),
        evidence={
            "settlement_event_id": settlement.id,
            "decision_reason": (
                "BANK_STATEMENT_WINDOW_CLOSED_BEFORE_SLA"
                if not within_window
                else ("AMBIGUOUS_BANK_MATCH_CANDIDATES" if ambiguous else "NO_BANK_CREDIT_EVIDENCE")
            ),
            "statement_window_end": (
                statement_window_end.isoformat() if statement_window_end else None
            ),
            "latest_expected_credit_at": latest_expected.isoformat(),
            "compatible_unmatched_bank_event_ids": [bank.id for bank in compatible],
            "cash_exposure": str(exposure),
            "authority": "DETERMINISTIC",
            "lineage": LineageType.PRIMARY.value,
            "counts_toward_verified_leakage": False,
            "financial_impact_policy": "CASH_EXPOSURE_NOT_LEAKAGE",
        },
        snapshots=_snapshot_ids(settlement),
        violation_category="Missing bank settlement",
        violation_expected=str(exposure),
        violation_actual="0",
        fingerprint_parts=(exposure, statement_window_end, guard_days),
        violation_type="MISSING_BANK_SETTLEMENT",
    )


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
    violation_type: str = "",
) -> LiveControlEvaluation:
    fingerprint = _fingerprint(
        event.id,
        control.id,
        control.version,
        target_type,
        target_id,
        *fingerprint_parts,
    )
    # Every caller resolves its control with ``_effective_control`` against the
    # target event's own date, so the evaluation can state on the record which
    # date put this version in force. Recording it makes version selection
    # auditable instead of merely trusted: an evaluation whose date falls
    # outside the recorded window is a defect anyone can see.
    evidence = {
        **evidence,
        "control_version_selection": {
            "logical_control_key": control.logical_control_key,
            "control_version": control.version,
            "effective_from": control.effective_from.isoformat(),
            "effective_to": (
                control.effective_to.isoformat() if control.effective_to is not None else None
            ),
            "selected_on": event.timestamp.date().isoformat(),
            "basis": "TARGET_EVENT_TIMESTAMP",
        },
    }
    violation = None
    if outcome == EvaluationStatus.VIOLATION:
        taxonomy = VIOLATION_TYPES.get(violation_type)
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
            violation_type=violation_type,
            target_type=taxonomy[1] if taxonomy else target_type,
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
        check_name=violation_type or control.control_type.value,
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
        violation_type="MDR_RATE",
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
        violation_type="GST_ON_FEE",
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
    # Clause 6.1 asks when *this payment* was settled. A settlement batch
    # aggregates many rows and carries the latest of their timestamps, so the
    # batch timestamp would penalise a payment that the source declares as
    # settled earlier within the same batch. Prefer the payment's own declared
    # settled_at when the settlement source itemizes per-payment rows.
    settled_at = settlement.timestamp if settlement is not None else None
    settled_at_basis = "SETTLEMENT_EVENT_TIMESTAMP"
    if settlement is not None:
        components = settlement.normalized_payload.get("payment_components")
        own = components.get(event.external_id) if isinstance(components, dict) else None
        declared = _parse_timestamp(own.get("settled_at")) if isinstance(own, dict) else None
        if declared is not None:
            settled_at = _align_timezone(declared, settlement.timestamp)
            settled_at_basis = "PAYMENT_SETTLEMENT_ROW"
    due_at = add_business_days(event.timestamp, days) if days is not None else None
    delay_days = (
        business_days_late(due_at, settled_at)
        if due_at is not None and settled_at is not None
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
            "settled_at": settled_at.isoformat() if settled_at is not None else None,
            "settled_at_basis": settled_at_basis,
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
        violation_actual=(settled_at.isoformat() if settled_at is not None else "UNRESOLVED"),
        fingerprint_parts=(event.timestamp, due_at, settled_at),
        violation_type="SETTLEMENT_SLA",
    )


def _parse_timestamp(value: object) -> datetime | None:
    """Parse a declared ISO timestamp from a source row, if it is one."""

    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.strip())
    except ValueError:
        return None


def _align_timezone(value: datetime, reference: datetime) -> datetime:
    """Give a naive declared timestamp the same awareness as the canonical one.

    Source rows may omit an offset while canonical events carry one. Comparing
    the two directly would raise, so the declared value adopts the reference's
    timezone (the canonicalizer applied that same timezone to this very row).
    """

    if value.tzinfo is None and reference.tzinfo is not None:
        return value.replace(tzinfo=reference.tzinfo)
    if value.tzinfo is not None and reference.tzinfo is None:
        return value.replace(tzinfo=None)
    return value


def _payment_settlement_components(
    payment: FinancialEvent,
    *,
    outgoing: dict[tuple[str, str], list[CanonicalEventEdge]],
    event_by_id: dict[str, FinancialEvent],
) -> dict[str, Any] | None:
    """The payment's own settlement-row components, if the source carries them.

    Settlement sources that itemize per-payment rows persist those components
    on the settlement event (keyed by contributing payment id) during
    canonicalization. The refund-deduction check uses only these declared
    values; nothing is inferred. The INCLUDED_IN edge runs payment ->
    settlement, so it is found in the payment's outgoing edges.
    """

    for edge in outgoing.get((payment.id, "INCLUDED_IN"), []):
        settlement = event_by_id.get(edge.to_event_id)
        if settlement is None or settlement.event_type != "SETTLEMENT":
            continue
        components = settlement.normalized_payload.get("payment_components")
        if isinstance(components, dict):
            own = components.get(payment.external_id)
            if isinstance(own, dict):
                return own
    return None


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
    # The settlement row declares how much refund principal was actually
    # deducted from the merchant's payout for this payment.
    components = _payment_settlement_components(event, outgoing=outgoing, event_by_id=event_by_id)
    deducted = _decimal_string(components.get("refund_adjustment")) if components else None

    # Deterministic sub-checks against clause 7.2 semantics:
    # 1. REFUND_EXCEEDS_PAYMENT: refunded principal above the payment amount.
    exceeds_by = (
        money(linked_total - event.amount)
        if linked_total > event.amount + tolerance
        else Decimal("0")
    )
    # 2. DUPLICATE_REFUND_DEDUCTION: principal deducted more than once.
    duplicate_by = (
        money(deducted - linked_total)
        if deducted is not None and deducted - linked_total > tolerance
        else Decimal("0")
    )
    # 3. Over-declared refund total on the payment record.
    over_declared = money(linked_total - declared) if declared is not None else None

    difference = (
        money(
            max(over_declared or Decimal("0"), Decimal("0")) + total_fee + exceeds_by + duplicate_by
        )
        if over_declared is not None or exceeds_by or duplicate_by
        else None
    )
    unresolved = (
        declared is None
        or invalid_fee
        or event.status == "unresolved"
        or (declared > linked_total and declared > 0)
    )
    violated = declared is not None and (
        exceeds_by > Decimal("0")
        or duplicate_by > Decimal("0")
        or linked_total - declared > tolerance
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
    # Clause 7.2 carries several distinct obligations. The canonical type names
    # the one that failed, in order of financial severity, so a finding is never
    # mislabelled as a duplicate deduction when the real failure was an
    # unsupported refund fee or an under-declared refund total.
    if exceeds_by > Decimal("0"):
        violation_type = "REFUND_EXCEEDS_PAYMENT"
    elif duplicate_by > Decimal("0"):
        violation_type = "DUPLICATE_REFUND_DEDUCTION"
    elif total_fee - parameters.refund_fee > tolerance:
        violation_type = "UNSUPPORTED_REFUND_FEE"
    else:
        violation_type = "UNDECLARED_REFUND"
    category = {
        "REFUND_EXCEEDS_PAYMENT": "Refund exceeds payment principal",
        "DUPLICATE_REFUND_DEDUCTION": "Duplicate refund deduction",
        "UNSUPPORTED_REFUND_FEE": "Unsupported refund fee",
        "UNDECLARED_REFUND": "Refund principal integrity deviation",
    }[violation_type]
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
            "settlement_refund_deduction": str(deducted) if deducted is not None else None,
            "refund_exceeds_payment_by": str(exceeds_by),
            "duplicate_refund_deduction_by": str(duplicate_by),
            "authority": "DETERMINISTIC",
            "decision_reason": (
                "INCOMPLETE_REFUND_EVIDENCE" if unresolved else "REFUND_PRINCIPAL_AND_FEE_COMPARE"
            ),
        },
        snapshots=_snapshot_ids(event, *refunds),
        violation_category=category,
        violation_expected=str(declared) if declared is not None else "UNRESOLVED",
        violation_actual=str(money(linked_total + total_fee)),
        fingerprint_parts=(
            declared,
            linked_total,
            total_fee,
            deducted,
            parameters.refund_fee,
            tolerance,
        ),
        violation_type=violation_type,
    )


def _evaluate_settlement_arithmetic(
    event: FinancialEvent,
    control: Control,
    *,
    controls: list[Control],
    incoming: dict[tuple[str, str], list[CanonicalEventEdge]],
    outgoing: dict[tuple[str, str], list[CanonicalEventEdge]],
    event_by_id: dict[str, FinancialEvent],
) -> LiveControlEvaluation:
    parameters = SettlementArithmeticParameters.model_validate(control.parameters)
    related_edges = incoming.get((event.id, "INCLUDED_IN"), [])
    contributors = [
        event_by_id[edge.from_event_id]
        for edge in related_edges
        if edge.from_event_id in event_by_id
    ]
    contributor_ids = {contributor.id for contributor in contributors}
    expected = Decimal("0")
    complete = bool(contributors)
    components: list[dict[str, str]] = []
    contributor_deltas: list[dict[str, str]] = []
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
        # A non-captured payment must never be settled; it cannot contribute
        # contractually valid fee/tax arithmetic, so the settlement evidence
        # is incomplete rather than silently accepted.
        if not _is_captured_payment(contributor):
            complete = False
            continue
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
        # Refund principals linked to this payment reduce the expected payout
        # (clause 6.2: net of approved fee, valid GST and valid refunds).
        # Refund events already itemized as settlement contributors (some
        # sources link refunds directly to settlements) are excluded so the
        # principal is never subtracted twice.
        refund_principal = money(
            sum(
                (
                    refund.amount
                    for edge in outgoing.get((contributor.id, "REFUNDED_BY"), [])
                    if (refund := event_by_id.get(edge.to_event_id)) is not None
                    and refund.event_type == "REFUND"
                    and refund.id not in contributor_ids
                ),
                Decimal("0"),
            )
        )
        expected -= refund_principal
        if refund_principal > Decimal("0"):
            components.append(
                {
                    "event_id": contributor.id,
                    "type": "REFUND_PRINCIPAL",
                    "amount": str(-refund_principal),
                }
            )
        # Per-contributor declared-vs-approved delta: the raw material for
        # residual leakage attribution in lineage resolution. The declared
        # net comes from the settlement's per-payment components when the
        # source itemizes them.
        declared_net = None
        raw_components = event.normalized_payload.get("payment_components")
        if isinstance(raw_components, dict):
            own = raw_components.get(contributor.external_id)
            if isinstance(own, dict):
                declared_net = _decimal_string(own.get("net_amount"))
        if declared_net is not None:
            contributor_deltas.append(
                {
                    "event_id": contributor.id,
                    "declared_net": str(declared_net),
                    "approved_net": str(money(net - refund_principal)),
                    "delta": str(money(declared_net - (net - refund_principal))),
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
            "contributor_deltas": contributor_deltas,
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
        violation_type="SETTLEMENT_ARITHMETIC",
    )
