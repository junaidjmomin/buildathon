"""Control dependency semantics and deterministic violation lineage.

Root/parent relationships between violations come from *control dependency
semantics* (one control's expected value is derived from another control's
governed quantity) plus persisted causal evidence in the evaluations. They are
never inferred from transaction IDs or generic clustering.

The dependency chain for the settlement lifecycle is:

    MDR_RATE (approved processing fee)
      -> GST_ON_FEE (tax computed from the approved fee)
      -> SETTLEMENT_ARITHMETIC (expected net computed from approved fee + tax
         and refund principals)

A dependent violation is classified ``DOWNSTREAM`` only when an upstream
violation of a dependency control exists on the same entity (or on a
contributing payment) and the dependent deviation is fully explained by the
upstream deviation within tolerance. Otherwise the violation exists
independently and is ``PRIMARY`` — a downstream violation never becomes an
independent systemic root cause unless it also exists independently.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from hashlib import sha256
from typing import Any

from app.controls.live import LiveControlEvaluation
from app.core.money import money
from app.domain.models import (
    CanonicalEventEdge,
    ControlType,
    FinancialEvent,
    LineageType,
    RootCause,
    Violation,
)

#: Declarative control dependency semantics: each key control recomputes its
#: expected value from the governed quantities of the mapped dependency
#: controls. GST_ON_FEE parameters declare ``base: approved_processing_fee``;
#: SETTLEMENT_ARITHMETIC sums approved payment nets (fee and tax) and refund
#: principals.
CONTROL_DEPENDENCIES: dict[ControlType, frozenset[ControlType]] = {
    ControlType.GST_ON_FEE: frozenset({ControlType.MDR_RATE}),
    ControlType.SETTLEMENT_ARITHMETIC: frozenset(
        {ControlType.MDR_RATE, ControlType.GST_ON_FEE, ControlType.REFUND_INTEGRITY}
    ),
}

_TOLERANCE = Decimal("0.01")


def _decimal(parameter: Any) -> Decimal:
    return Decimal(str(parameter))


def _settlement_contributions(
    edges: list[CanonicalEventEdge],
    event_by_id: dict[str, FinancialEvent],
) -> dict[str, list[str]]:
    """Map each settlement external id to its contributing payment ids."""

    contributions: dict[str, list[str]] = defaultdict(list)
    for edge in edges:
        if edge.relationship != "INCLUDED_IN":
            continue
        settlement = event_by_id.get(edge.to_event_id)
        payment = event_by_id.get(edge.from_event_id)
        if (
            settlement is not None
            and payment is not None
            and settlement.event_type == "SETTLEMENT"
            and payment.event_type == "PAYMENT"
        ):
            contributions[settlement.external_id].append(payment.external_id)
    return dict(contributions)


def _dominant(candidates: list[Violation]) -> Violation:
    """Deterministically pick the parent: largest impact, then lowest id."""

    return sorted(candidates, key=lambda item: (-item.financial_impact, item.id))[0]


@dataclass
class LineageOutcome:
    violation: Violation
    parent: Violation | None
    #: Impact override for independent residuals: the portion of the deviation
    #: that no upstream violation explains. ``None`` keeps the evaluator impact.
    impact: Decimal | None = None


def _classify(
    violation: Violation,
    *,
    violations_by_key: dict[tuple[str, ControlType], list[Violation]],
    evaluation_by_key: dict[tuple[ControlType, str], LiveControlEvaluation],
    settlement_contributions: dict[str, list[str]],
) -> LineageOutcome:
    dependencies = CONTROL_DEPENDENCIES.get(violation.control_type, frozenset())
    if not dependencies:
        return LineageOutcome(violation=violation, parent=None)

    if violation.control_type == ControlType.GST_ON_FEE:
        # Tax base is the approved fee: a fee deviation propagates to tax as
        # gst_rate * fee_delta. The tax deviation is downstream of the fee
        # violation only when that identity holds within tolerance; any excess
        # beyond it means the tax computation itself deviates independently.
        evaluation = evaluation_by_key.get(
            (violation.control_type, violation.payment_id, violation.violation_type)
        )
        mdr = evaluation_by_key.get((ControlType.MDR_RATE, violation.payment_id, "MDR_RATE"))
        parents = [
            candidate
            for candidate in violations_by_key.get((violation.payment_id, ControlType.MDR_RATE), [])
            if candidate.id != violation.id
        ]
        if evaluation is None or mdr is None or mdr.difference_amount is None:
            return LineageOutcome(violation=violation, parent=None)
        if not parents:
            return LineageOutcome(violation=violation, parent=None)
        gst_rate = _decimal(evaluation.control.parameters.get("rate", "0"))
        tolerance = evaluation.tolerance_amount or _TOLERANCE
        fee_delta = mdr.difference_amount or Decimal("0")
        tax_delta = evaluation.difference_amount or Decimal("0")
        explained = money(fee_delta * gst_rate)
        if abs(tax_delta - explained) <= tolerance:
            return LineageOutcome(violation=violation, parent=_dominant(parents))
        return LineageOutcome(violation=violation, parent=None)

    if violation.violation_type == "MISSING_BANK_SETTLEMENT":
        # Missing bank evidence is an exposure finding, never leakage, and is
        # not downstream of any arithmetic deviation.
        return LineageOutcome(violation=violation, parent=None)

    if violation.control_type == ControlType.SETTLEMENT_ARITHMETIC:
        # The expected settlement is recomputed from approved fee, approved
        # tax and refund principals, so upstream violations on contributing
        # payments fully explain the arithmetic deviation when their combined
        # impact covers the difference. Any residual beyond that is
        # independent leakage (e.g. an unlisted deduction) and keeps the
        # violation primary.
        evaluation = evaluation_by_key.get(
            (violation.control_type, violation.payment_id, violation.violation_type)
        )
        if evaluation is None:
            return LineageOutcome(violation=violation, parent=None)
        contributors = settlement_contributions.get(violation.payment_id, [])
        parents: list[Violation] = []
        for payment_id in contributors:
            for dependency in sorted(dependencies, key=lambda item: item.value):
                parents.extend(violations_by_key.get((payment_id, dependency), []))
        difference = evaluation.difference_amount or Decimal("0")
        tolerance = evaluation.tolerance_amount or _TOLERANCE
        explained = money(sum((item.financial_impact for item in parents), Decimal("0")))
        if parents and abs(difference) <= explained + tolerance:
            return LineageOutcome(violation=violation, parent=_dominant(parents))
        # Residual leakage no dependency violation explains: the settlement
        # deviation exists independently and carries only its residual, so the
        # upstream impacts are never double counted.
        residual = max(abs(difference) - explained, Decimal("0"))
        return LineageOutcome(violation=violation, parent=None, impact=money(residual))

    return LineageOutcome(violation=violation, parent=None)


def resolve_violation_lineage(
    violations: list[Violation],
    evaluations: list[LiveControlEvaluation],
    edges: list[CanonicalEventEdge],
    event_by_id: dict[str, FinancialEvent],
) -> tuple[list[Violation], dict[str, list[str]]]:
    """Classify every violation as PRIMARY or DOWNSTREAM.

    Returns the enriched violations plus a mapping of violation id to its
    causal evidence explanation (dependency semantics, parent ids, residual
    attribution), which callers persist on the violation records.
    """

    violations_by_key: dict[tuple[str, ControlType], list[Violation]] = defaultdict(list)
    for violation in violations:
        violations_by_key[(violation.payment_id, violation.control_type)].append(violation)
    # Keyed by control type, target and canonical violation type: one control
    # can execute several distinct deterministic checks (e.g. settlement
    # arithmetic and missing-bank evidence) on the same target.
    evaluation_by_key: dict[tuple[ControlType, str, str], LiveControlEvaluation] = {
        (
            evaluation.control.control_type,
            evaluation.target_id,
            evaluation.violation.violation_type if evaluation.violation else "",
        ): evaluation
        for evaluation in evaluations
    }
    contributions = _settlement_contributions(edges, event_by_id)

    enriched: list[Violation] = []
    explanations: dict[str, list[str]] = {}
    for violation in violations:
        outcome = _classify(
            violation,
            violations_by_key=violations_by_key,
            evaluation_by_key=evaluation_by_key,
            settlement_contributions=contributions,
        )
        parent = outcome.parent
        impact_override = (
            outcome.impact
            if outcome.impact is not None and outcome.impact != violation.financial_impact
            else None
        )
        if parent is not None:
            root_violation_id = parent.root_violation_id or parent.id
            enriched.append(
                violation.model_copy(
                    update={
                        "lineage_type": LineageType.DOWNSTREAM,
                        "root_violation_id": root_violation_id,
                        "parent_violation_id": parent.id,
                        "causal_evidence": {
                            "authority": "DETERMINISTIC",
                            "control_dependency": (
                                f"{violation.control_type.value} depends on "
                                f"{parent.control_type.value} "
                                "(expected value recomputed from the governed quantity)"
                            ),
                            "parent_violation_id": parent.id,
                            "parent_control_type": parent.control_type.value,
                            "counts_toward_verified_leakage": violation.financial_impact
                            > Decimal("0"),
                        },
                    }
                )
            )
            explanations[violation.id] = [
                f"DOWNSTREAM of {parent.id} ({parent.control_type.value})",
            ]
        else:
            primary_evidence: dict[str, Any] = {
                "authority": "DETERMINISTIC",
                "relationship": "DIRECT_CONTROL_DEVIATION",
                "control_type": violation.control_type.value,
            }
            if impact_override is not None:
                primary_evidence["relationship"] = "INDEPENDENT_RESIDUAL"
                primary_evidence["residual_impact"] = str(impact_override)
            enriched.append(
                violation.model_copy(
                    update={
                        "lineage_type": LineageType.PRIMARY,
                        "root_violation_id": violation.id,
                        "financial_impact": impact_override or violation.financial_impact,
                        "causal_evidence": primary_evidence,
                    }
                )
            )
            explanations[violation.id] = ["PRIMARY (independent control deviation)"]
    return enriched, explanations


def attribute_root_causes(
    run_id: str,
    violations: list[Violation],
    evaluations: list[LiveControlEvaluation],
) -> tuple[list[RootCause], list[Violation]]:
    """Group PRIMARY violations into systemic root causes and attribute
    downstream violations to the root cause of their primary ancestor.

    A control category produces an independent systemic root cause only when
    it has at least one PRIMARY violation; downstream-only categories are
    symptoms attributed to their upstream root. Each violation is attributed
    to exactly one root cause, so impacts never double count:
    ``sum(root.total_attributable_impact) == sum(violation.financial_impact)``.
    """

    by_id = {violation.id: violation for violation in violations}
    evaluation_by_violation_id = {
        evaluation.violation.id: evaluation
        for evaluation in evaluations
        if evaluation.violation is not None
    }

    def primary_ancestor(violation: Violation) -> Violation:
        current = violation
        seen: set[str] = set()
        while current.parent_violation_id and current.parent_violation_id not in seen:
            seen.add(current.id)
            parent = by_id.get(current.parent_violation_id)
            if parent is None:
                break
            current = parent
        return current

    primary_category_by_id: dict[str, str] = {}
    for violation in violations:
        ancestor = primary_ancestor(violation)
        # Root causes group by canonical violation type — the deterministic
        # failure mode — falling back to the control type for legacy records.
        primary_category_by_id[violation.id] = (
            ancestor.violation_type or ancestor.control_type.value
        )

    root_ids: dict[str, str] = {}
    for violation in violations:
        category = primary_category_by_id[violation.id]
        if violation.lineage_type != LineageType.PRIMARY:
            continue
        if category not in root_ids:
            digest = sha256(f"{run_id}:{category}".encode()).hexdigest()[:16].upper()
            root_ids[category] = f"RC_{digest}"

    attributed = [
        violation.model_copy(
            update={"root_cause_id": root_ids.get(primary_category_by_id[violation.id])}
        )
        for violation in violations
    ]

    titles = {
        ControlType.MDR_RATE.value: "Systemic MDR rate deviation",
        ControlType.GST_ON_FEE.value: "Systemic GST fee deviation",
        ControlType.SETTLEMENT_SLA.value: "Settlement SLA breach pattern",
        ControlType.REFUND_INTEGRITY.value: "Refund integrity deviation",
        ControlType.SETTLEMENT_ARITHMETIC.value: "Settlement arithmetic deviation",
        "REFUND_EXCEEDS_PAYMENT": "Refunds exceeding payment principal",
        "DUPLICATE_REFUND_DEDUCTION": "Duplicate refund deductions",
        "UNSUPPORTED_REFUND_FEE": "Unsupported refund fees",
        "UNDECLARED_REFUND": "Under-declared refund totals",
        "MISSING_BANK_SETTLEMENT": "Settlements missing bank credits",
    }

    roots: list[RootCause] = []
    for category, root_id in sorted(root_ids.items(), key=lambda item: item[1]):
        members = [violation for violation in attributed if violation.root_cause_id == root_id]
        primaries = [
            violation for violation in members if violation.lineage_type == LineageType.PRIMARY
        ]
        downstream = [
            violation for violation in members if violation.lineage_type == LineageType.DOWNSTREAM
        ]
        if not primaries:
            # Defensive: a root cause always requires at least one primary.
            continue
        direct_impact = money(sum((item.financial_impact for item in primaries), Decimal("0")))
        downstream_impact = money(sum((item.financial_impact for item in downstream), Decimal("0")))
        total = money(direct_impact + downstream_impact)
        member_evaluations = [
            evaluation_by_violation_id[item.id]
            for item in members
            if item.id in evaluation_by_violation_id
        ]
        # The "unaffected" comparison counts evaluations of the same control
        # family (control_type) — violation types are finer than controls.
        member_control_types = {item.control_type for item in members}
        unaffected = sum(
            evaluation.control.control_type in member_control_types and evaluation.violation is None
            for evaluation in evaluations
        )
        roots.append(
            RootCause(
                id=root_id,
                title=titles.get(category, category.replace("_", " ").title()),
                category=category,
                affected_count=len(members),
                verified_impact=total,
                expected_value=primaries[0].expected,
                observed_value=primaries[0].actual,
                first_seen=min(item.occurred_at for item in members),
                last_seen=max(item.occurred_at for item in members),
                verification_status="DETERMINISTICALLY_VERIFIED",
                verification_evidence={
                    "engine": "sl3dge-deterministic-v1",
                    "grouping_basis": "PRIMARY_VIOLATION_CANONICAL_TYPE",
                    "lineage_authority": "CONTROL_DEPENDENCY_SEMANTICS",
                    "evaluation_ids": sorted(
                        evaluation.evaluation_id for evaluation in member_evaluations
                    ),
                    "violation_ids": sorted(item.id for item in members),
                    "primary_violation_ids": sorted(item.id for item in primaries),
                    "downstream_violation_ids": sorted(item.id for item in downstream),
                    "downstream_attribution": (
                        "Downstream violations are attributed to the root cause of "
                        "their primary ancestor and never form an independent "
                        "systemic root cause."
                    ),
                    "unaffected_comparison": {
                        "evaluations_in_control_family": sum(
                            evaluation.control.control_type in member_control_types
                            for evaluation in evaluations
                        ),
                        "violating_evaluations": len(primaries),
                        "unaffected_evaluations": unaffected,
                        "comparison_basis": "same_control_type_and_run",
                    },
                    "impact_accounting": {
                        "direct_impact": str(direct_impact),
                        "downstream_impact": str(downstream_impact),
                        "total_attributable_impact": str(total),
                        "policy": "each violation attributed to exactly one root cause",
                    },
                },
                primary_violation_count=len(primaries),
                downstream_effect_count=len(downstream),
                direct_impact=direct_impact,
                downstream_impact=downstream_impact,
                total_attributable_impact=total,
            )
        )
    return roots, attributed
