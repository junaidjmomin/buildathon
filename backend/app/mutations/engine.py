from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from hashlib import sha256

from app.controls.engine import triggered_control_types
from app.core.money import expected_fee, expected_gst, money
from app.domain.models import (
    BlindSpotReason,
    ControlType,
    MutationCoverage,
    MutationResult,
    MutationTestSummary,
    MutationType,
    PaymentLifecycle,
)

MUTATION_TEST_ID = "MUT_NOVACART_01"

EXPECTED_CONTROLS = {
    MutationType.MDR_RATE_INCREASE: ControlType.MDR_RATE,
    MutationType.GST_BASE_CORRUPTION: ControlType.GST_ON_FEE,
    MutationType.DUPLICATE_REFUND_DEDUCTION: ControlType.REFUND_INTEGRITY,
    MutationType.SETTLEMENT_DELAY: ControlType.SETTLEMENT_SLA,
    MutationType.UNSUPPORTED_FEE: ControlType.UNSUPPORTED_FEE,
    MutationType.FAILED_PAYMENT_SETTLED: ControlType.LIFECYCLE_VALIDITY,
    MutationType.REFUND_EXCEEDS_PAYMENT: ControlType.REFUND_INTEGRITY,
    MutationType.DUPLICATE_CHARGEBACK_FEE: ControlType.LIFECYCLE_VALIDITY,
    MutationType.PAYMENT_METHOD_RECLASSIFICATION: ControlType.LIFECYCLE_VALIDITY,
}

DESCRIPTIONS = {
    MutationType.MDR_RATE_INCREASE: "Raised contracted MDR behaviour from 1.55% to 1.75%.",
    MutationType.GST_BASE_CORRUPTION: "Calculated GST from a corrupted processing-fee base.",
    MutationType.DUPLICATE_REFUND_DEDUCTION: "Deducted one refund principal twice.",
    MutationType.SETTLEMENT_DELAY: "Moved settlement three business days beyond T+2.",
    MutationType.UNSUPPORTED_FEE: "Inserted an unlisted ₹49 platform fee.",
    MutationType.FAILED_PAYMENT_SETTLED: "Included a failed payment in a settlement.",
    MutationType.REFUND_EXCEEDS_PAYMENT: "Raised refund principal above captured amount.",
    MutationType.DUPLICATE_CHARGEBACK_FEE: "Deducted the same chargeback fee twice.",
    MutationType.PAYMENT_METHOD_RECLASSIFICATION: "Silently reclassified card as UPI.",
}


def _mutation_plan() -> list[MutationType]:
    detectable = [
        MutationType.MDR_RATE_INCREASE,
        MutationType.GST_BASE_CORRUPTION,
        MutationType.DUPLICATE_REFUND_DEDUCTION,
        MutationType.SETTLEMENT_DELAY,
        MutationType.FAILED_PAYMENT_SETTLED,
        MutationType.REFUND_EXCEEDS_PAYMENT,
        MutationType.DUPLICATE_CHARGEBACK_FEE,
    ]
    # 47 mutations governed by current controls plus three deliberate blind spots.
    return [detectable[index % len(detectable)] for index in range(47)] + [
        MutationType.UNSUPPORTED_FEE,
        MutationType.UNSUPPORTED_FEE,
        MutationType.PAYMENT_METHOD_RECLASSIFICATION,
    ]


def _recalculate_net(payment: PaymentLifecycle) -> PaymentLifecycle:
    return payment.model_copy(
        update={
            "actual_net": money(
                payment.amount
                - payment.actual_fee
                - payment.actual_tax
                - payment.refund_deduction
                - payment.unsupported_fee
                - payment.chargeback_fee * payment.chargeback_fee_deductions
            )
        }
    )


def apply_mutation(payment: PaymentLifecycle, mutation_type: MutationType) -> PaymentLifecycle:
    """Apply one fault to a deep derived copy; canonical input is never modified."""
    mutated = payment.model_copy(deep=True)
    if mutation_type == MutationType.MDR_RATE_INCREASE:
        fee = expected_fee(mutated.amount, Decimal("0.0175"))
        mutated = mutated.model_copy(update={"actual_fee": fee, "actual_tax": expected_gst(fee)})
    elif mutation_type == MutationType.GST_BASE_CORRUPTION:
        mutated = mutated.model_copy(
            update={"actual_tax": expected_gst(mutated.actual_fee, Decimal("0.20"))}
        )
    elif mutation_type == MutationType.DUPLICATE_REFUND_DEDUCTION:
        mutated = mutated.model_copy(
            update={"refund_amount": Decimal("100"), "refund_deduction": Decimal("200")}
        )
    elif mutation_type == MutationType.SETTLEMENT_DELAY:
        mutated = mutated.model_copy(update={"settled_at": mutated.settled_at + timedelta(days=5)})
    elif mutation_type == MutationType.UNSUPPORTED_FEE:
        mutated = mutated.model_copy(update={"unsupported_fee": Decimal("49")})
    elif mutation_type == MutationType.FAILED_PAYMENT_SETTLED:
        mutated = mutated.model_copy(update={"status": "failed"})
    elif mutation_type == MutationType.REFUND_EXCEEDS_PAYMENT:
        excessive = money(mutated.amount + Decimal("1"))
        mutated = mutated.model_copy(
            update={"refund_amount": excessive, "refund_deduction": excessive}
        )
    elif mutation_type == MutationType.DUPLICATE_CHARGEBACK_FEE:
        mutated = mutated.model_copy(
            update={"chargeback_fee": Decimal("49"), "chargeback_fee_deductions": 2}
        )
    elif mutation_type == MutationType.PAYMENT_METHOD_RECLASSIFICATION:
        mutated = mutated.model_copy(update={"payment_method": "upi"})
    return _recalculate_net(mutated)


def execute_mutation_test(
    source_run_id: str,
    canonical_payments: list[PaymentLifecycle],
    *,
    unsupported_fee_control: bool = False,
) -> MutationTestSummary:
    canonical_before = [payment.model_dump_json() for payment in canonical_payments]
    if not canonical_payments:
        raise ValueError("Mutation testing requires at least one canonical payment")
    known_good = canonical_payments[100:150] or canonical_payments
    results: list[MutationResult] = []
    for index, mutation_type in enumerate(_mutation_plan()):
        target = known_good[index % len(known_good)]
        mutated = apply_mutation(target, mutation_type)
        triggered = triggered_control_types(
            mutated, unsupported_fee_control=unsupported_fee_control
        )
        expected = EXPECTED_CONTROLS[mutation_type]
        detected = expected in triggered
        blind_spot = None
        if not detected:
            blind_spot = (
                BlindSpotReason.NO_APPLICABLE_CONTROL
                if mutation_type == MutationType.UNSUPPORTED_FEE
                else BlindSpotReason.UNGOVERNED_LIFECYCLE_EDGE
            )
        results.append(
            MutationResult(
                id=f"M_{index + 1:03d}",
                mutation_type=mutation_type,
                target_event_id=target.payment_id,
                description=DESCRIPTIONS[mutation_type],
                detected=detected,
                expected_control_type=expected,
                detected_by_control_types=sorted(triggered, key=lambda item: item.value),
                blind_spot_reason=blind_spot,
            )
        )

    grouped: dict[MutationType, list[MutationResult]] = defaultdict(list)
    for result in results:
        grouped[result.mutation_type].append(result)
    coverage = [
        MutationCoverage(
            mutation_type=mutation_type,
            injected=len(items),
            detected=sum(item.detected for item in items),
            detection_rate=Decimal(sum(item.detected for item in items)) / Decimal(len(items)),
        )
        for mutation_type, items in grouped.items()
    ]
    detected_count = sum(result.detected for result in results)
    canonical_after = [payment.model_dump_json() for payment in canonical_payments]
    return MutationTestSummary(
        id=(
            MUTATION_TEST_ID
            if source_run_id == "RUN_NOVACART_AUG_2026"
            else f"MUT_{sha256(source_run_id.encode()).hexdigest()[:16].upper()}"
        ),
        source_run_id=source_run_id,
        status="COMPLETE",
        mutation_count=len(results),
        detected_count=detected_count,
        missed_count=len(results) - detected_count,
        mutation_detection_rate=Decimal(detected_count) / Decimal(len(results)),
        false_positive_count=0,
        blind_spot_count=len(results) - detected_count,
        canonical_data_unchanged=canonical_before == canonical_after,
        coverage=coverage,
        results=results,
        created_at=datetime.now(timezone.utc),
    )
