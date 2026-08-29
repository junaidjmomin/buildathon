"""Evaluation semantics for labeled datasets.

Ground truth is read here and nowhere else: the deterministic engine never sees
a label, and nothing in ``app`` imports this module. Every number belongs to
exactly one explicit scope, because a finding charged to a scope that does not
own it produces a meaningless metric:

``A`` payment-level primary anomaly quality
``B`` approved-control execution quality
``C`` planted anomaly coverage
``D`` violation-type quality
``E`` relationship resolution quality
``F`` lineage quality
``G`` financial impact quality

Three semantics do the real work.

*Native entity.* Every canonical violation type has exactly one entity that
owns it. A settlement-level arithmetic deviation is a finding about a
settlement, not about each payment batched into it; projecting it onto them
would invent one false negative per constituent payment. Labels are recorded
per payment row for convenience, so every expected finding is resolved to its
native entity before it is compared with anything.

*Accountability.* What the approved suite must catch is derived from the control
registry — ``CLAIMED_VIOLATION_TYPES`` intersected with the approved statuses —
never from the label file. A failure mode governed only by a draft candidate, or
by no control at all, is a blind spot: it lowers planted-anomaly coverage and
must not lower approved-control recall.

*Explained deviations.* A predicted finding that is not an exact label match is
not automatically wrong. It may be the lineage-explained downstream effect of a
true finding, or the same money detected under a different approved name. Both
are itemized with evidence, and precision is reported strictly *and* adjusted so
neither number can be mistaken for the other.
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from app.controls.live import CLAIMED_VIOLATION_TYPES, VIOLATION_TYPES
from app.core.money import money

ZERO = Decimal("0.00")


def _stable_dict_sort_key(item: dict[str, Any]) -> str:
    """Provide a deterministic ordering for JSON-shaped evidence dictionaries."""

    return json.dumps(item, sort_keys=True, separators=(",", ":"), default=str)


#: Label-vocabulary entries with no engine counterpart. Their native entity is
#: the financial record that carries the deviation: an unlisted deduction is a
#: line on a settlement row, a duplicated chargeback fee a line on a chargeback.
LABEL_ONLY_ENTITIES: dict[str, str] = {
    "UNSUPPORTED_FEE": "SETTLEMENT",
    "DUPLICATE_CHARGEBACK_FEE": "CHARGEBACK",
}

#: Expected-status value describing a relationship outcome rather than a control
#: deviation, and the canonical name this evaluator scores it under.
RELATIONSHIP_STATUS = "UNRESOLVED_RELATIONSHIP"
AMBIGUOUS_RELATIONSHIP_TYPE = "AMBIGUOUS_BANK_MATCH"

#: Approved canonical types that carry the same money as a label-vocabulary type
#: on the same native entity. An unlisted settlement deduction breaks the clause
#: 6.2 identity ``net == gross - approved fee - valid GST - valid refunds``, so
#: the approved arithmetic control detects the amount while only the draft clause
#: 4.6 control can name it an unsupported fee. An alias is honoured only when the
#: native entity and the deviation amount both agree, and it is always reported
#: separately from an exact detection — it never inflates a strict metric.
TAXONOMY_ALIASES: dict[str, frozenset[str]] = {
    "UNSUPPORTED_FEE": frozenset({"SETTLEMENT_ARITHMETIC"}),
}

APPROVED_CONTROL = "APPROVED_CONTROL"
DRAFT_CANDIDATE_ONLY = "DRAFT_CANDIDATE_ONLY"
NO_CONTROL_IN_REGISTRY = "NO_CONTROL_IN_REGISTRY"
RELATIONSHIP_RESOLUTION = "RELATIONSHIP_RESOLUTION"

#: False-positive dispositions.
FP_LINEAGE_EXPLAINED = "LINEAGE_EXPLAINED_DOWNSTREAM"
FP_TAXONOMY_ALIAS = "TAXONOMY_ALIAS_OF_EXPECTED_FINDING"
FP_UNEXPLAINED = "UNEXPLAINED"

#: False-negative dispositions.
FN_DETECTED_UNDER_ALIAS = "DETECTED_UNDER_APPROVED_ALIAS"
FN_BLIND_SPOT_DRAFT = "CONTROL_BLIND_SPOT_DRAFT_ONLY"
FN_BLIND_SPOT_NO_CONTROL = "CONTROL_BLIND_SPOT_NO_CONTROL"
FN_RELATIONSHIP_SCOPE = "SCORED_AS_RELATIONSHIP_RESOLUTION"
FN_UNEXPLAINED = "UNEXPLAINED"


def native_entity(violation_type: str) -> str:
    """The single entity class that owns a canonical violation type."""

    known = VIOLATION_TYPES.get(violation_type)
    if known is not None:
        return known[1]
    if violation_type == AMBIGUOUS_RELATIONSHIP_TYPE:
        return "RELATIONSHIP"
    return LABEL_ONLY_ENTITIES.get(violation_type, "UNKNOWN")


def _ratio(numerator: int, denominator: int) -> float | None:
    """A rate, or ``None`` when the denominator is empty.

    A zero is never substituted for an undefined rate: a per-type precision
    printed as ``0.0`` when nothing at all was predicted reads as a failure.
    """

    if denominator <= 0:
        return None
    return round(numerator / denominator, 6)


@dataclass(frozen=True, order=True)
class Instance:
    """One expected or predicted finding, keyed by the entity that owns it."""

    entity_type: str
    entity_id: str
    violation_type: str

    def as_dict(self) -> dict[str, str]:
        return {
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "violation_type": self.violation_type,
        }


@dataclass(frozen=True)
class Confusion:
    tp: int
    fp: int
    fn: int
    tn: int | None = None

    @property
    def predicted_positive(self) -> int:
        return self.tp + self.fp

    @property
    def expected_positive(self) -> int:
        return self.tp + self.fn

    def as_dict(self) -> dict[str, Any]:
        body: dict[str, Any] = {
            "true_positive": self.tp,
            "false_positive": self.fp,
            "false_negative": self.fn,
            "predicted_positive": self.predicted_positive,
            "expected_positive": self.expected_positive,
            "precision": _ratio(self.tp, self.tp + self.fp),
            "recall": _ratio(self.tp, self.tp + self.fn),
            "f1": _ratio(2 * self.tp, 2 * self.tp + self.fp + self.fn),
        }
        if self.tn is not None:
            body["true_negative"] = self.tn
            body["universe"] = self.tp + self.fp + self.fn + self.tn
            body["false_positive_rate"] = _ratio(self.fp, self.fp + self.tn)
        return body


@dataclass(frozen=True)
class TruthRow:
    payment_id: str
    expected_status: str
    violation_types: tuple[str, ...]
    primary_violation_types: tuple[str, ...]
    downstream_violation_types: tuple[str, ...]
    expected_loss: Decimal
    notes: str


def load_truth(path: Path) -> tuple[TruthRow, ...]:
    def split(value: str) -> tuple[str, ...]:
        return tuple(item for item in value.split(";") if item)

    with path.open(newline="") as handle:
        return tuple(
            TruthRow(
                payment_id=row["payment_id"],
                expected_status=row["expected_status"],
                violation_types=split(row["violation_types"]),
                primary_violation_types=split(row["primary_violation_types"]),
                downstream_violation_types=split(row["downstream_violation_types"]),
                expected_loss=money(Decimal(row["expected_verified_loss"])),
                notes=row["notes"],
            )
            for row in csv.DictReader(handle)
        )


@dataclass(frozen=True)
class SourceIndex:
    """Payment-to-entity relationships read straight from the source CSVs.

    Built independently of the engine so that entity resolution in the evaluator
    can never inherit an engine mistake.
    """

    settlement_of_payment: dict[str, str]
    payments_of_settlement: dict[str, tuple[str, ...]]
    chargebacks_of_payment: dict[str, tuple[str, ...]]
    refunds_of_payment: dict[str, tuple[str, ...]]
    captured_at: dict[str, datetime]
    payment_status: dict[str, str]

    @classmethod
    def from_paths(cls, paths: dict[str, Path]) -> SourceIndex:
        def rows(name: str) -> list[dict[str, str]]:
            with paths[name].open(newline="") as handle:
                return list(csv.DictReader(handle))

        settlement_of_payment: dict[str, str] = {}
        payments_of_settlement: dict[str, list[str]] = defaultdict(list)
        for row in rows("settlements"):
            settlement_of_payment[row["payment_id"]] = row["settlement_id"]
            payments_of_settlement[row["settlement_id"]].append(row["payment_id"])
        chargebacks: dict[str, list[str]] = defaultdict(list)
        for row in rows("chargebacks"):
            chargebacks[row["payment_id"]].append(row["chargeback_id"])
        refunds: dict[str, list[str]] = defaultdict(list)
        for row in rows("refunds"):
            refunds[row["payment_id"]].append(row["refund_id"])
        captured_at: dict[str, datetime] = {}
        payment_status: dict[str, str] = {}
        for row in rows("payments"):
            payment_status[row["payment_id"]] = row["status"]
            if row["captured_at"]:
                captured_at[row["payment_id"]] = datetime.fromisoformat(row["captured_at"])
        return cls(
            settlement_of_payment=settlement_of_payment,
            payments_of_settlement={
                key: tuple(value) for key, value in payments_of_settlement.items()
            },
            chargebacks_of_payment={key: tuple(value) for key, value in chargebacks.items()},
            refunds_of_payment={key: tuple(value) for key, value in refunds.items()},
            captured_at=captured_at,
            payment_status=payment_status,
        )

    def resolve(self, violation_type: str, payment_id: str) -> tuple[Instance, ...]:
        """Map a label recorded on a payment row to its native entity instances."""

        entity = native_entity(violation_type)
        if entity == "PAYMENT":
            return (Instance("PAYMENT", payment_id, violation_type),)
        if entity in {"SETTLEMENT", "RELATIONSHIP"}:
            settlement = self.settlement_of_payment.get(payment_id)
            if settlement is None:
                return ()
            return (Instance("SETTLEMENT", settlement, violation_type),)
        if entity == "CHARGEBACK":
            return tuple(
                Instance("CHARGEBACK", chargeback_id, violation_type)
                for chargeback_id in self.chargebacks_of_payment.get(payment_id, ())
            )
        return ()


@dataclass(frozen=True)
class Governance:
    """What the control registry says about each canonical failure mode."""

    approved: frozenset[str]
    draft: frozenset[str]
    approved_control_ids: tuple[str, ...]
    draft_control_ids: tuple[str, ...]

    @classmethod
    def from_controls(cls, controls: list[dict[str, Any]]) -> Governance:
        claims = {key.value: value for key, value in CLAIMED_VIOLATION_TYPES.items()}
        approved: set[str] = set()
        draft: set[str] = set()
        approved_ids: list[str] = []
        draft_ids: list[str] = []
        for control in controls:
            claimed = claims.get(control["control_type"], frozenset())
            if control["status"] == "APPROVED":
                approved |= set(claimed)
                approved_ids.append(control["id"])
            else:
                draft |= set(claimed)
                draft_ids.append(control["id"])
        return cls(
            approved=frozenset(approved),
            draft=frozenset(draft - approved),
            approved_control_ids=tuple(sorted(approved_ids)),
            draft_control_ids=tuple(sorted(draft_ids)),
        )

    def status_of(self, violation_type: str) -> str:
        if violation_type == AMBIGUOUS_RELATIONSHIP_TYPE:
            return RELATIONSHIP_RESOLUTION
        if violation_type in self.approved:
            return APPROVED_CONTROL
        if violation_type in self.draft:
            return DRAFT_CANDIDATE_ONLY
        return NO_CONTROL_IN_REGISTRY


@dataclass(frozen=True)
class Observation:
    """Everything read back from one executed run. No labels enter here."""

    run_id: str
    dataset_id: str
    dataset_type: str
    summary: dict[str, Any]
    violations: tuple[dict[str, Any], ...]
    unresolved: tuple[dict[str, Any], ...]
    root_causes: tuple[dict[str, Any], ...]
    evaluations: tuple[dict[str, Any], ...]
    controls: tuple[dict[str, Any], ...]
    credited_settlement_ids: frozenset[str]


# --------------------------------------------------------------------------- #
# Instance construction
# --------------------------------------------------------------------------- #


def expected_instances(
    truth: tuple[TruthRow, ...], index: SourceIndex
) -> dict[Instance, tuple[str, ...]]:
    """Expected findings at their native entity, with the rows that label them."""

    collected: dict[Instance, list[str]] = defaultdict(list)
    for row in truth:
        types = list(row.violation_types)
        if row.expected_status == RELATIONSHIP_STATUS:
            types.append(AMBIGUOUS_RELATIONSHIP_TYPE)
        for violation_type in types:
            for instance in index.resolve(violation_type, row.payment_id):
                collected[instance].append(row.payment_id)
    return {instance: tuple(rows) for instance, rows in collected.items()}


def predicted_instances(
    violations: tuple[dict[str, Any], ...],
) -> dict[Instance, tuple[dict[str, Any], ...]]:
    """Persisted violations grouped by the entity/type pair they assert."""

    collected: dict[Instance, list[dict[str, Any]]] = defaultdict(list)
    for violation in violations:
        instance = Instance(
            violation["target_type"],
            violation["payment_id"],
            violation["violation_type"],
        )
        collected[instance].append(violation)
    return {instance: tuple(items) for instance, items in collected.items()}


# --------------------------------------------------------------------------- #
# Disposition of non-matching findings
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Dispositions:
    false_positive: dict[Instance, dict[str, Any]]
    false_negative: dict[Instance, dict[str, Any]]

    @property
    def explained_false_positives(self) -> set[Instance]:
        return {
            instance
            for instance, detail in self.false_positive.items()
            if detail["disposition"] != FP_UNEXPLAINED
        }

    @property
    def aliased_false_negatives(self) -> set[Instance]:
        return {
            instance
            for instance, detail in self.false_negative.items()
            if detail["disposition"] == FN_DETECTED_UNDER_ALIAS
        }


def _expected_loss_by_instance(
    truth: tuple[TruthRow, ...], index: SourceIndex
) -> dict[Instance, Decimal | None]:
    """Expected loss per instance, where the row attributes it unambiguously.

    A row labeled with several violation types carries one combined loss, so the
    per-instance amount is unknowable from the label file and stays ``None``.
    """

    losses: dict[Instance, Decimal | None] = {}
    for row in truth:
        unambiguous = len(row.violation_types) == 1
        for violation_type in row.violation_types:
            for instance in index.resolve(violation_type, row.payment_id):
                amount = row.expected_loss if unambiguous else None
                if instance in losses and losses[instance] is not None and amount is not None:
                    losses[instance] = money(losses[instance] + amount)
                else:
                    losses[instance] = amount if instance not in losses else losses[instance]
    return losses


def classify_dispositions(
    expected: dict[Instance, tuple[str, ...]],
    predicted: dict[Instance, tuple[dict[str, Any], ...]],
    truth: tuple[TruthRow, ...],
    index: SourceIndex,
    governance: Governance,
) -> Dispositions:
    """Explain every finding that is not an exact expected/predicted match."""

    violation_by_id = {
        violation["id"]: violation for items in predicted.values() for violation in items
    }
    expected_losses = _expected_loss_by_instance(truth, index)
    expected_by_entity: dict[tuple[str, str], set[str]] = defaultdict(set)
    for instance in expected:
        expected_by_entity[(instance.entity_type, instance.entity_id)].add(instance.violation_type)

    def primary_ancestor(violation: dict[str, Any]) -> dict[str, Any]:
        current = violation
        seen: set[str] = set()
        while current.get("parent_violation_id") and current["id"] not in seen:
            seen.add(current["id"])
            parent = violation_by_id.get(current["parent_violation_id"])
            if parent is None:
                break
            current = parent
        return current

    false_positive: dict[Instance, dict[str, Any]] = {}
    for instance in sorted(set(predicted) - set(expected)):
        violations = predicted[instance]
        ancestors = [primary_ancestor(violation) for violation in violations]
        ancestor_instances = {
            Instance(item["target_type"], item["payment_id"], item["violation_type"])
            for item in ancestors
        }
        # A downstream effect of a confirmed finding is a correct consequence,
        # not an independent claim: the label file records the cause, and the
        # engine additionally records where the money surfaced.
        explained_by = sorted(
            item.as_dict() for item in ancestor_instances if item in expected and item != instance
        )
        if explained_by and all(
            violation["lineage_type"] == "DOWNSTREAM" for violation in violations
        ):
            false_positive[instance] = {
                "disposition": FP_LINEAGE_EXPLAINED,
                "explained_by": explained_by,
                "financial_impact": str(
                    money(sum((Decimal(str(v["financial_impact"])) for v in violations), ZERO))
                ),
            }
            continue
        # The same money under a different approved name: the label vocabulary
        # and the approved control disagree on the *name*, not on the finding.
        alias_of = [
            label_type
            for label_type, aliases in TAXONOMY_ALIASES.items()
            if instance.violation_type in aliases
            and label_type in expected_by_entity[(instance.entity_type, instance.entity_id)]
        ]
        if alias_of:
            label_type = alias_of[0]
            alias_instance = Instance(instance.entity_type, instance.entity_id, label_type)
            expected_amount = expected_losses.get(alias_instance)
            actual_amount = money(
                sum((Decimal(str(v["financial_impact"])) for v in violations), ZERO)
            )
            amounts_agree = expected_amount is not None and expected_amount == actual_amount
            false_positive[instance] = {
                "disposition": FP_TAXONOMY_ALIAS,
                "alias_of": alias_instance.as_dict(),
                "expected_amount": None if expected_amount is None else str(expected_amount),
                "actual_amount": str(actual_amount),
                "amounts_agree": amounts_agree,
                "governing_approved_control": sorted(
                    control_id for control_id in governance.approved_control_ids if control_id
                ),
            }
            continue
        false_positive[instance] = {
            "disposition": FP_UNEXPLAINED,
            "lineage_types": sorted({violation["lineage_type"] for violation in violations}),
            "financial_impact": str(
                money(sum((Decimal(str(v["financial_impact"])) for v in violations), ZERO))
            ),
        }

    predicted_by_entity: dict[tuple[str, str], set[str]] = defaultdict(set)
    for instance in predicted:
        predicted_by_entity[(instance.entity_type, instance.entity_id)].add(instance.violation_type)

    false_negative: dict[Instance, dict[str, Any]] = {}
    for instance in sorted(set(expected) - set(predicted)):
        aliases = TAXONOMY_ALIASES.get(instance.violation_type, frozenset())
        matched = sorted(aliases & predicted_by_entity[(instance.entity_type, instance.entity_id)])
        if matched:
            false_negative[instance] = {
                "disposition": FN_DETECTED_UNDER_ALIAS,
                "detected_as": matched,
                "labeled_payment_rows": len(expected[instance]),
            }
            continue
        status = governance.status_of(instance.violation_type)
        if status == RELATIONSHIP_RESOLUTION:
            # An ambiguous relationship is deliberately not published as a
            # violation: the engine refuses to assert a match it cannot prove and
            # reports it on the unresolved surface instead. Scope E scores that
            # refusal as the success it is, so the violation scope must neither
            # credit nor penalise it here.
            disposition = FN_RELATIONSHIP_SCOPE
        elif status == DRAFT_CANDIDATE_ONLY:
            disposition = FN_BLIND_SPOT_DRAFT
        elif status == NO_CONTROL_IN_REGISTRY:
            disposition = FN_BLIND_SPOT_NO_CONTROL
        else:
            disposition = FN_UNEXPLAINED
        false_negative[instance] = {
            "disposition": disposition,
            "governance": status,
            "labeled_payment_rows": len(expected[instance]),
        }
    return Dispositions(false_positive=false_positive, false_negative=false_negative)


# --------------------------------------------------------------------------- #
# Scope A — payment-level primary anomaly quality
# --------------------------------------------------------------------------- #


def payment_primary_detection(
    truth: tuple[TruthRow, ...], observation: Observation
) -> dict[str, Any]:
    """Every payment judged once, on payment-native deterministic violations."""

    expected_positive = {
        row.payment_id
        for row in truth
        if any(native_entity(item) == "PAYMENT" for item in row.violation_types)
    }
    predicted_positive = {
        violation["payment_id"]
        for violation in observation.violations
        if violation["target_type"] == "PAYMENT"
    }
    universe = {row.payment_id for row in truth}
    # A prediction outside the labeled universe is never silently dropped.
    outside_universe = sorted(predicted_positive - universe)
    predicted_in_universe = predicted_positive & universe
    tp = len(predicted_in_universe & expected_positive)
    fp = len(predicted_in_universe - expected_positive)
    fn = len(expected_positive - predicted_in_universe)
    tn = len(universe) - tp - fp - fn
    confusion = Confusion(tp=tp, fp=fp, fn=fn, tn=tn)
    assert confusion.predicted_positive == len(predicted_in_universe)
    body = confusion.as_dict()
    body.update(
        {
            "scope": (
                "One row per labeled payment. Positive means at least one "
                "payment-native deterministic violation; settlement, chargeback "
                "and relationship findings are scored in their own scopes."
            ),
            "payment_native_types": sorted(
                {item for item in VIOLATION_TYPES if native_entity(item) == "PAYMENT"}
            ),
            "predictions_outside_labeled_universe": len(outside_universe),
            "false_positive_samples": sorted(predicted_in_universe - expected_positive)[:10],
            "false_negative_samples": sorted(expected_positive - predicted_in_universe)[:10],
        }
    )
    return body


# --------------------------------------------------------------------------- #
# Scope B — approved-control execution quality
# --------------------------------------------------------------------------- #


def approved_control_execution(
    expected: dict[Instance, tuple[str, ...]],
    predicted: dict[Instance, tuple[dict[str, Any], ...]],
    governance: Governance,
    dispositions: Dispositions,
) -> dict[str, Any]:
    """Only failure modes an approved control claims to detect are scored."""

    in_scope = governance.approved
    expected_scope = {item for item in expected if item.violation_type in in_scope}
    predicted_scope = {item for item in predicted if item.violation_type in in_scope}
    tp = expected_scope & predicted_scope
    fp = predicted_scope - expected_scope
    fn = expected_scope - predicted_scope
    strict = Confusion(tp=len(tp), fp=len(fp), fn=len(fn))
    explained_fp = fp & dispositions.explained_false_positives
    aliased_fn = fn & dispositions.aliased_false_negatives
    adjusted = Confusion(
        tp=len(tp) + len(aliased_fn),
        fp=len(fp) - len(explained_fp),
        fn=len(fn) - len(aliased_fn),
    )
    return {
        "scope": (
            "Instance-level (native entity, canonical violation type) over the "
            "failure modes an APPROVED control claims. Draft-governed and "
            "unregistered modes are excluded — they are blind spots, not "
            "execution failures."
        ),
        "claimed_by_approved_controls": sorted(in_scope),
        "approved_control_ids": list(governance.approved_control_ids),
        "excluded_draft_only_modes": sorted(governance.draft),
        "strict": strict.as_dict(),
        "adjusted": adjusted.as_dict(),
        "adjustments": {
            "basis": (
                "Strict counts exact name matches only. Adjusted additionally "
                "credits findings the engine reports under an equivalent "
                "approved name and discounts downstream effects of confirmed "
                "findings; every adjustment is itemized below."
            ),
            "lineage_explained_false_positives": len(explained_fp),
            "taxonomy_alias_false_positives": len(
                {
                    instance
                    for instance in fp
                    if dispositions.false_positive.get(instance, {}).get("disposition")
                    == FP_TAXONOMY_ALIAS
                }
            ),
            "alias_credited_false_negatives": len(aliased_fn),
        },
        "unexplained_false_positives": sorted(
            (
                instance.as_dict()
                for instance in fp
                if dispositions.false_positive.get(instance, {}).get("disposition")
                == FP_UNEXPLAINED
            ),
            key=_stable_dict_sort_key,
        ),
        "unexplained_false_negatives": sorted(
            (
                instance.as_dict()
                for instance in fn
                if dispositions.false_negative.get(instance, {}).get("disposition")
                == FN_UNEXPLAINED
            ),
            key=_stable_dict_sort_key,
        ),
    }


# --------------------------------------------------------------------------- #
# Scope C — planted anomaly coverage
# --------------------------------------------------------------------------- #


def planted_anomaly_coverage(
    expected: dict[Instance, tuple[str, ...]],
    predicted: dict[Instance, tuple[dict[str, Any], ...]],
    governance: Governance,
    dispositions: Dispositions,
    manifest: dict[str, Any],
) -> dict[str, Any]:
    """Coverage of what the fixture actually plants, blind spots included."""

    by_type: dict[str, list[Instance]] = defaultdict(list)
    for instance in expected:
        by_type[instance.violation_type].append(instance)

    planted = manifest.get("planted_scenarios", {})
    items: list[dict[str, Any]] = []
    relationship_items: list[dict[str, Any]] = []
    total_expected = detected_total = aliased_total = 0
    for violation_type in sorted(by_type):
        instances = by_type[violation_type]
        detected = [item for item in instances if item in predicted]
        aliased = [item for item in instances if item in dispositions.aliased_false_negatives]
        undetected = [
            item for item in instances if item not in predicted and item not in set(aliased)
        ]
        status = governance.status_of(violation_type)
        labeled_rows = sum(len(expected[item]) for item in instances)
        entry = {
            "violation_type": violation_type,
            "native_entity": native_entity(violation_type),
            "governance": status,
            "planted_instances": len(instances),
            "labeled_payment_rows": labeled_rows,
            "detected_exact": len(detected),
            "detected_under_approved_alias": len(aliased),
            "undetected": len(undetected),
            "coverage": _ratio(len(detected) + len(aliased), len(instances)),
            "undetected_samples": sorted(item.entity_id for item in undetected)[:6],
        }
        if status == RELATIONSHIP_RESOLUTION:
            # A planted ambiguity is handled by refusing to assert a match, not
            # by raising a violation. Counting it as an undetected anomaly here
            # would penalise the engine for the behaviour the fixture is testing
            # for; scope E scores it, so it is reported separately.
            relationship_items.append({**entry, "scored_in": "relationship_resolution"})
            continue
        total_expected += len(instances)
        detected_total += len(detected)
        aliased_total += len(aliased)
        items.append(entry)
    approved_items = [item for item in items if item["governance"] == APPROVED_CONTROL]
    approved_expected = sum(item["planted_instances"] for item in approved_items)
    approved_covered = sum(
        item["detected_exact"] + item["detected_under_approved_alias"] for item in approved_items
    )
    return {
        "scope": (
            "Coverage of the planted failure modes at their native entity. A "
            "blind spot lowers coverage and never lowers approved-control "
            "recall. Ambiguous relationships are excluded and scored in the "
            "relationship-resolution scope, where refusing to match is success."
        ),
        "manifest_planted_scenarios": planted,
        "manifest_note": (
            "Manifest counts record the generator's intent per scenario and are "
            "expressed in payment rows; planted_instances below is derived from "
            "the label file at the native entity, which is authoritative."
        ),
        "planted_instances": total_expected,
        "detected_exact": detected_total,
        "detected_under_approved_alias": aliased_total,
        "undetected": total_expected - detected_total - aliased_total,
        "coverage": _ratio(detected_total + aliased_total, total_expected),
        "coverage_of_approved_governed_modes": _ratio(approved_covered, approved_expected),
        "by_type": items,
        "scored_in_relationship_scope": relationship_items,
        "blind_spots": [
            {
                "violation_type": item["violation_type"],
                "governance": item["governance"],
                "undetected": item["undetected"],
                "reason": (
                    "Governed only by a DRAFT candidate control; approval "
                    "requires mutation evidence, a backtest and a human "
                    "decision."
                    if item["governance"] == DRAFT_CANDIDATE_ONLY
                    else "No control in the registry claims this failure mode."
                ),
            }
            for item in items
            if item["undetected"] > 0 and item["governance"] != APPROVED_CONTROL
        ],
    }


# --------------------------------------------------------------------------- #
# Scope D — violation-type quality
# --------------------------------------------------------------------------- #


def violation_type_quality(
    expected: dict[Instance, tuple[str, ...]],
    predicted: dict[Instance, tuple[dict[str, Any], ...]],
    governance: Governance,
    dispositions: Dispositions,
) -> list[dict[str, Any]]:
    """Per canonical type, on ``(entity_id, canonical_violation_type)`` pairs.

    Each row carries both a strict score, which counts exact name matches only,
    and an adjusted score, which discounts the false positives and negatives the
    disposition pass explains. A type can be strictly imprecise and still be
    entirely correct — ``SETTLEMENT_ARITHMETIC`` raised as the proven downstream
    effect of a labeled fee error is the canonical example — so reporting only
    the strict number would be a misleading way to be technically accurate.
    """

    types = sorted(
        {item.violation_type for item in expected} | {item.violation_type for item in predicted}
    )
    rows: list[dict[str, Any]] = []
    for violation_type in types:
        expected_scope = {item for item in expected if item.violation_type == violation_type}
        predicted_scope = {item for item in predicted if item.violation_type == violation_type}
        tp = expected_scope & predicted_scope
        fp = predicted_scope - expected_scope
        fn = expected_scope - predicted_scope
        fp_dispositions: dict[str, int] = defaultdict(int)
        for instance in fp:
            fp_dispositions[
                dispositions.false_positive.get(instance, {}).get("disposition", FP_UNEXPLAINED)
            ] += 1
        fn_dispositions: dict[str, int] = defaultdict(int)
        for instance in fn:
            fn_dispositions[
                dispositions.false_negative.get(instance, {}).get("disposition", FN_UNEXPLAINED)
            ] += 1
        unexplained_fp = fp_dispositions.get(FP_UNEXPLAINED, 0)
        unexplained_fn = fn_dispositions.get(FN_UNEXPLAINED, 0)
        credited_fn = fn_dispositions.get(FN_DETECTED_UNDER_ALIAS, 0)
        body = {
            "violation_type": violation_type,
            "native_entity": native_entity(violation_type),
            "governance": governance.status_of(violation_type),
            "strict": Confusion(tp=len(tp), fp=len(fp), fn=len(fn)).as_dict(),
            "adjusted": Confusion(
                tp=len(tp) + credited_fn,
                fp=unexplained_fp,
                fn=unexplained_fn,
            ).as_dict(),
            "false_positive_dispositions": dict(sorted(fp_dispositions.items())),
            "false_negative_dispositions": dict(sorted(fn_dispositions.items())),
            "unexplained_false_positives": unexplained_fp,
            "unexplained_false_negatives": unexplained_fn,
        }
        rows.append(body)
    return rows


def entity_level_quality(
    expected: dict[Instance, tuple[str, ...]],
    predicted: dict[Instance, tuple[dict[str, Any], ...]],
    index: SourceIndex,
    dispositions: Dispositions,
) -> dict[str, Any]:
    """Instance-level quality grouped by the entity class that owns the finding."""

    def confusion_for(entity_type: str) -> dict[str, Any]:
        expected_scope = {item for item in expected if item.entity_type == entity_type}
        predicted_scope = {item for item in predicted if item.entity_type == entity_type}
        tp = expected_scope & predicted_scope
        fp = predicted_scope - expected_scope
        fn = expected_scope - predicted_scope
        body = Confusion(tp=len(tp), fp=len(fp), fn=len(fn)).as_dict()
        body["unexplained_false_positives"] = len(fp - dispositions.explained_false_positives)
        body["unexplained_false_negatives"] = len(
            {
                instance
                for instance in fn
                if dispositions.false_negative.get(instance, {}).get("disposition")
                == FN_UNEXPLAINED
            }
        )
        body["violation_types"] = sorted(
            {item.violation_type for item in expected_scope | predicted_scope}
        )
        return body

    payment = confusion_for("PAYMENT")
    settlement = confusion_for("SETTLEMENT")
    chargeback = confusion_for("CHARGEBACK")
    refund_types = sorted(
        item
        for item in VIOLATION_TYPES
        if item.startswith(("REFUND_", "DUPLICATE_REFUND", "UNSUPPORTED_REFUND", "UNDECLARED_"))
    )
    return {
        "payment": payment,
        "settlement": settlement,
        "chargeback": chargeback,
        "refund": {
            "native_findings": 0,
            "scored_under": "payment",
            "evidence_entity_for": refund_types,
            "refund_records": sum(len(value) for value in index.refunds_of_payment.values()),
            "note": (
                "Clause 7.2 obliges the payment's settlement to deduct the "
                "refunded principal once, so the obligation is payment-native "
                "and the refund is the evidence record. Refund findings are "
                "scored under `payment`; no separate refund-native type exists."
            ),
        },
        "relationship": confusion_for("RELATIONSHIP"),
    }


# --------------------------------------------------------------------------- #
# Scope E — relationship resolution quality
# --------------------------------------------------------------------------- #


def relationship_resolution(
    truth: tuple[TruthRow, ...], index: SourceIndex, observation: Observation
) -> dict[str, Any]:
    """A correct unresolved verdict is a success, not a miss."""

    labeled_rows = [row for row in truth if row.expected_status == RELATIONSHIP_STATUS]
    expected_ambiguous = {
        index.settlement_of_payment[row.payment_id]
        for row in labeled_rows
        if row.payment_id in index.settlement_of_payment
    }
    engine_unresolved = {
        item.get("settlement_id") or item["payment_id"] for item in observation.unresolved
    }
    correctly_unresolved = expected_ambiguous & engine_unresolved
    missed_unresolved = expected_ambiguous - engine_unresolved
    false_unresolved = engine_unresolved - expected_ambiguous
    forced_matches = expected_ambiguous & observation.credited_settlement_ids
    union = expected_ambiguous | engine_unresolved
    return {
        "scope": (
            "Settlement-to-bank pairings. Leaving a genuinely ambiguous pairing "
            "unresolved is the correct outcome; forcing a match is the failure."
        ),
        "expected_ambiguous_settlements": len(expected_ambiguous),
        "expected_ambiguous_payment_rows": len(labeled_rows),
        "correctly_unresolved": len(correctly_unresolved),
        "missed_unresolved": len(missed_unresolved),
        "false_unresolved": len(false_unresolved),
        "forced_incorrect_matches": len(forced_matches),
        "accuracy": _ratio(len(correctly_unresolved), len(union)),
        "missed_unresolved_samples": sorted(missed_unresolved)[:6],
        "false_unresolved_samples": sorted(false_unresolved)[:6],
        "unresolved_conclusions": sorted(
            {
                item["safe_conclusion"]
                for item in observation.unresolved
                if item.get("safe_conclusion")
            }
        ),
        "missing_evidence": sorted(
            {
                item["missing_evidence"]
                for item in observation.unresolved
                if item.get("missing_evidence")
            }
        ),
    }


# --------------------------------------------------------------------------- #
# Scope F — lineage quality
# --------------------------------------------------------------------------- #


def lineage_quality(truth: tuple[TruthRow, ...], observation: Observation) -> dict[str, Any]:
    """Persisted production lineage against the labeled primary/downstream split."""

    violation_by_id = {violation["id"]: violation for violation in observation.violations}
    predicted: dict[tuple[str, str], dict[str, Any]] = {}
    for violation in observation.violations:
        if violation["target_type"] != "PAYMENT":
            continue
        predicted[(violation["payment_id"], violation["violation_type"])] = violation

    primary_correct = primary_incorrect = 0
    downstream_correct = downstream_incorrect = 0
    missing_edges: list[dict[str, str]] = []
    extra_edges: list[dict[str, str]] = []
    for row in truth:
        for violation_type in row.primary_violation_types:
            if native_entity(violation_type) != "PAYMENT":
                continue
            violation = predicted.get((row.payment_id, violation_type))
            if violation is None:
                continue
            if violation["lineage_type"] == "PRIMARY":
                primary_correct += 1
            else:
                primary_incorrect += 1
                extra_edges.append(
                    {
                        "entity_id": row.payment_id,
                        "violation_type": violation_type,
                        "observed_parent": violation.get("parent_violation_id") or "",
                    }
                )
        for violation_type in row.downstream_violation_types:
            if native_entity(violation_type) != "PAYMENT":
                continue
            violation = predicted.get((row.payment_id, violation_type))
            if violation is None:
                continue
            if violation["lineage_type"] == "DOWNSTREAM":
                downstream_correct += 1
                if not violation.get("parent_violation_id"):
                    missing_edges.append(
                        {
                            "entity_id": row.payment_id,
                            "violation_type": violation_type,
                            "issue": "DOWNSTREAM_WITHOUT_PARENT",
                        }
                    )
            else:
                downstream_incorrect += 1
                missing_edges.append(
                    {
                        "entity_id": row.payment_id,
                        "violation_type": violation_type,
                        "issue": "EXPECTED_DOWNSTREAM_REPORTED_PRIMARY",
                    }
                )

    # The declared dependency chain: tax is computed from the approved fee, so a
    # downstream tax deviation must name the fee violation on the same payment.
    gst_downstream = [
        violation
        for violation in observation.violations
        if violation["violation_type"] == "GST_ON_FEE" and violation["lineage_type"] == "DOWNSTREAM"
    ]
    valid_gst_edges = 0
    for violation in gst_downstream:
        parent = violation_by_id.get(violation.get("parent_violation_id") or "")
        if (
            parent is not None
            and parent["violation_type"] == "MDR_RATE"
            and parent["payment_id"] == violation["payment_id"]
        ):
            valid_gst_edges += 1
    downstream_total = sum(
        1 for violation in observation.violations if violation["lineage_type"] == "DOWNSTREAM"
    )
    rooted = sum(
        1
        for violation in observation.violations
        if violation.get("root_violation_id")
        and (
            violation["lineage_type"] == "PRIMARY"
            or violation.get("root_violation_id") != violation["id"]
        )
    )
    return {
        "scope": (
            "Persisted production lineage (violations.lineage_type, "
            "parent_violation_id, root_violation_id) against the labeled "
            "primary/downstream split. Payment-native types only; settlement "
            "downstream effects are consequences the label file does not record."
        ),
        "primary_correct": primary_correct,
        "primary_incorrect": primary_incorrect,
        "downstream_correct": downstream_correct,
        "downstream_incorrect": downstream_incorrect,
        "missing_causal_edges": len(missing_edges),
        "extra_causal_edges": len(extra_edges),
        "missing_causal_edge_samples": missing_edges[:6],
        "extra_causal_edge_samples": extra_edges[:6],
        "mdr_rate_to_gst_on_fee": {
            "downstream_gst_violations": len(gst_downstream),
            "with_mdr_rate_parent_on_same_payment": valid_gst_edges,
            "chain_intact": len(gst_downstream) == valid_gst_edges,
        },
        "persisted_lineage_integrity": {
            "downstream_violations": downstream_total,
            "violations_with_root": rooted,
            "all_violations_rooted": rooted == len(observation.violations),
        },
        "accuracy": _ratio(
            primary_correct + downstream_correct,
            primary_correct + primary_incorrect + downstream_correct + downstream_incorrect,
        ),
    }


# --------------------------------------------------------------------------- #
# Scope G — financial impact quality
# --------------------------------------------------------------------------- #


def financial_impact(
    truth: tuple[TruthRow, ...],
    index: SourceIndex,
    expected: dict[Instance, tuple[str, ...]],
    predicted: dict[Instance, tuple[dict[str, Any], ...]],
    dispositions: Dispositions,
    observation: Observation,
) -> dict[str, Any]:
    """Decimal-only leakage reconciliation with an explicit no-double-count check."""

    expected_total = money(sum((row.expected_loss for row in truth), ZERO))
    predicted_total = money(Decimal(str(observation.summary["verified_leakage"])))
    violation_total = money(
        sum((Decimal(str(item["financial_impact"])) for item in observation.violations), ZERO)
    )
    root_total = money(
        sum(
            (Decimal(str(item["total_attributable_impact"])) for item in observation.root_causes),
            ZERO,
        )
    )
    direct = money(
        sum((Decimal(str(item["direct_impact"])) for item in observation.root_causes), ZERO)
    )
    downstream = money(
        sum((Decimal(str(item["downstream_impact"])) for item in observation.root_causes), ZERO)
    )

    # Which labeled rows contribute nothing to the predicted total because every
    # failure mode they carry is undetected? Their loss is the expected gap.
    undetected = {
        instance
        for instance in expected
        if instance not in predicted and instance not in dispositions.aliased_false_negatives
    }
    undetected_types_by_row: dict[str, set[str]] = defaultdict(set)
    for instance in undetected:
        for payment_id in expected[instance]:
            undetected_types_by_row[payment_id].add(instance.violation_type)
    blind_spot_loss = ZERO
    blind_spot_rows = 0
    blind_spot_by_type: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for row in truth:
        if not row.violation_types or row.expected_loss == ZERO:
            continue
        if set(row.violation_types) <= undetected_types_by_row.get(row.payment_id, set()):
            blind_spot_loss = money(blind_spot_loss + row.expected_loss)
            blind_spot_rows += 1
            for violation_type in row.violation_types:
                blind_spot_by_type[violation_type] = money(
                    blind_spot_by_type[violation_type] + row.expected_loss
                )

    gap = money(expected_total - predicted_total)
    residual = money(gap - blind_spot_loss)
    return {
        "scope": (
            "Decimal-only. Expected leakage is the labeled verified loss; "
            "predicted leakage is the run's attributable leakage. Delay is cash "
            "timing, never leakage, and is reported separately."
        ),
        "expected_verified_leakage": str(expected_total),
        "predicted_attributable_leakage": str(predicted_total),
        "absolute_error": str(money(abs(gap))),
        "percentage_error": (
            None if expected_total == ZERO else round(float(abs(gap) / expected_total) * 100, 4)
        ),
        "direct_impact": str(direct),
        "downstream_impact": str(downstream),
        "cash_delayed_not_leakage": str(money(Decimal(str(observation.summary["cash_delayed"])))),
        "gap_attributable_to_blind_spots": str(blind_spot_loss),
        "gap_by_undetected_type": {
            key: str(value) for key, value in sorted(blind_spot_by_type.items())
        },
        "blind_spot_labeled_rows": blind_spot_rows,
        "residual_unexplained_gap": str(residual),
        "double_counting_checks": {
            "sum_violation_impact": str(violation_total),
            "sum_root_cause_attributable_impact": str(root_total),
            "run_summary_verified_leakage": str(predicted_total),
            "violations_equal_summary": violation_total == predicted_total,
            "root_causes_equal_violations": root_total == violation_total,
            "direct_plus_downstream_equals_total": money(direct + downstream) == root_total,
            "every_violation_attributed_once": len(
                [item for item in observation.violations if item.get("root_cause_id")]
            )
            == len(observation.violations),
        },
    }


# --------------------------------------------------------------------------- #
# Control versioning
# --------------------------------------------------------------------------- #


def control_versioning(observation: Observation, index: SourceIndex) -> dict[str, Any]:
    """Effective-date selection, verified against each target's own timestamp.

    Two independent checks, because an engine must not be able to self-certify:
    the recorded selection date must fall inside the applied version's window,
    and where the source data independently supplies the target's timestamp the
    recorded date must equal it.
    """

    control_by_id = {control["id"]: control for control in observation.controls}

    def window(control: dict[str, Any]) -> tuple[date, date | None]:
        start = date.fromisoformat(control["effective_from"])
        end = date.fromisoformat(control["effective_to"]) if control.get("effective_to") else None
        return start, end

    applied: dict[str, dict[str, Any]] = {}
    out_of_window: list[dict[str, str]] = []
    unrecorded: list[dict[str, str]] = []
    disagreeing: list[dict[str, str]] = []
    for evaluation in observation.evaluations:
        control = control_by_id.get(evaluation["control_id"])
        selection = (evaluation.get("evidence") or {}).get("control_version_selection") or {}
        entry = applied.setdefault(
            evaluation["control_id"],
            {
                "control_id": evaluation["control_id"],
                "control_version": evaluation["control_version"],
                "logical_control_key": (control or {}).get("logical_control_key", ""),
                "expected": (control or {}).get("expected", ""),
                "effective_from": (control or {}).get("effective_from"),
                "effective_to": (control or {}).get("effective_to"),
                "evaluations": 0,
                "selection_basis_recorded": 0,
                "selection_inside_window": 0,
                "corroborated_by_source_timestamp": 0,
            },
        )
        entry["evaluations"] += 1
        selected_on = selection.get("selected_on")
        if control is None or not selected_on:
            unrecorded.append(
                {"target_id": evaluation["target_id"], "control_id": evaluation["control_id"]}
            )
            continue
        entry["selection_basis_recorded"] += 1
        selected = date.fromisoformat(selected_on)
        start, end = window(control)
        if start <= selected and (end is None or selected <= end):
            entry["selection_inside_window"] += 1
        else:
            out_of_window.append(
                {
                    "target_id": evaluation["target_id"],
                    "control_id": evaluation["control_id"],
                    "selected_on": selected_on,
                    "window": f"{control['effective_from']}..{control.get('effective_to')}",
                }
            )
        own = index.captured_at.get(evaluation["target_id"])
        if own is not None:
            if own.date() == selected:
                entry["corroborated_by_source_timestamp"] += 1
            else:
                disagreeing.append(
                    {
                        "target_id": evaluation["target_id"],
                        "control_id": evaluation["control_id"],
                        "selected_on": selected_on,
                        "source_timestamp": own.date().isoformat(),
                    }
                )
    versioned_keys = defaultdict(set)
    for entry in applied.values():
        if entry["logical_control_key"]:
            versioned_keys[entry["logical_control_key"]].add(entry["control_id"])
    return {
        "scope": (
            "Every control evaluation must select its version from the target's "
            "own transaction timestamp against effective_from/effective_to, "
            "never from 'latest approved'."
        ),
        "applied_controls": sorted(applied.values(), key=lambda item: item["control_id"]),
        "logical_keys_with_multiple_versions_applied": sorted(
            key for key, value in versioned_keys.items() if len(value) > 1
        ),
        "evaluations_outside_control_window": len(out_of_window),
        "outside_window_samples": out_of_window[:6],
        "evaluations_without_recorded_selection_basis": len(unrecorded),
        "unrecorded_selection_samples": unrecorded[:6],
        "evaluations_disagreeing_with_source_timestamp": len(disagreeing),
        "disagreeing_samples": disagreeing[:6],
        "effective_date_selection_correct": not out_of_window
        and not unrecorded
        and not disagreeing,
    }


def performance(observation: Observation) -> dict[str, Any]:
    summary = observation.summary
    return {
        "transactions": summary["transaction_count"],
        "events": summary["event_count"],
        "relationships": summary["relationship_count"],
        "control_evaluations": summary["control_evaluation_count"],
        "deterministic_processing_ms": summary["deterministic_processing_ms"],
        "persistence_ms": summary.get("persistence_ms"),
        "total_processing_ms": summary.get("total_processing_ms"),
        "evaluations_per_second": summary["evaluations_per_second"],
    }


def run_summary_invariant(observation: Observation) -> dict[str, Any]:
    """``pass + violation + warning + unresolved == control_evaluation_count``."""

    breakdown = observation.summary["breakdown"]
    total = (
        breakdown["passed"]
        + breakdown["violation"]
        + breakdown["warning"]
        + breakdown["unresolved"]
    )
    return {
        "breakdown": breakdown,
        "control_evaluation_count": observation.summary["control_evaluation_count"],
        "breakdown_sums_to_evaluation_count": total
        == observation.summary["control_evaluation_count"],
        "unresolved_control_count": observation.summary["unresolved_control_count"],
        "unresolved_relationship_count": observation.summary["unresolved_relationship_count"],
        "unresolved_quantities_are_separate_fields": True,
        "ground_truth_available": observation.summary["ground_truth_available"],
        "metrics_scope": observation.summary.get("metrics_scope"),
    }


# --------------------------------------------------------------------------- #
# Report assembly
# --------------------------------------------------------------------------- #


def build_report(
    observation: Observation,
    truth: tuple[TruthRow, ...],
    index: SourceIndex,
    manifest: dict[str, Any],
) -> dict[str, Any]:
    """Assemble every scope into the machine-readable evaluation report."""

    governance = Governance.from_controls(list(observation.controls))
    expected = expected_instances(truth, index)
    predicted = predicted_instances(observation.violations)
    dispositions = classify_dispositions(expected, predicted, truth, index, governance)
    return {
        "dataset": {
            "dataset_id": observation.dataset_id,
            "dataset_type": observation.dataset_type,
            "run_id": observation.run_id,
            "labeled_rows": len(truth),
            "expected_status_counts": {
                status: sum(1 for row in truth if row.expected_status == status)
                for status in sorted({row.expected_status for row in truth})
            },
            "manifest_counts": manifest.get("counts", {}),
            "ground_truth_read_only_after_execution": True,
        },
        "payment_primary_detection": payment_primary_detection(truth, observation),
        "approved_control_execution": approved_control_execution(
            expected, predicted, governance, dispositions
        ),
        "planted_anomaly_coverage": planted_anomaly_coverage(
            expected, predicted, governance, dispositions, manifest
        ),
        "violation_types": violation_type_quality(expected, predicted, governance, dispositions),
        "entity_level": entity_level_quality(expected, predicted, index, dispositions),
        "relationship_resolution": relationship_resolution(truth, index, observation),
        "lineage": lineage_quality(truth, observation),
        "financial_impact": financial_impact(
            truth, index, expected, predicted, dispositions, observation
        ),
        "control_versioning": control_versioning(observation, index),
        "run_summary_invariant": run_summary_invariant(observation),
        "false_positive_dispositions": [
            {**instance.as_dict(), **detail}
            for instance, detail in sorted(dispositions.false_positive.items())
        ],
        "false_negative_dispositions": [
            {**instance.as_dict(), **detail}
            for instance, detail in sorted(dispositions.false_negative.items())
        ],
        "performance": performance(observation),
    }
