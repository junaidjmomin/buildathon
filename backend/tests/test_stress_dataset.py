"""Generic properties for the independent 1,000-row production stress fixture.

These tests intentionally never assert a payment, settlement, or root-cause ID.
The ground-truth file is read only by evaluation tests and is not passed to the
deterministic ingestion/control pipeline.
"""

import csv

from tests.fixtures.datasets import load_dataset_fixture

STRESS = load_dataset_fixture("prod_stress")


def _rows(name: str) -> list[dict[str, str]]:
    with STRESS.source_paths[name].open(newline="") as handle:
        return list(csv.DictReader(handle))


def test_stress_manifest_identity_and_counts() -> None:
    assert STRESS.dataset_id == "novacart_prod_stress_v1"
    assert STRESS.dataset_type == "LABELED_STRESS"
    assert len(_rows("payments")) == 1000
    assert len(_rows("orders")) == 1000
    assert len(_rows("settlements")) == 930
    assert len(_rows("bank")) == 99
    assert len(_rows("refunds")) == 94
    assert len(_rows("chargebacks")) == 20


def test_stress_fixture_has_no_canonical_id_dependency() -> None:
    canonical = {"PAY_82HD9", "REF_91", "SET_1042", "RC_MDR_01", "UNR_003"}
    observed = set()
    for name in STRESS.source_paths:
        for row in _rows(name):
            observed.update(value for value in row.values() if value)
    assert canonical.isdisjoint(observed)


def test_ground_truth_is_evaluation_only() -> None:
    assert STRESS.ground_truth is not None
    assert STRESS.ground_truth.name == "ground_truth.csv"
    assert STRESS.ground_truth.parent == STRESS.root
    # The fixture loader exposes ground truth separately; source_paths contains
    # only files eligible for ingestion.
    assert "ground_truth" not in STRESS.source_paths


def test_stress_payment_ids_are_generated_and_unique() -> None:
    ids = [row["payment_id"] for row in _rows("payments")]
    assert len(ids) == len(set(ids)) == 1000
    assert all(value for value in ids)
