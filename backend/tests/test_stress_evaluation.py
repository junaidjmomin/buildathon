"""Scored evaluation of the labeled production stress fixture.

The engine runs first and is scored afterwards: nothing in ``app`` reads a
label, and this module reads the label file only after the run has completed and
persisted. Every metric is reported on one explicit scope — see
``tests/support/scoring`` for why a settlement finding is not a payment finding
and why a draft-governed failure mode is not an execution failure.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from tests.fixtures.datasets import load_dataset_fixture
from tests.support import runner
from tests.support.scoring import (
    APPROVED_CONTROL,
    FN_UNEXPLAINED,
    FP_UNEXPLAINED,
    Governance,
    Observation,
    SourceIndex,
    TruthRow,
    build_report,
    classify_dispositions,
    expected_instances,
    load_truth,
    predicted_instances,
)

STRESS = load_dataset_fixture("prod_stress")
REPORT_PATH = Path(__file__).parents[1] / "test-results" / "prod_stress_evaluation.json"


@dataclass(frozen=True)
class Scored:
    observation: Observation
    truth: tuple[TruthRow, ...]
    index: SourceIndex
    report: dict[str, Any]
    invariance: dict[str, Any]


def _truth() -> tuple[TruthRow, ...]:
    assert STRESS.ground_truth is not None, "The stress fixture must ship a label file"
    return load_truth(STRESS.ground_truth)


@pytest.fixture(scope="module")
def scored(tmp_path_factory: pytest.TempPathFactory) -> Scored:
    """Execute the bundle four ways once, then score the baseline run."""

    database = tmp_path_factory.mktemp("stress") / "stress.db"
    index = SourceIndex.from_paths(STRESS.source_paths)
    truth = _truth()
    with runner.api_client(database) as client:
        original = runner.read_bundle(STRESS.source_paths)
        baseline_id = runner.execute_bundle(client, original, name="stress baseline")
        baseline = runner.observe(
            client,
            baseline_id,
            dataset_id=STRESS.dataset_id,
            dataset_type=STRESS.dataset_type,
        )

        renamed_files, mapping = runner.rename_identifiers(original)
        renamed_id = runner.execute_bundle(client, renamed_files, name="stress renamed")
        renamed = runner.observe(
            client, renamed_id, dataset_id=STRESS.dataset_id, dataset_type=STRESS.dataset_type
        )

        shuffled_files = runner.shuffle_rows(original, seed=STRESS.manifest["seed"])
        shuffled_id = runner.execute_bundle(client, shuffled_files, name="stress shuffled")
        shuffled = runner.observe(
            client, shuffled_id, dataset_id=STRESS.dataset_id, dataset_type=STRESS.dataset_type
        )

        # Dataset identity is provenance: the same bytes under a different run
        # name and a different dataset label must reach identical conclusions.
        relabeled_id = runner.execute_bundle(client, original, name="unrelated-dataset-identity")
        relabeled = runner.observe(
            client, relabeled_id, dataset_id="unrelated_dataset_v9", dataset_type="DEMO"
        )

    baseline_conclusions = runner.financial_conclusions(baseline)
    invariance = {
        "id_rename": {
            "basis": (
                "Every identifier in the bundle renamed consistently, then "
                "conclusions compared under the bijection: same findings about "
                "the same entities, not merely the same totals."
            ),
            "identifiers_renamed": len(mapping),
            "equivalent": runner.financial_conclusions(baseline, rename=mapping)
            == runner.financial_conclusions(renamed),
        },
        "row_order": {
            "basis": "Data rows of every source file independently shuffled.",
            "seed": STRESS.manifest["seed"],
            "equivalent": baseline_conclusions == runner.financial_conclusions(shuffled),
        },
        "dataset_metadata": {
            "basis": (
                "Identical bytes executed under a different run name and dataset "
                "label; only provenance differs."
            ),
            "equivalent": baseline_conclusions == runner.financial_conclusions(relabeled),
        },
    }
    report = build_report(baseline, truth, index, STRESS.manifest)
    report["invariance"] = invariance
    return Scored(
        observation=baseline, truth=truth, index=index, report=report, invariance=invariance
    )


# --------------------------------------------------------------------------- #
# Ground-truth hygiene
# --------------------------------------------------------------------------- #


def test_ground_truth_is_schema_complete_and_self_consistent() -> None:
    truth = _truth()
    assert len(truth) == 1000
    for row in truth:
        assert row.payment_id
        assert row.expected_status in {"PASS", "VIOLATION", "UNRESOLVED_RELATIONSHIP"}
        # A status and its labels must agree, and the primary/downstream split
        # must partition the labels exactly.
        assert bool(row.violation_types) == (row.expected_status == "VIOLATION")
        assert set(row.primary_violation_types) | set(row.downstream_violation_types) == set(
            row.violation_types
        )
        assert not set(row.primary_violation_types) & set(row.downstream_violation_types)
        if row.expected_status != "VIOLATION":
            assert row.expected_loss == 0


def test_expected_findings_resolve_to_exactly_one_native_entity() -> None:
    """Labels recorded per payment row collapse onto the entity that owns them."""

    truth = _truth()
    index = SourceIndex.from_paths(STRESS.source_paths)
    expected = expected_instances(truth, index)
    by_entity: dict[str, set[str]] = {}
    for instance in expected:
        by_entity.setdefault(instance.entity_type, set()).add(instance.violation_type)
    assert by_entity["PAYMENT"]
    assert by_entity["SETTLEMENT"]
    # No label may resolve to more than one entity class.
    for violation_type in {item.violation_type for item in expected}:
        owners = {item.entity_type for item in expected if item.violation_type == violation_type}
        assert len(owners) == 1, (violation_type, owners)
    # Projection actually collapses: settlement-native labels are recorded on
    # many payment rows but describe far fewer settlements.
    settlement_labels = sum(
        len(rows) for instance, rows in expected.items() if instance.entity_type == "SETTLEMENT"
    )
    settlement_instances = sum(1 for item in expected if item.entity_type == "SETTLEMENT")
    assert settlement_labels > settlement_instances


# --------------------------------------------------------------------------- #
# Scope A–G
# --------------------------------------------------------------------------- #


def test_scope_a_payment_primary_detection(scored: Scored) -> None:
    body = scored.report["payment_primary_detection"]
    assert body["universe"] == len(scored.truth)
    assert body["predicted_positive"] == body["true_positive"] + body["false_positive"]
    assert body["predictions_outside_labeled_universe"] == 0
    assert body["false_positive"] == 0, body["false_positive_samples"]
    assert body["false_negative"] == 0, body["false_negative_samples"]
    assert body["precision"] == 1.0
    assert body["recall"] == 1.0
    assert body["false_positive_rate"] == 0.0


def test_scope_b_approved_control_execution(scored: Scored) -> None:
    body = scored.report["approved_control_execution"]
    # The approved scope is derived from the registry, never from the labels.
    assert body["approved_control_ids"]
    assert "UNSUPPORTED_FEE" in body["excluded_draft_only_modes"]
    assert "DUPLICATE_CHARGEBACK_FEE" not in body["claimed_by_approved_controls"]
    assert body["unexplained_false_positives"] == []
    assert body["unexplained_false_negatives"] == []
    adjusted = body["adjusted"]
    assert adjusted["false_positive"] == 0
    assert adjusted["false_negative"] == 0
    assert adjusted["precision"] == 1.0
    assert adjusted["recall"] == 1.0
    assert adjusted["f1"] == 1.0


def test_scope_c_planted_anomaly_coverage(scored: Scored) -> None:
    body = scored.report["planted_anomaly_coverage"]
    assert body["planted_instances"] > 0
    assert body["coverage_of_approved_governed_modes"] == 1.0
    # Blind spots must remain blind spots: every uncovered mode is governed by a
    # draft candidate or by no control at all, never by an approved control.
    for item in body["blind_spots"]:
        assert item["governance"] != APPROVED_CONTROL
    uncovered_approved = [
        item
        for item in body["by_type"]
        if item["governance"] == APPROVED_CONTROL and item["undetected"] > 0
    ]
    assert uncovered_approved == []
    # Ambiguous relationships belong to scope E, not to violation coverage.
    relationship = body["scored_in_relationship_scope"]
    assert relationship
    for item in relationship:
        assert item["scored_in"] == "relationship_resolution"
    assert all(item["governance"] != "RELATIONSHIP_RESOLUTION" for item in body["by_type"])


def test_scope_d_violation_type_quality(scored: Scored) -> None:
    rows = scored.report["violation_types"]
    assert rows
    for row in rows:
        assert row["native_entity"] != "UNKNOWN", row["violation_type"]
        assert row["unexplained_false_positives"] == 0, row
        assert row["adjusted"]["false_positive"] == 0, row
        if row["governance"] == APPROVED_CONTROL:
            assert row["unexplained_false_negatives"] == 0, row
            assert row["adjusted"]["false_negative"] == 0, row
            # Every approved-governed type must be perfect once explained
            # findings are accounted for; strict may differ and that is reported.
            assert row["adjusted"]["precision"] in (1.0, None), row
    covered = {row["violation_type"] for row in rows if row["strict"]["true_positive"] > 0}
    assert covered


def test_scope_d_entity_level_quality(scored: Scored) -> None:
    body = scored.report["entity_level"]
    for key in ("payment", "settlement", "chargeback", "relationship"):
        assert body[key]["unexplained_false_positives"] == 0, (key, body[key])
    assert body["payment"]["false_negative"] == 0
    assert body["refund"]["scored_under"] == "payment"
    assert body["refund"]["refund_records"] > 0


def test_scope_e_relationship_resolution(scored: Scored) -> None:
    body = scored.report["relationship_resolution"]
    assert body["expected_ambiguous_settlements"] > 0
    assert body["missed_unresolved"] == 0, body["missed_unresolved_samples"]
    assert body["false_unresolved"] == 0, body["false_unresolved_samples"]
    assert body["forced_incorrect_matches"] == 0
    assert body["accuracy"] == 1.0
    assert body["correctly_unresolved"] == body["expected_ambiguous_settlements"]


def test_scope_f_lineage_quality(scored: Scored) -> None:
    body = scored.report["lineage"]
    assert body["primary_incorrect"] == 0, body["extra_causal_edge_samples"]
    assert body["downstream_incorrect"] == 0, body["missing_causal_edge_samples"]
    assert body["missing_causal_edges"] == 0
    assert body["accuracy"] == 1.0
    chain = body["mdr_rate_to_gst_on_fee"]
    assert chain["downstream_gst_violations"] > 0
    assert chain["chain_intact"]
    assert body["persisted_lineage_integrity"]["all_violations_rooted"]


def test_scope_g_financial_impact_reconciles(scored: Scored) -> None:
    body = scored.report["financial_impact"]
    checks = body["double_counting_checks"]
    assert checks["violations_equal_summary"]
    assert checks["root_causes_equal_violations"]
    assert checks["direct_plus_downstream_equals_total"]
    assert checks["every_violation_attributed_once"]
    # The whole gap between expected and predicted leakage must be attributable
    # to declared blind spots; anything else is an unexplained accounting error.
    assert body["residual_unexplained_gap"] == "0.00", body
    assert body["gap_by_undetected_type"]


def test_control_versioning_selects_on_effective_dates(scored: Scored) -> None:
    body = scored.report["control_versioning"]
    assert body["evaluations_outside_control_window"] == 0, body["outside_window_samples"]
    # The engine must state which date put a version in force, and that date must
    # agree with the source data wherever the source supplies it independently.
    assert body["evaluations_without_recorded_selection_basis"] == 0, body[
        "unrecorded_selection_samples"
    ]
    assert body["evaluations_disagreeing_with_source_timestamp"] == 0, body["disagreeing_samples"]
    assert body["effective_date_selection_correct"]
    assert body["logical_keys_with_multiple_versions_applied"], (
        "The fixture spans a contract amendment, so at least one logical control "
        "key must apply more than one version within a single run"
    )


def test_run_summary_invariant_holds(scored: Scored) -> None:
    body = scored.report["run_summary_invariant"]
    assert body["breakdown_sums_to_evaluation_count"]
    assert body["unresolved_control_count"] == body["breakdown"]["unresolved"]
    assert body["ground_truth_available"] is False


# --------------------------------------------------------------------------- #
# Genericity and invariance (P0)
# --------------------------------------------------------------------------- #


def test_conclusions_are_invariant_under_consistent_id_renaming(scored: Scored) -> None:
    body = scored.invariance["id_rename"]
    assert body["identifiers_renamed"] > 1000
    assert body["equivalent"]


def test_conclusions_are_invariant_under_row_shuffling(scored: Scored) -> None:
    assert scored.invariance["row_order"]["equivalent"]


def test_conclusions_are_invariant_under_dataset_metadata(scored: Scored) -> None:
    assert scored.invariance["dataset_metadata"]["equivalent"]


# --------------------------------------------------------------------------- #
# Report
# --------------------------------------------------------------------------- #


def test_evaluation_report_is_written(scored: Scored) -> None:
    REPORT_PATH.parent.mkdir(exist_ok=True)
    REPORT_PATH.write_text(json.dumps(scored.report, indent=2, sort_keys=False))
    reloaded = json.loads(REPORT_PATH.read_text())
    for key in (
        "dataset",
        "payment_primary_detection",
        "approved_control_execution",
        "planted_anomaly_coverage",
        "violation_types",
        "entity_level",
        "relationship_resolution",
        "lineage",
        "financial_impact",
        "control_versioning",
        "invariance",
        "performance",
    ):
        assert key in reloaded, key
    # Money stays a Decimal string end to end.
    assert isinstance(reloaded["financial_impact"]["expected_verified_leakage"], str)
    assert isinstance(reloaded["financial_impact"]["predicted_attributable_leakage"], str)


def test_dispositions_are_fully_explained(scored: Scored) -> None:
    """No finding is left unaccounted for on either side of the comparison."""

    governance = Governance.from_controls(list(scored.observation.controls))
    expected = expected_instances(scored.truth, scored.index)
    predicted = predicted_instances(scored.observation.violations)
    dispositions = classify_dispositions(
        expected, predicted, scored.truth, scored.index, governance
    )
    unexplained_fp = [
        instance
        for instance, detail in dispositions.false_positive.items()
        if detail["disposition"] == FP_UNEXPLAINED
    ]
    unexplained_fn = [
        instance
        for instance, detail in dispositions.false_negative.items()
        if detail["disposition"] == FN_UNEXPLAINED
    ]
    assert unexplained_fp == [], unexplained_fp
    assert unexplained_fn == [], unexplained_fn
