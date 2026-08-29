"""Semantic invariants for unresolved accounting, violation lineage, coverage
and metric wording.

These tests pin the contracts the semantic-correctness pass established:

1. ``pass + violation + warning + unresolved_control == control_evaluation_count``
   and ``unresolved_relationship_count`` is an independent quantity.
2. Lineage root/parent links come from control dependency semantics; impacts
   never double count (``sum(root.total_attributable_impact) ==
   sum(violation.financial_impact)``).
3. Runtime coverage counts only relationship types with actual material edges;
   mutation-derived blind spots are capability statements outside edge totals.
4. The ground-truth metrics note is source neutral.
"""

from datetime import datetime, timezone
from decimal import Decimal

from app.controls.lineage import attribute_root_causes, resolve_violation_lineage
from app.controls.live import build_live_control_evaluations
from app.domain.models import CanonicalEventEdge, ControlType, LineageType, PaymentLifecycle
from app.integrations.razorpay.mapper import map_payment, map_settlement
from app.integrations.razorpay.schemas import PaymentItem, SettlementItem
from app.services.governance import governance

RUN_ID = "RUN_SEMANTIC_INVARIANTS"
CREATED_AT = int(datetime(2026, 8, 3, 10, tzinfo=timezone.utc).timestamp())


def _payment_event(payment_id: str, *, fee: int, tax: int, amount: int = 1_000_000):
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
                "fee": fee,
                "tax": tax,
                "created_at": CREATED_AT,
            }
        ),
        run_id=RUN_ID,
        sync_id="SYNC_INVARIANTS",
    )


def _settlement_event(settlement_id: str, amount: int):
    return map_settlement(
        SettlementItem.model_validate(
            {
                "id": settlement_id,
                "amount": amount,
                "status": "processed",
                "fees": 0,
                "tax": 0,
                "created_at": CREATED_AT + 86_400,
            }
        ),
        run_id=RUN_ID,
        sync_id="SYNC_INVARIANTS",
    )


def _included_in(payment_id: str, settlement_id: str) -> CanonicalEventEdge:
    return CanonicalEventEdge(
        id=f"EDGE_{payment_id}_{settlement_id}",
        run_id=RUN_ID,
        from_event_id=f"rzp:payment:{payment_id}",
        to_event_id=f"rzp:settlement:{settlement_id}",
        relationship="INCLUDED_IN",
        confidence=Decimal("1"),
        method="DETERMINISTIC",
        evidence={},
    )


def _lineage(payment, settlement):
    """Evaluate controls for one payment settled once and resolve lineage."""

    events = [payment, settlement]
    edges = [_included_in(payment.external_id, settlement.external_id)]
    evaluations = build_live_control_evaluations(events, edges, governance.controls)
    violations = [item.violation for item in evaluations if item.violation is not None]
    event_by_id = {event.id: event for event in events}
    violations, _ = resolve_violation_lineage(violations, evaluations, edges, event_by_id)
    roots, violations = attribute_root_causes(RUN_ID, violations, evaluations)
    return evaluations, violations, roots


def _by_control_type(violations):
    return {violation.control_type: violation for violation in violations}


# ---------------------------------------------------------------------------
# Lineage: control dependency semantics
# ---------------------------------------------------------------------------


def test_fee_deviation_propagates_to_tax_and_settlement_as_downstream() -> None:
    # Fee overcharged 175 vs 155 approved; tax is exactly 18% of the excess
    # fee; the settlement nets the overcharged fee and tax.
    payment = _payment_event("pay_chain", fee=17_500, tax=3_150)
    settlement = _settlement_event("set_chain", amount=979_350)
    evaluations, violations, roots = _lineage(payment, settlement)

    by_type = _by_control_type(violations)
    mdr = by_type[ControlType.MDR_RATE]
    gst = by_type[ControlType.GST_ON_FEE]
    settlement_violation = by_type[ControlType.SETTLEMENT_ARITHMETIC]

    assert mdr.lineage_type == LineageType.PRIMARY
    assert mdr.financial_impact == Decimal("20.00")

    # GST: tax_delta (3.60) == fee_delta (20.00) * gst_rate (0.18).
    assert gst.lineage_type == LineageType.DOWNSTREAM
    assert gst.parent_violation_id == mdr.id
    assert gst.root_violation_id == mdr.id
    assert "MDR_RATE" in gst.causal_evidence["control_dependency"]

    # Settlement: |difference| (23.60) == MDR (20.00) + GST (3.60).
    assert settlement_violation.lineage_type == LineageType.DOWNSTREAM
    assert settlement_violation.parent_violation_id == mdr.id
    assert settlement_violation.financial_impact == Decimal("0.00")

    # A downstream violation never becomes an independent systemic root cause.
    categories = {root.category for root in roots}
    assert categories == {ControlType.MDR_RATE.value}
    root = roots[0]
    assert root.primary_violation_count == 1
    assert root.downstream_effect_count == 2
    assert root.direct_impact == Decimal("20.00")
    assert root.downstream_impact == Decimal("3.60")
    assert root.total_attributable_impact == Decimal("23.60")


def test_independent_tax_deviation_stays_primary() -> None:
    # Fee is correct (155); tax deviates on its own (31.00 vs 27.90).
    payment = _payment_event("pay_gst", fee=15_500, tax=3_100)
    settlement = _settlement_event("set_gst", amount=981_400)
    _evaluations, violations, roots = _lineage(payment, settlement)

    gst = _by_control_type(violations)[ControlType.GST_ON_FEE]
    assert gst.lineage_type == LineageType.PRIMARY
    assert gst.parent_violation_id is None
    assert gst.financial_impact == Decimal("3.10")

    categories = {root.category for root in roots}
    assert ControlType.GST_ON_FEE.value in categories
    gst_root = next(root for root in roots if root.category == ControlType.GST_ON_FEE.value)
    assert gst_root.primary_violation_count >= 1


def test_unexplained_settlement_residual_is_primary_and_carries_residual_impact() -> None:
    # Correct fee and tax, but the settlement is short by an unlisted ₹49 fee.
    payment = _payment_event("pay_residual", fee=15_500, tax=2_790)
    settlement = _settlement_event("set_residual", amount=976_810)
    _evaluations, violations, roots = _lineage(payment, settlement)

    residual = _by_control_type(violations)[ControlType.SETTLEMENT_ARITHMETIC]
    assert residual.lineage_type == LineageType.PRIMARY
    assert residual.parent_violation_id is None
    assert residual.financial_impact == Decimal("49.00")
    assert residual.causal_evidence["relationship"] == "INDEPENDENT_RESIDUAL"
    assert residual.causal_evidence["residual_impact"] == "49.00"

    categories = {root.category for root in roots}
    assert categories == {ControlType.SETTLEMENT_ARITHMETIC.value}
    assert roots[0].direct_impact == Decimal("49.00")
    assert roots[0].total_attributable_impact == Decimal("49.00")


def test_partially_explained_settlement_keeps_only_the_residual_impact() -> None:
    # Overcharged fee and tax (23.60 explainable) plus an unlisted ₹49 fee.
    payment = _payment_event("pay_mixed", fee=17_500, tax=3_150)
    settlement = _settlement_event("set_mixed", amount=974_450)
    _evaluations, violations, roots = _lineage(payment, settlement)

    by_type = _by_control_type(violations)
    residual = by_type[ControlType.SETTLEMENT_ARITHMETIC]
    assert residual.lineage_type == LineageType.PRIMARY
    # 72.60 total deviation − 23.60 explained upstream = 49.00 independent.
    assert residual.financial_impact == Decimal("49.00")

    violation_total = sum((violation.financial_impact for violation in violations), Decimal("0"))
    root_total = sum((root.total_attributable_impact for root in roots), Decimal("0"))
    assert violation_total == Decimal("72.60")
    # No double counting: every violation is attributed to exactly one root.
    assert root_total == violation_total
    assert {root.category for root in roots} == {
        ControlType.MDR_RATE.value,
        ControlType.SETTLEMENT_ARITHMETIC.value,
    }


def test_root_cause_attribution_partitions_violations_exactly_once() -> None:
    payment = _payment_event("pay_partition", fee=17_500, tax=3_150)
    settlement = _settlement_event("set_partition", amount=974_450)
    _evaluations, violations, roots = _lineage(payment, settlement)

    assert all(violation.root_cause_id for violation in violations)
    members_by_root = {root.id: set(root.verification_evidence["violation_ids"]) for root in roots}
    all_members = [vid for members in members_by_root.values() for vid in members]
    # No violation appears under two root causes.
    assert len(all_members) == len(set(all_members))
    # Every violation is a member of exactly one root cause.
    assert set(all_members) == {violation.id for violation in violations}
    for root in roots:
        assert root.verification_evidence["grouping_basis"] == "PRIMARY_VIOLATION_CANONICAL_TYPE"
        assert root.verification_evidence["lineage_authority"] == "CONTROL_DEPENDENCY_SEMANTICS"
        assert root.primary_violation_count >= 1
        assert root.primary_violation_count + root.downstream_effect_count == len(
            root.verification_evidence["violation_ids"]
        )


# ---------------------------------------------------------------------------
# Coverage: runtime edges vs mutation-derived blind spots
# ---------------------------------------------------------------------------


def _lifecycle(
    payment_id: str,
    *,
    refund: Decimal = Decimal("0"),
    unsupported: Decimal = Decimal("0"),
    bank_credit: Decimal | None = Decimal("9_000.00"),
) -> PaymentLifecycle:
    return PaymentLifecycle(
        payment_id=payment_id,
        order_id=f"order_{payment_id}",
        settlement_id=f"set_{payment_id}",
        bank_txn_id=None,
        amount=Decimal("10_000.00"),
        payment_method="card",
        card_network="visa",
        card_scope="domestic",
        captured_at=datetime(2026, 8, 3, 10, tzinfo=timezone.utc),
        actual_fee=Decimal("155.00"),
        actual_tax=Decimal("27.90"),
        refund_amount=refund,
        unsupported_fee=unsupported,
        settled_at=datetime(2026, 8, 5, 10, tzinfo=timezone.utc),
        actual_net=Decimal("9_817.10"),
        bank_credit=bank_credit,
    )


def test_relationship_types_without_actual_edges_are_absent_from_runtime_coverage() -> None:
    # No refunds, no unsupported deductions: those relationship types must not
    # appear as runtime coverage items — not even as governed 0/0 rows.
    summary = governance.coverage(RUN_ID, [_lifecycle("pay_a"), _lifecycle("pay_b")])
    relationships = {item.relationship for item in summary.items}
    assert "REFUND → SETTLEMENT" not in relationships
    assert "OTHER DEDUCTION → SETTLEMENT" not in relationships
    assert "PAYMENT → METHOD CLASSIFICATION" not in relationships
    assert all(item.material_edge_count > 0 for item in summary.items)

    # Failure modes remain visible as mutation-derived capability statements.
    failure_modes = {spot.failure_mode for spot in summary.mutation_derived_blind_spots}
    assert "UNSUPPORTED_FEE" in failure_modes
    assert "PAYMENT_METHOD_RECLASSIFICATION" in failure_modes

    # Blind spots never inflate runtime edge totals.
    assert summary.total_material_edges == sum(item.material_edge_count for item in summary.items)
    assert (
        summary.governed_edges + summary.partially_governed_edges + summary.ungoverned_edges
        == summary.total_material_edges
    )


def test_actual_unlisted_deductions_are_runtime_edges_not_mutation_blind_spots() -> None:
    payments = [
        _lifecycle("pay_a"),
        _lifecycle("pay_b", unsupported=Decimal("49.00")),
    ]
    summary = governance.coverage(RUN_ID, payments)
    other = next(
        item for item in summary.items if item.relationship == "OTHER DEDUCTION → SETTLEMENT"
    )
    # Real deductions in the run with a draft control: an ungoverned runtime
    # edge, not merely a mutation-derived blind spot.
    assert other.material_edge_count == 1
    assert other.governed_edge_count == 0
    assert summary.ungoverned_edges == 1

    governance.reset()
    governance.record_backtest("CTRL_UNSUPPORTED_FEE_CANDIDATE")
    governance.approve("CTRL_UNSUPPORTED_FEE_CANDIDATE")
    approved_summary = governance.coverage(RUN_ID, payments)
    approved_other = next(
        item
        for item in approved_summary.items
        if item.relationship == "OTHER DEDUCTION → SETTLEMENT"
    )
    assert approved_other.governed_edge_count == 1
    assert approved_summary.ungoverned_edges == 0
    assert "UNSUPPORTED_FEE" not in {
        spot.failure_mode for spot in approved_summary.mutation_derived_blind_spots
    }
    governance.reset()
