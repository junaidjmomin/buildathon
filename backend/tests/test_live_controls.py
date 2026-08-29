from datetime import datetime, timezone
from decimal import Decimal

from app.controls.live import build_live_control_evaluations
from app.domain.models import CanonicalEventEdge, ControlType, EvaluationStatus
from app.integrations.razorpay.mapper import map_payment, map_refund, map_settlement
from app.integrations.razorpay.schemas import PaymentItem, RefundItem, SettlementItem
from app.integrations.razorpay.sync import (
    IncompleteControlRegistryError,
    _validate_live_control_registry,
)
from app.services.governance import CONTROLS


def test_production_control_registry_requires_every_authoritative_live_control() -> None:
    _validate_live_control_registry(CONTROLS)
    incomplete = [
        control
        for control in CONTROLS
        if control.logical_control_key != "SETTLEMENT_BANK_ARITHMETIC"
    ]
    try:
        _validate_live_control_registry(incomplete)
    except IncompleteControlRegistryError as exc:
        assert "SETTLEMENT_BANK_ARITHMETIC" in str(exc)
    else:
        raise AssertionError("An incomplete production control registry must fail closed")


def _payment(
    *,
    payment_id: str = "pay_live_1",
    amount: int = 1_000_000,
    amount_refunded: int = 0,
    fee: int = 17_500,
    tax: int = 3_150,
    created_at: int | None = None,
):
    created = created_at or int(datetime(2026, 8, 3, 10, tzinfo=timezone.utc).timestamp())
    return map_payment(
        PaymentItem.model_validate(
            {
                "id": payment_id,
                "amount": amount,
                "currency": "INR",
                "status": "captured",
                "method": "card",
                "international": False,
                "captured": True,
                "amount_refunded": amount_refunded,
                "fee": fee,
                "tax": tax,
                "created_at": created,
            }
        ),
        run_id="RUN_LIVE",
        sync_id="SYNC_LIVE",
    )


def _by_control(evaluations):
    return {evaluation.control.control_type: evaluation for evaluation in evaluations}


def _by_violation_type(evaluations, violation_type):
    """Select the evaluation of a specific deterministic check.

    One control can execute several checks on the same target (settlement
    arithmetic and missing-bank evidence), so control type alone is not a
    unique key.
    """

    return next(
        evaluation
        for evaluation in evaluations
        if evaluation.violation is not None
        and evaluation.violation.violation_type == violation_type
    )


def test_live_suite_evaluates_mdr_gst_and_marks_missing_settlement_unresolved() -> None:
    evaluations = build_live_control_evaluations([_payment()], [], CONTROLS)
    by_control = _by_control(evaluations)

    mdr = by_control[ControlType.MDR_RATE]
    assert mdr.outcome == EvaluationStatus.VIOLATION
    assert mdr.expected_amount == Decimal("155.00")
    assert mdr.actual_amount == Decimal("175.00")
    assert mdr.financial_impact == Decimal("20.00")

    gst = by_control[ControlType.GST_ON_FEE]
    assert gst.outcome == EvaluationStatus.VIOLATION
    assert gst.expected_amount == Decimal("27.90")
    assert gst.actual_amount == Decimal("31.50")
    assert gst.financial_impact == Decimal("3.60")

    assert by_control[ControlType.SETTLEMENT_SLA].outcome == EvaluationStatus.UNRESOLVED
    assert by_control[ControlType.REFUND_INTEGRITY].outcome == EvaluationStatus.PASS


def test_live_suite_rejects_binary_float_money_as_unresolved() -> None:
    payment = _payment().model_copy(deep=True)
    payment.normalized_payload["fee"] = 175.0
    evaluations = build_live_control_evaluations([payment], [], CONTROLS)

    mdr = _by_control(evaluations)[ControlType.MDR_RATE]
    assert mdr.outcome == EvaluationStatus.UNRESOLVED
    assert mdr.actual_amount is None
    assert mdr.evidence["decision_reason"] == "MISSING_OR_AMBIGUOUS_INPUT"


def test_live_suite_proves_settlement_sla_with_business_day_evidence() -> None:
    captured_at = datetime(2026, 8, 3, 10, tzinfo=timezone.utc)
    settled_at = datetime(2026, 8, 10, 10, tzinfo=timezone.utc)
    payment = _payment(created_at=int(captured_at.timestamp()))
    settlement = map_settlement(
        SettlementItem.model_validate(
            {
                "id": "set_live_1",
                "amount": 976_350,
                "status": "processed",
                "created_at": int(settled_at.timestamp()),
            }
        ),
        run_id="RUN_LIVE",
        sync_id="SYNC_LIVE",
    )
    edge = CanonicalEventEdge(
        id="edge:included",
        run_id="RUN_LIVE",
        from_event_id=payment.id,
        to_event_id=settlement.id,
        relationship="INCLUDED_IN",
        confidence=Decimal("1"),
        method="EXACT",
        evidence={"source": "test"},
    )

    evaluations = build_live_control_evaluations([payment, settlement], [edge], CONTROLS)
    sla = _by_control(evaluations)[ControlType.SETTLEMENT_SLA]
    assert sla.outcome == EvaluationStatus.VIOLATION
    assert sla.difference_amount == Decimal("3")
    assert sla.evidence["due_at"] == "2026-08-05T10:00:00+00:00"
    assert sla.evidence["settled_at"] == "2026-08-10T10:00:00+00:00"
    assert sla.financial_impact == Decimal("0")


def test_live_suite_detects_refund_principal_over_deduction() -> None:
    payment = _payment(amount=100_000, amount_refunded=10_000, fee=1_550, tax=279)
    refunds = []
    edges = []
    for refund_id in ("rfnd_live_1", "rfnd_live_2"):
        refund, edge = map_refund(
            RefundItem.model_validate(
                {
                    "id": refund_id,
                    "amount": 10_000,
                    "currency": "INR",
                    "payment_id": payment.external_id,
                    "created_at": int(payment.timestamp.timestamp()) + 60,
                    "status": "processed",
                }
            ),
            run_id="RUN_LIVE",
            sync_id="SYNC_LIVE",
        )
        refunds.append(refund)
        edges.append(edge)

    evaluations = build_live_control_evaluations([payment, *refunds], edges, CONTROLS)
    refund_result = _by_control(evaluations)[ControlType.REFUND_INTEGRITY]
    assert refund_result.outcome == EvaluationStatus.VIOLATION
    assert refund_result.expected_amount == Decimal("100.00")
    assert refund_result.actual_amount == Decimal("200.00")
    assert refund_result.financial_impact == Decimal("100.00")


def test_settlement_arithmetic_is_downstream_and_does_not_double_count_leakage() -> None:
    payment = _payment(amount=100_000, fee=1_750, tax=315)
    settlement = map_settlement(
        SettlementItem.model_validate(
            {
                "id": "set_live_2",
                "amount": 97_935,
                "status": "processed",
                "created_at": int(payment.timestamp.timestamp()) + 3600,
            }
        ),
        run_id="RUN_LIVE",
        sync_id="SYNC_LIVE",
    )
    edge = CanonicalEventEdge(
        id="edge:included:2",
        run_id="RUN_LIVE",
        from_event_id=payment.id,
        to_event_id=settlement.id,
        relationship="INCLUDED_IN",
        confidence=Decimal("1"),
        method="EXACT",
        evidence={"source": "test"},
    )

    evaluations = build_live_control_evaluations([payment, settlement], [edge], CONTROLS)
    arithmetic = _by_violation_type(evaluations, "SETTLEMENT_ARITHMETIC")
    assert arithmetic.outcome == EvaluationStatus.VIOLATION
    assert arithmetic.expected_amount == Decimal("981.71")
    assert arithmetic.actual_amount == Decimal("979.35")
    assert arithmetic.difference_amount == Decimal("-2.36")
    assert arithmetic.financial_impact == Decimal("0")
    assert arithmetic.evidence["lineage"] == "DOWNSTREAM"
    assert arithmetic.evidence["counts_toward_verified_leakage"] is False
    assert arithmetic.evidence["financial_impact_policy"] == "EXCLUDE_DOWNSTREAM_DUPLICATE"
