from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.controls.engine import DOMESTIC_MDR_RATE, evaluate_payment
from app.core.money import add_business_days, expected_fee, expected_gst, money
from app.domain.models import PaymentLifecycle

DEMO_SEED = 20260825
KNOWN_PAYMENT_ID = "PAY_82HD9"


@dataclass(frozen=True)
class SyntheticDataset:
    payments: list[PaymentLifecycle]
    ground_truth: dict[str, str]
    counts: dict[str, int]


def _scenario(index: int) -> str:
    if index < 25:
        return "MDR_RATE_DEVIATION"
    if index < 33:
        return "INCORRECT_GST"
    if index < 38:
        return "DUPLICATE_REFUND"
    if index < 48:
        return "SETTLEMENT_SLA"
    if index < 56:
        return "UNSUPPORTED_FEE"
    if index < 61:
        return "UNRESOLVED"
    return "PASS"


def generate_dataset(seed: int = DEMO_SEED, payment_count: int = 500) -> SyntheticDataset:
    if payment_count < 61:
        raise ValueError("The full demo requires at least 61 payments")
    rng = random.Random(seed)
    base = datetime(2026, 8, 17, 9, 30, tzinfo=timezone.utc)
    payments: list[PaymentLifecycle] = []
    ground_truth: dict[str, str] = {}

    for index in range(payment_count):
        scenario = _scenario(index)
        payment_id = KNOWN_PAYMENT_ID if index == 0 else f"PAY_{index:04d}"
        amount = Decimal("10000.00") if index == 0 else money(rng.randint(800, 85000))
        captured_at = base + timedelta(minutes=index * 47)
        contracted_fee = expected_fee(amount, DOMESTIC_MDR_RATE)
        contracted_tax = expected_gst(contracted_fee)
        actual_fee = contracted_fee
        actual_tax = contracted_tax
        refund_amount = Decimal("0")
        refund_deduction = Decimal("0")
        unsupported_fee = Decimal("0")
        settled_at = add_business_days(captured_at, 2)

        if scenario == "MDR_RATE_DEVIATION":
            actual_fee = expected_fee(amount, Decimal("0.0175"))
            actual_tax = expected_gst(actual_fee)
        elif scenario == "INCORRECT_GST":
            actual_tax = expected_gst(contracted_fee, Decimal("0.20"))
        elif scenario == "DUPLICATE_REFUND":
            refund_amount = money(min(amount / Decimal("5"), Decimal("2500")))
            refund_deduction = money(refund_amount * 2)
        elif scenario == "SETTLEMENT_SLA":
            settled_at = add_business_days(captured_at, 5)
        elif scenario == "UNSUPPORTED_FEE":
            unsupported_fee = Decimal("49.00")

        actual_net = money(
            amount - actual_fee - actual_tax - refund_deduction - unsupported_fee
        )
        bank_credit = None if scenario == "UNRESOLVED" else actual_net
        payment = PaymentLifecycle(
            payment_id=payment_id,
            order_id=f"ORD_{index:04d}",
            settlement_id=f"SET_{index // 6:03d}",
            bank_txn_id=None if bank_credit is None else f"BANK_{index // 6:03d}",
            amount=amount,
            payment_method="card",
            card_network="Visa" if index % 3 else "Mastercard",
            card_scope="domestic",
            captured_at=captured_at,
            actual_fee=actual_fee,
            actual_tax=actual_tax,
            refund_amount=refund_amount,
            refund_deduction=refund_deduction,
            unsupported_fee=unsupported_fee,
            settled_at=settled_at,
            actual_net=actual_net,
            bank_credit=bank_credit,
        )
        payments.append(payment)
        ground_truth[payment_id] = scenario

    # The famous demo transaction must remain exact and independently inspectable.
    known = payments[0]
    assert known.actual_fee == Decimal("175.00")
    assert known.actual_tax == Decimal("31.50")
    assert evaluate_payment(known).leakage == Decimal("23.60")
    return SyntheticDataset(
        payments=payments,
        ground_truth=ground_truth,
        counts={
            "orders": payment_count,
            "payments": payment_count,
            "settlements": len({payment.settlement_id for payment in payments}),
            "bank_entries": len(
                {payment.bank_txn_id for payment in payments if payment.bank_txn_id}
            ),
            "refunds": sum(1 for payment in payments if payment.refund_amount > 0),
            "chargebacks": 6,
        },
    )

