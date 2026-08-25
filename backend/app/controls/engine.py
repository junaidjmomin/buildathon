from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.core.money import add_business_days, business_days_late, expected_fee, expected_gst, money
from app.domain.models import ControlType, EvaluationStatus, PaymentLifecycle
from app.services.governance import governance

DOMESTIC_MDR_RATE = Decimal("0.0155")
GST_RATE = Decimal("0.18")
TOLERANCE = Decimal("0.01")


@dataclass(frozen=True)
class PaymentEvaluation:
    expected_fee: Decimal
    expected_tax: Decimal
    expected_refund: Decimal
    expected_net: Decimal
    fee_status: EvaluationStatus
    tax_status: EvaluationStatus
    net_status: EvaluationStatus
    bank_status: EvaluationStatus
    leakage: Decimal
    delay_days: int


def evaluate_payment(
    payment: PaymentLifecycle, *, mdr_rate: Decimal | None = None
) -> PaymentEvaluation:
    if mdr_rate is None:
        control = governance.effective_control("DOMESTIC_CARD_MDR", payment.captured_at.date())
        mdr_rate = Decimal(str(control.parameters["rate"]))
    fee = expected_fee(payment.amount, mdr_rate)
    tax = expected_gst(fee, GST_RATE)
    expected_refund = payment.refund_amount
    expected_net = money(payment.amount - fee - tax - expected_refund)
    fee_difference = money(payment.actual_fee - fee)
    tax_difference = money(payment.actual_tax - tax)
    refund_difference = money(payment.refund_deduction - expected_refund)
    unsupported = money(payment.unsupported_fee)
    leakage = money(
        max(fee_difference, Decimal("0"))
        + max(tax_difference, Decimal("0"))
        + max(refund_difference, Decimal("0"))
        + max(unsupported, Decimal("0"))
    )
    fee_status = (
        EvaluationStatus.PASS if abs(fee_difference) <= TOLERANCE else EvaluationStatus.VIOLATION
    )
    tax_status = (
        EvaluationStatus.PASS if abs(tax_difference) <= TOLERANCE else EvaluationStatus.VIOLATION
    )
    net_status = (
        EvaluationStatus.PASS
        if abs(payment.actual_net - expected_net) <= TOLERANCE
        else EvaluationStatus.VIOLATION
    )
    if payment.bank_credit is None:
        bank_status = EvaluationStatus.UNRESOLVED
    elif abs(payment.bank_credit - expected_net) <= TOLERANCE:
        bank_status = EvaluationStatus.PASS
    else:
        bank_status = EvaluationStatus.VIOLATION
    due_at = add_business_days(payment.captured_at, 2)
    delay_days = business_days_late(due_at, payment.settled_at)
    return PaymentEvaluation(
        expected_fee=fee,
        expected_tax=tax,
        expected_refund=expected_refund,
        expected_net=expected_net,
        fee_status=fee_status,
        tax_status=tax_status,
        net_status=net_status,
        bank_status=bank_status,
        leakage=leakage,
        delay_days=delay_days,
    )


def triggered_control_types(
    payment: PaymentLifecycle, *, unsupported_fee_control: bool = False
) -> set[ControlType]:
    """Run the approved deterministic controls and return the violated types."""
    result = evaluate_payment(payment)
    triggered: set[ControlType] = set()
    if result.fee_status == EvaluationStatus.VIOLATION:
        triggered.add(ControlType.MDR_RATE)
    if result.tax_status == EvaluationStatus.VIOLATION:
        triggered.add(ControlType.GST_ON_FEE)
    if result.delay_days > 0:
        triggered.add(ControlType.SETTLEMENT_SLA)
    if payment.refund_deduction > payment.refund_amount or payment.refund_amount > payment.amount:
        triggered.add(ControlType.REFUND_INTEGRITY)
    if payment.status != "captured" and payment.settlement_id:
        triggered.add(ControlType.LIFECYCLE_VALIDITY)
    if payment.chargeback_fee_deductions > 1:
        triggered.add(ControlType.LIFECYCLE_VALIDITY)
    if unsupported_fee_control and payment.unsupported_fee > 0:
        triggered.add(ControlType.UNSUPPORTED_FEE)
    return triggered
