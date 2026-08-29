"""Clause-driven evaluation against the new, independent CSV fixture.

The six source files are executed through the public upload/run API first.  The
evaluation-only files are opened only after the run has persisted, and never
enter ingestion, matching, control evaluation, lineage, or root-cause code.
This module is deliberately separate from the canonical demo and stress suites.
"""

from __future__ import annotations

import asyncio
import csv
import hashlib
import json
from collections import defaultdict
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

import pytest

from app.agents.control_workflows import AgreementControlCompiler
from app.ingestion.pdf import (
    extract_agreement_pages,
    infer_agreement_effective_from,
    segment_agreement_clauses,
)
from tests.fixtures.datasets import DatasetFixture, load_dataset_fixture
from tests.support import runner
from tests.support.scoring import (
    Instance,
    Observation,
    SourceIndex,
    TruthRow,
    build_report,
    load_truth,
    native_entity,
)

CLAUSE = load_dataset_fixture("clause_driven")
REPORT_PATH = Path(__file__).parents[1] / "test-results" / "clause_driven_evaluation.json"
EVALUATION_FILENAMES = frozenset(CLAUSE.evaluation_files)
MONEY_ZERO = Decimal("0.00")
CENT = Decimal("0.01")

CANONICAL_NATIVE_ENTITIES: dict[str, str] = {
    "CHARGEBACK_FEE_OVERCHARGE": "CHARGEBACK",
    "FAILED_PAYMENT_IN_SETTLEMENT": "SETTLEMENT",
    "UNSUPPORTED_FEE": "SETTLEMENT",
}

CANONICAL_MAPPING: dict[str, dict[str, str]] = {
    "CHARGEBACK_FEE_OVERCHARGE": {
        "canonical_type": "CHARGEBACK_FEE_OVERCHARGE",
        "native_entity": "CHARGEBACK",
        "engine_type": "NOT_IMPLEMENTED",
    },
    "FAILED_PAYMENT_IN_SETTLEMENT": {
        "canonical_type": "FAILED_PAYMENT_IN_SETTLEMENT",
        "native_entity": "SETTLEMENT",
        "engine_type": "NOT_IMPLEMENTED",
    },
    "UNSUPPORTED_FEE": {
        "canonical_type": "UNSUPPORTED_FEE",
        "native_entity": "SETTLEMENT",
        "engine_type": "UNSUPPORTED_FEE (draft candidate)",
        "observed_alias": "SETTLEMENT_ARITHMETIC",
    },
}

EXPECTED_CONTROL_PROPOSALS: dict[str, dict[str, Any]] = {
    "DOMESTIC_CARD_MDR#1": {
        "clause": "4.2",
        "page": 4,
        "rate": "0.0155",
        "effective_from": "2026-01-01",
        "effective_to": "2026-08-31",
    },
    "DOMESTIC_CARD_MDR#2": {
        "clause": "A1.2",
        "page": 9,
        "rate": "0.0165",
        "effective_from": "2026-09-01",
        "effective_to": None,
    },
    "GST_ON_VALID_FEE#1": {"clause": "4.3", "page": 4, "rate": "0.18"},
    "UNSUPPORTED_SETTLEMENT_FEE#1": {
        "clause": "4.6",
        "page": 5,
        "expected_amount": "0.00",
    },
    "CHARGEBACK_ADMIN_FEE#1": {
        "clause": "4.7",
        "page": 5,
        "fee": "250.00",
        "maximum_deductions": 1,
        "native_entity": "CHARGEBACK",
    },
    "CAPTURE_TO_SETTLEMENT_SLA#1": {"clause": "6.1", "page": 6},
    "SETTLEMENT_BANK_ARITHMETIC#1": {"clause": "6.2", "page": 6},
    "REFUND_PRINCIPAL_INTEGRITY#1": {
        "clause": "7.2",
        "page": 7,
        "maximum_deductions": 1,
        "refund_fee": "0.00",
        "tolerance": "0.01",
    },
    "REFUND_AMOUNT_LIMIT#1": {"clause": "7.3", "page": 7},
}


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, (date,)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_jsonable(item) for item in value]
    return value


def _confusion(expected: set[Instance], predicted: set[Instance]) -> dict[str, Any]:
    tp = len(expected & predicted)
    fp = len(predicted - expected)
    fn = len(expected - predicted)
    denominator = 2 * tp + fp + fn
    return {
        "true_positive": tp,
        "false_positive": fp,
        "false_negative": fn,
        "predicted_positive": tp + fp,
        "expected_positive": tp + fn,
        "precision": None if tp + fp == 0 else round(tp / (tp + fp), 6),
        "recall": None if tp + fn == 0 else round(tp / (tp + fn), 6),
        "f1": None if denominator == 0 else round(2 * tp / denominator, 6),
    }


def _native_for(violation_type: str) -> str:
    return CANONICAL_NATIVE_ENTITIES.get(violation_type, native_entity(violation_type))


def _expected_by_type(truth: tuple[TruthRow, ...], index: SourceIndex) -> dict[str, set[Instance]]:
    result: dict[str, set[Instance]] = defaultdict(set)
    for row in truth:
        for violation_type in row.violation_types:
            native = _native_for(violation_type)
            if native == "PAYMENT":
                result[violation_type].add(Instance("PAYMENT", row.payment_id, violation_type))
            elif native == "SETTLEMENT":
                settlement_id = index.settlement_of_payment.get(row.payment_id)
                if settlement_id:
                    result[violation_type].add(
                        Instance("SETTLEMENT", settlement_id, violation_type)
                    )
            elif native == "CHARGEBACK":
                for chargeback_id in index.chargebacks_of_payment.get(row.payment_id, ()):
                    result[violation_type].add(
                        Instance("CHARGEBACK", chargeback_id, violation_type)
                    )
    return result


def _predicted_by_type(observation: Observation) -> dict[str, set[Instance]]:
    result: dict[str, set[Instance]] = defaultdict(set)
    for violation in observation.violations:
        result[violation["violation_type"]].add(
            Instance(
                violation["target_type"],
                violation["payment_id"],
                violation["violation_type"],
            )
        )
    return result


def _manifest_integrity(fixture: DatasetFixture) -> dict[str, Any]:
    source = {name: _rows(path) for name, path in fixture.source_paths.items()}
    payments = source["payments"]
    actual = {
        "orders": len(source["orders"]),
        "payments": len(payments),
        "captured_payments": sum(row["status"].lower() == "captured" for row in payments),
        "failed_payments": sum(row["status"].lower() == "failed" for row in payments),
        "settlement_rows": len(source["settlements"]),
        "unique_settlements": len({row["settlement_id"] for row in source["settlements"]}),
        "bank_rows": len(source["bank"]),
        "refunds": len(source["refunds"]),
        "chargebacks": len(source["chargebacks"]),
    }
    expected = fixture.manifest["counts"]
    return {
        "expected": expected,
        "actual": actual,
        "all_counts_match": actual == expected,
        "identity": {
            "dataset_id": fixture.manifest["dataset_id"],
            "dataset_type": fixture.manifest["dataset_type"],
            "agreement_id": fixture.manifest["agreement_id"],
            "dataset_id_matches_fixture": fixture.dataset_id == fixture.manifest["dataset_id"],
            "dataset_type_matches_fixture": fixture.dataset_type
            == fixture.manifest["dataset_type"],
        },
        "engine_input_files": sorted(fixture.source_paths),
        "evaluation_only_files": sorted(path.name for path in fixture.evaluation_files.values()),
        "evaluation_files_excluded_from_engine": not set(fixture.source_paths.values())
        & set(fixture.evaluation_files.values()),
        "manifest_is_metadata_only": True,
    }


def _clause_models(pdf: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    content = pdf.read_bytes()
    pages = extract_agreement_pages(
        content,
        max_pages=200,
        max_page_content_bytes=5 * 1024 * 1024,
        max_extracted_chars=500_000,
    )
    effective = infer_agreement_effective_from(pages, fallback=date(2026, 1, 1))
    segmented = segment_agreement_clauses(pages, agreement_effective_from=effective)
    clauses = [
        {
            "id": f"CLAUSE_{item.clause_number.replace('.', '_')}",
            "reference": item.clause_number,
            "page": item.page_number,
            "heading": item.clause_title,
            "text": item.text,
            "effective_from": item.effective_from.isoformat(),
            "effective_to": item.effective_to.isoformat() if item.effective_to else None,
            "source_type": "PDF_TEXT_EXTRACTION",
            "source_offsets": {
                "page_number": item.page_number,
                "start_offset": item.start_offset,
                "end_offset": item.end_offset,
                "offset_basis": "normalized_page_text",
            },
        }
        for item in segmented
    ]
    execution = asyncio.run(
        AgreementControlCompiler(provider=None).run(
            tenant_id="clause-evaluation",
            agreement_id="fixture-agreement",
            clauses=clauses,
            seed_candidates=[],
        )
    )
    by_id = {item["id"]: item for item in clauses}
    proposals: list[dict[str, Any]] = []
    for candidate in execution.proposals:
        raw = candidate.model_dump(mode="json")
        clause = by_id[raw["clause_id"]]
        proposals.append(
            {
                "logical_control_key": raw["logical_control_key"],
                "version": raw["version"],
                "clause": clause["reference"],
                "page": clause["page"],
                "title": clause["heading"],
                "effective_from": raw["effective_from"],
                "effective_to": raw.get("effective_to"),
                "parameters": raw["parameters"],
                "source_offsets": clause["source_offsets"],
                "source_excerpt": clause["text"],
            }
        )
    return clauses, {
        "pdf_sha256": hashlib.sha256(content).hexdigest(),
        "pages_with_text": len(pages),
        "records_detected": len(clauses),
        "numbered_clauses": sum(
            not item["reference"].startswith("UNNUMBERED_") for item in clauses
        ),
        "unnumbered_source_sections": [
            item["reference"] for item in clauses if item["reference"].startswith("UNNUMBERED_")
        ],
        "controls_proposed": len(proposals),
        "proposals": sorted(proposals, key=lambda item: (item["clause"], item["version"])),
        "validation_warnings": list(execution.validation_warnings),
        "execution_status": execution.status,
        "needs_review_label": "Needs review",
        "confidence_is_not_presented_as_model_confidence": True,
        "unnumbered_sections_not_controls": all(
            not item["clause"].startswith("UNNUMBERED_") for item in proposals
        ),
    }


def _clause_extraction_result(fixture: DatasetFixture) -> dict[str, Any]:
    clauses, report = _clause_models(fixture.root / "NovaCart_Merchant_Services_Agreement_2026.pdf")
    by_ref = {item["reference"]: item for item in clauses}
    proposal_by_key = {
        f"{item['logical_control_key']}#{item['version']}": item for item in report["proposals"]
    }
    expected_checks: list[dict[str, Any]] = []
    for key, expected in EXPECTED_CONTROL_PROPOSALS.items():
        actual = proposal_by_key.get(key)
        checks = {}
        for name, value in expected.items():
            if name in {"clause", "page"}:
                continue
            actual_value = None
            if actual is not None:
                actual_value = actual.get(name, actual.get("parameters", {}).get(name))
            checks[name] = actual is not None and actual_value == value
        if actual is not None:
            checks["clause"] = actual["clause"] == expected["clause"]
            checks["page"] = actual["page"] == expected["page"]
            checks["source_excerpt_nonempty"] = bool(actual["source_excerpt"])
            checks["source_offsets_present"] = bool(actual["source_offsets"])
        expected_checks.append(
            {
                "control": key,
                "expected": expected,
                "actual": actual,
                "all_checks_pass": bool(actual) and all(checks.values()),
                "checks": checks,
            }
        )
    return {
        **report,
        "expected_proposals": expected_checks,
        "all_expected_proposals_present_and_aligned": all(
            item["all_checks_pass"] for item in expected_checks
        ),
        "cover_page_provenance_rejected": all(
            item["clause"] not in {"UNNUMBERED_1", "UNNUMBERED_10"} for item in report["proposals"]
        ),
        "clause_samples": {
            key: {
                "title": by_ref[key]["heading"],
                "page": by_ref[key]["page"],
                "text": by_ref[key]["text"],
                "source_offsets": by_ref[key]["source_offsets"],
            }
            for key in ("4.2", "4.3", "4.6", "4.7", "6.1", "6.2", "7.2", "7.3", "A1.2")
        },
    }


def _source_payment_rows(fixture: DatasetFixture) -> dict[str, dict[str, str]]:
    return {row["payment_id"]: row for row in _rows(fixture.source_paths["payments"])}


def _rounding_ids(fixture: DatasetFixture) -> set[str]:
    result: set[str] = set()
    for row in _source_payment_rows(fixture).values():
        if not (
            row["status"].lower() == "captured"
            and row["payment_method"].lower() == "card"
            and row["card_scope"].lower() == "domestic"
        ):
            continue
        rate = Decimal("0.0155") if row["captured_at"][:10] < "2026-09-01" else Decimal("0.0165")
        expected = (Decimal(row["amount"]) * rate).quantize(CENT, rounding=ROUND_HALF_UP)
        if Decimal(row["fee"]) - expected == CENT:
            result.add(row["payment_id"])
    return result


def _mdr_scenario_ids(fixture: DatasetFixture) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {"pre": set(), "stale": set(), "post_overcharge": set()}
    for row in _source_payment_rows(fixture).values():
        if not (
            row["status"].lower() == "captured"
            and row["payment_method"].lower() == "card"
            and row["card_scope"].lower() == "domestic"
        ):
            continue
        post = row["captured_at"][:10] >= "2026-09-01"
        current_rate = Decimal("0.0165") if post else Decimal("0.0155")
        expected = (Decimal(row["amount"]) * current_rate).quantize(CENT, rounding=ROUND_HALF_UP)
        difference = Decimal(row["fee"]) - expected
        if not post and difference > CENT:
            result["pre"].add(row["payment_id"])
        if post:
            old = (Decimal(row["amount"]) * Decimal("0.0155")).quantize(
                CENT, rounding=ROUND_HALF_UP
            )
            if Decimal(row["fee"]) == old and old != expected:
                result["stale"].add(row["payment_id"])
            elif difference > CENT and Decimal(row["fee"]) != old:
                result["post_overcharge"].add(row["payment_id"])
    return result


def _violation_ids(
    observation: Observation, violation_type: str, *, target_type: str | None = None
) -> set[str]:
    return {
        item["payment_id"]
        for item in observation.violations
        if item["violation_type"] == violation_type
        and (target_type is None or item["target_type"] == target_type)
    }


def _clause_coverage(
    fixture: DatasetFixture,
    truth: tuple[TruthRow, ...],
    index: SourceIndex,
    observation: Observation,
) -> list[dict[str, Any]]:
    declared = _rows(fixture.evaluation_files["clause_coverage.csv"])
    expected_by_type = _expected_by_type(truth, index)
    predicted_by_type = _predicted_by_type(observation)
    mdr = _mdr_scenario_ids(fixture)
    primary_gst = {row.payment_id for row in truth if "GST_ON_FEE" in row.primary_violation_types}
    scenario_ids: dict[str, set[str]] = {
        "Rounding tolerance": _rounding_ids(fixture),
        "Pre-amendment MDR overcharge": mdr["pre"],
        "Post-amendment stale old MDR": mdr["stale"],
        "Post-amendment MDR overcharge": mdr["post_overcharge"],
        "Independent GST error": primary_gst,
        "Late settlement": {
            row.payment_id for row in truth if "SETTLEMENT_SLA" in row.violation_types
        },
        "Duplicate refund principal deduction": {
            row.payment_id for row in truth if "DUPLICATE_REFUND_DEDUCTION" in row.violation_types
        },
        "Cumulative refund exceeds payment": {
            row.payment_id for row in truth if "REFUND_EXCEEDS_PAYMENT" in row.violation_types
        },
        "Chargeback fee overcharge": {
            row.payment_id for row in truth if "CHARGEBACK_FEE_OVERCHARGE" in row.violation_types
        },
        "Failed payment included in settlement": {
            row.payment_id for row in truth if "FAILED_PAYMENT_IN_SETTLEMENT" in row.violation_types
        },
    }
    exact_type: dict[str, str] = {
        "Pre-amendment MDR overcharge": "MDR_RATE",
        "Post-amendment stale old MDR": "MDR_RATE",
        "Post-amendment MDR overcharge": "MDR_RATE",
        "Independent GST error": "GST_ON_FEE",
        "Late settlement": "SETTLEMENT_SLA",
        "Duplicate refund principal deduction": "DUPLICATE_REFUND_DEDUCTION",
        "Cumulative refund exceeds payment": "REFUND_EXCEEDS_PAYMENT",
    }
    controls: dict[str, str] = {
        "Rounding tolerance": "CTRL_MDR_DOMESTIC / CTRL_MDR_DOMESTIC_V2",
        "Pre-amendment MDR overcharge": "CTRL_MDR_DOMESTIC",
        "Post-amendment stale old MDR": "CTRL_MDR_DOMESTIC_V2",
        "Post-amendment MDR overcharge": "CTRL_MDR_DOMESTIC_V2",
        "Independent GST error": "CTRL_GST_FEE",
        "Unlisted settlement fee": "CTRL_UNSUPPORTED_FEE_CANDIDATE (DRAFT)",
        "Chargeback fee overcharge": "No approved runtime control",
        "Late settlement": "CTRL_SETTLEMENT_SLA",
        "Bank arithmetic mismatch": "CTRL_SETTLEMENT_ARITHMETIC",
        "Ambiguous bank relationship": "Deterministic relationship matcher",
        "Missing bank credit": "CTRL_SETTLEMENT_ARITHMETIC",
        "Duplicate refund principal deduction": "CTRL_REFUND",
        "Cumulative refund exceeds payment": "CTRL_REFUND",
        "Failed payment included in settlement": "No registered runtime control",
    }
    native: dict[str, str] = {
        "Rounding tolerance": "PAYMENT",
        "Pre-amendment MDR overcharge": "PAYMENT",
        "Post-amendment stale old MDR": "PAYMENT",
        "Post-amendment MDR overcharge": "PAYMENT",
        "Independent GST error": "PAYMENT",
        "Unlisted settlement fee": "SETTLEMENT",
        "Chargeback fee overcharge": "CHARGEBACK",
        "Late settlement": "PAYMENT",
        "Bank arithmetic mismatch": "SETTLEMENT",
        "Ambiguous bank relationship": "RELATIONSHIP",
        "Missing bank credit": "SETTLEMENT",
        "Duplicate refund principal deduction": "PAYMENT",
        "Cumulative refund exceeds payment": "PAYMENT",
        "Failed payment included in settlement": "SETTLEMENT",
    }
    result: list[dict[str, Any]] = []
    for row in declared:
        scenario = row["scenario"]
        declared_count = int(row["count"])
        expected_count = declared_count
        detected_count = 0
        missed_count = 0
        false_positive_count = 0
        observed_behavior = ""
        result_status = "REVIEW"
        scope_note = ""
        ids = scenario_ids.get(scenario, set())
        if scenario == "Rounding tolerance":
            detected_count = sum(
                1
                for item in observation.evaluations
                if item["target_type"] == "PAYMENT"
                and item["target_id"] in ids
                and item["check_name"] == "MDR_RATE"
                and item["outcome"] == "PASS"
            )
            expected_count = len(ids)
            missed_count = expected_count - detected_count
            observed_behavior = "MDR evaluation PASS within INR 0.01 tolerance"
            result_status = "PASS" if missed_count == 0 else "FAIL"
        elif scenario in exact_type:
            violation_type = exact_type[scenario]
            detected_count = len(
                ids & _violation_ids(observation, violation_type, target_type="PAYMENT")
            )
            expected_count = len(ids)
            missed_count = expected_count - detected_count
            observed_behavior = f"{violation_type} on payment-native entity"
            result_status = "PASS" if missed_count == 0 else "FAIL"
        elif scenario == "Independent GST error":
            detected_count = len(
                ids & _violation_ids(observation, "GST_ON_FEE", target_type="PAYMENT")
            )
            expected_count = len(ids)
            missed_count = expected_count - detected_count
            observed_behavior = "GST_ON_FEE primary violations"
            result_status = "PASS" if missed_count == 0 else "FAIL"
        elif scenario == "Unlisted settlement fee":
            expected_set = expected_by_type["UNSUPPORTED_FEE"]
            predicted_set = predicted_by_type.get("UNSUPPORTED_FEE", set())
            detected_count = len(expected_set & predicted_set)
            expected_count = len(expected_set)
            missed_count = len(expected_set - predicted_set)
            alias_count = len(expected_set & predicted_by_type.get("SETTLEMENT_ARITHMETIC", set()))
            observed_behavior = (
                f"Exact UNSUPPORTED_FEE={detected_count}; SETTLEMENT_ARITHMETIC alias={alias_count}"
            )
            result_status = "BLIND_SPOT" if missed_count else "PASS"
            scope_note = (
                f"coverage file declares {declared_count} payment rows; "
                f"native settlement scope contains {expected_count} settlements"
            )
        elif scenario == "Chargeback fee overcharge":
            expected_set = expected_by_type["CHARGEBACK_FEE_OVERCHARGE"]
            detected_count = len(
                expected_set & predicted_by_type.get("CHARGEBACK_FEE_OVERCHARGE", set())
            )
            expected_count = len(expected_set)
            missed_count = expected_count - detected_count
            observed_behavior = "No CHARGEBACK_FEE_OVERCHARGE violation emitted"
            result_status = "BLIND_SPOT" if missed_count else "PASS"
        elif scenario == "Bank arithmetic mismatch":
            # The engine intentionally uses the shorter runtime alias
            # SETTLEMENT_ARITHMETIC for the canonical settlement-bank
            # arithmetic control.  Score by stable settlement identity while
            # retaining the canonical type in this report so the clause
            # coverage view does not turn an implementation alias into a
            # false miss.
            expected_ids = {
                row["settlement_id"]
                for row in _rows(fixture.evaluation_files["settlement_ground_truth.csv"])
                if row["violation_type"] == "SETTLEMENT_BANK_ARITHMETIC"
            }
            predicted_ids = _violation_ids(
                observation, "SETTLEMENT_ARITHMETIC", target_type="SETTLEMENT"
            )
            detected_count = len(expected_ids & predicted_ids)
            missed_count = len(expected_ids - predicted_ids)
            false_positive_count = len(predicted_ids - expected_ids)
            expected_count = len(expected_ids)
            observed_behavior = (
                "Settlement-level SETTLEMENT_BANK_ARITHMETIC (engine alias: SETTLEMENT_ARITHMETIC)"
            )
            result_status = "PASS" if missed_count == 0 else "FAIL"
        elif scenario == "Ambiguous bank relationship":
            expected_ids = {
                row["left_entity"]
                for row in _rows(fixture.evaluation_files["relationship_ground_truth.csv"])
                if row["expected_result"] == "UNRESOLVED"
            }
            unresolved_ids = {
                item["payment_id"] for item in observation.unresolved if item.get("settlement_id")
            }
            detected_count = len(expected_ids & unresolved_ids)
            expected_count = len(expected_ids)
            missed_count = len(expected_ids - unresolved_ids)
            false_positive_count = len(unresolved_ids - expected_ids)
            observed_behavior = "UNRESOLVED with no EventEdge"
            result_status = "PASS" if missed_count == 0 and false_positive_count == 0 else "FAIL"
        elif scenario == "Missing bank credit":
            expected_ids = {
                row["settlement_id"]
                for row in _rows(fixture.evaluation_files["settlement_ground_truth.csv"])
                if row["violation_type"] == "MISSING_BANK_SETTLEMENT"
            }
            predicted_ids = _violation_ids(
                observation, "MISSING_BANK_SETTLEMENT", target_type="SETTLEMENT"
            )
            detected_count = len(expected_ids & predicted_ids)
            expected_count = len(expected_ids)
            missed_count = len(expected_ids - predicted_ids)
            false_positive_count = len(predicted_ids - expected_ids)
            observed_behavior = "Settlement-level missing bank credit"
            result_status = "PASS" if missed_count == 0 else "FAIL"
        elif scenario == "Failed payment included in settlement":
            expected_set = expected_by_type["FAILED_PAYMENT_IN_SETTLEMENT"]
            predicted_set = predicted_by_type.get("FAILED_PAYMENT_IN_SETTLEMENT", set())
            detected_count = len(expected_set & predicted_set)
            expected_count = len(expected_set)
            missed_count = len(expected_set - predicted_set)
            observed_behavior = "No FAILED_PAYMENT_IN_SETTLEMENT violation emitted"
            result_status = "BLIND_SPOT" if missed_count else "PASS"
            scope_note = f"coverage file declares {declared_count} payment rows"
        else:
            # This branch is defensive: every current coverage row is handled
            # above, and a future row must be visibly reviewed instead of being
            # silently marked covered.
            observed_behavior = "No evaluator mapping exists"
            scope_note = "unmapped coverage scenario"
        result.append(
            {
                "clause": row["clause"],
                "scenario": scenario,
                "expected_behavior": row["expected"],
                "declared_count": declared_count,
                "expected_count_native_scope": expected_count,
                "observed_behavior": observed_behavior,
                "detected": detected_count,
                "missed": missed_count,
                "false_positives": false_positive_count,
                **(
                    {
                        "canonical_violation_type": "SETTLEMENT_BANK_ARITHMETIC",
                        "engine_type_used": "SETTLEMENT_ARITHMETIC",
                    }
                    if scenario == "Bank arithmetic mismatch"
                    else {}
                ),
                "applicable_approved_control": controls.get(scenario, "Review required"),
                "native_entity": native.get(scenario, "UNKNOWN"),
                "result": result_status,
                "scope_note": scope_note,
            }
        )
    return result


def _relationship_result(fixture: DatasetFixture, observation: Observation) -> dict[str, Any]:
    rows = _rows(fixture.evaluation_files["relationship_ground_truth.csv"])
    expected_ids = {row["left_entity"] for row in rows if row["expected_result"] == "UNRESOLVED"}
    unresolved_ids = {
        item["payment_id"] for item in observation.unresolved if item.get("settlement_id")
    }
    forced = expected_ids & set(observation.credited_settlement_ids)
    return {
        "scope": "Settlement-to-bank relationship ground truth; UNRESOLVED is a correct result.",
        "expected_ambiguous_relationships": len(expected_ids),
        "correctly_unresolved": len(expected_ids & unresolved_ids),
        "missed_unresolved": len(expected_ids - unresolved_ids),
        "false_unresolved": len(unresolved_ids - expected_ids),
        "forced_incorrect_matches": len(forced),
        "expected_ids": sorted(expected_ids),
        "unresolved_ids": sorted(unresolved_ids),
        "forced_ids": sorted(forced),
        "accuracy": 1.0 if expected_ids == unresolved_ids and not forced else 0.0,
    }


def _settlement_result(fixture: DatasetFixture, observation: Observation) -> dict[str, Any]:
    expected_rows = _rows(fixture.evaluation_files["settlement_ground_truth.csv"])
    result: list[dict[str, Any]] = []
    for violation_type in ("SETTLEMENT_BANK_ARITHMETIC", "MISSING_BANK_SETTLEMENT"):
        expected_ids = {
            row["settlement_id"] for row in expected_rows if row["violation_type"] == violation_type
        }
        predicted_type = (
            "SETTLEMENT_ARITHMETIC"
            if violation_type == "SETTLEMENT_BANK_ARITHMETIC"
            else violation_type
        )
        predicted_ids = _violation_ids(observation, predicted_type, target_type="SETTLEMENT")
        result.append(
            {
                "violation_type": violation_type,
                "expected": len(expected_ids),
                "detected": len(expected_ids & predicted_ids),
                "missed": len(expected_ids - predicted_ids),
                "false_positives": len(predicted_ids - expected_ids),
                "expected_ids": sorted(expected_ids),
                "detected_ids": sorted(expected_ids & predicted_ids),
                "false_positive_samples": sorted(predicted_ids - expected_ids)[:10],
                "engine_type_used": predicted_type,
            }
        )
    return {
        "scope": "Native settlement findings only; not projected into payment precision.",
        "by_type": result,
    }


def _control_versioning(
    base: dict[str, Any], fixture: DatasetFixture, observation: Observation
) -> dict[str, Any]:
    payments = _source_payment_rows(fixture)
    captured = [row for row in payments.values() if row["status"].lower() == "captured"]
    pre = [row for row in captured if row["captured_at"][:10] < "2026-09-01"]
    post = [row for row in captured if row["captured_at"][:10] >= "2026-09-01"]
    mdr_scenario = _mdr_scenario_ids(fixture)
    mdr_violations = _violation_ids(observation, "MDR_RATE", target_type="PAYMENT")
    return {
        **base,
        "captured_pre_amendment": len(pre),
        "captured_post_amendment": len(post),
        "v1_control_id": "CTRL_MDR_DOMESTIC",
        "v2_control_id": "CTRL_MDR_DOMESTIC_V2",
        "pre_amendment_v1_evaluations": next(
            (
                item["evaluations"]
                for item in base["applied_controls"]
                if item["control_id"] == "CTRL_MDR_DOMESTIC"
            ),
            0,
        ),
        "post_amendment_v2_evaluations": next(
            (
                item["evaluations"]
                for item in base["applied_controls"]
                if item["control_id"] == "CTRL_MDR_DOMESTIC_V2"
            ),
            0,
        ),
        "no_pre_amendment_v2": all(
            item["control_id"] != "CTRL_MDR_DOMESTIC_V2"
            for item in observation.evaluations
            if item["target_type"] == "PAYMENT"
            and item["target_id"] in {row["payment_id"] for row in pre}
        ),
        "no_post_amendment_v1": all(
            item["control_id"] != "CTRL_MDR_DOMESTIC"
            for item in observation.evaluations
            if item["target_type"] == "PAYMENT"
            and item["target_id"] in {row["payment_id"] for row in post}
        ),
        "stale_old_rate_cases": len(mdr_scenario["stale"]),
        "stale_old_rate_cases_detected": len(mdr_scenario["stale"] & mdr_violations),
        "post_amendment_overcharge_cases": len(mdr_scenario["post_overcharge"]),
        "post_amendment_overcharge_detected": len(mdr_scenario["post_overcharge"] & mdr_violations),
    }


def _lineage_result(
    base: dict[str, Any], fixture: DatasetFixture, observation: Observation
) -> dict[str, Any]:
    payments = _source_payment_rows(fixture)
    gst = [
        item
        for item in observation.violations
        if item["violation_type"] == "GST_ON_FEE" and item["lineage_type"] == "DOWNSTREAM"
    ]
    pre = [
        item
        for item in gst
        if payments.get(item["payment_id"], {}).get("captured_at", "")[:10] < "2026-09-01"
    ]
    post = [
        item
        for item in gst
        if payments.get(item["payment_id"], {}).get("captured_at", "")[:10] >= "2026-09-01"
    ]
    return {
        **base,
        "mdr_rate_to_gst_by_period": {
            "v1_pre_amendment": {
                "downstream_gst": len(pre),
                "valid_mdr_parent": sum(bool(item.get("parent_violation_id")) for item in pre),
            },
            "v2_post_amendment": {
                "downstream_gst": len(post),
                "valid_mdr_parent": sum(bool(item.get("parent_violation_id")) for item in post),
            },
        },
        "all_mdr_to_gst_edges_intact": all(bool(item.get("parent_violation_id")) for item in gst),
    }


def _financial_result(
    truth: tuple[TruthRow, ...], base: dict[str, Any], observation: Observation
) -> dict[str, Any]:
    expected_total = sum((row.expected_loss for row in truth), MONEY_ZERO).quantize(CENT)
    predicted_total = Decimal(str(observation.summary["verified_leakage"])).quantize(CENT)
    difference = expected_total - predicted_total
    payment_expected: dict[str, Decimal] = defaultdict(lambda: MONEY_ZERO)
    for row in truth:
        payment_expected[row.payment_id] += row.expected_loss
    payment_predicted: dict[str, Decimal] = defaultdict(lambda: MONEY_ZERO)
    for item in observation.violations:
        if item["target_type"] == "PAYMENT" and item["lineage_type"] == "PRIMARY":
            payment_predicted[item["payment_id"]] += Decimal(str(item["financial_impact"]))
    discrepancies = []
    for entity_id in sorted(set(payment_expected) | set(payment_predicted)):
        expected = payment_expected[entity_id].quantize(CENT)
        predicted = payment_predicted[entity_id].quantize(CENT)
        delta = (expected - predicted).quantize(CENT)
        if delta:
            discrepancies.append(
                {
                    "entity_id": entity_id,
                    "expected": str(expected),
                    "predicted": str(predicted),
                    "absolute_error": str(abs(delta)),
                }
            )
    discrepancies.sort(
        key=lambda item: (Decimal(item["absolute_error"]), item["entity_id"]), reverse=True
    )
    double_counting = base["double_counting_checks"]
    percentage = None
    if expected_total:
        percentage = str(
            (abs(difference) / expected_total * Decimal("100")).quantize(Decimal("0.0001"))
        )
    return {
        "scope": (
            "Raw supplied expected_verified_loss compared with runtime attributable leakage; "
            "SLA cash delay is reported separately."
        ),
        "expected_verified_loss": str(expected_total),
        "predicted_attributable_loss": str(predicted_total),
        "absolute_error": str(abs(difference)),
        "percentage_error": percentage,
        "largest_per_entity_discrepancies": discrepancies[:10],
        "cash_delayed_not_leakage": str(
            Decimal(str(observation.summary["cash_delayed"])).quantize(CENT)
        ),
        "double_counting_checks": double_counting,
        "reconciles_without_scope_adjustment": difference == MONEY_ZERO,
        "scope_warning": (
            "The fixture's expected_verified_loss includes payment-level SLA/cash-delay exposure "
            "and settlement-level labels, while runtime verified_leakage counts only attributable "
            "leakage. The difference is retained instead of being silently normalized."
        ),
    }


def _blind_spots(
    truth: tuple[TruthRow, ...], index: SourceIndex, observation: Observation
) -> list[dict[str, Any]]:
    expected = _expected_by_type(truth, index)
    predicted = _predicted_by_type(observation)
    entries = []
    for violation_type, clause, reason, candidate in (
        (
            "UNSUPPORTED_FEE",
            "4.6",
            "Draft-only control; exact violation type is not in the approved runtime registry.",
            "CTRL_UNSUPPORTED_FEE_CANDIDATE",
        ),
        (
            "CHARGEBACK_FEE_OVERCHARGE",
            "4.7/7.4",
            "No registered runtime control emits this canonical chargeback type.",
            None,
        ),
        (
            "FAILED_PAYMENT_IN_SETTLEMENT",
            "1.3/6.2",
            "No registered runtime control emits this eligibility type.",
            None,
        ),
    ):
        missing = expected.get(violation_type, set()) - predicted.get(violation_type, set())
        expected_loss = sum(
            (row.expected_loss for row in truth if violation_type in row.violation_types),
            MONEY_ZERO,
        ).quantize(CENT)
        entries.append(
            {
                "scenario": violation_type,
                "clause": clause,
                "missed_native_instances": len(missing),
                "financial_impact_labeled_rows": str(expected_loss),
                "reason": reason,
                "candidate_control": candidate,
            }
        )
    return entries


@pytest.fixture(scope="module")
def scored_clause_dataset(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    """Execute source-only baseline and invariance variants before reading labels."""

    truth_path = CLAUSE.ground_truth
    assert truth_path is not None
    database = tmp_path_factory.mktemp("clause-driven") / "clause-driven.db"
    source_files = runner.read_bundle(CLAUSE.source_paths)
    with runner.api_client(database) as client:
        baseline_id = runner.execute_bundle(
            client,
            source_files,
            name="clause-driven baseline",
            dataset_id=CLAUSE.dataset_id,
            dataset_type=CLAUSE.dataset_type,
        )
        baseline = runner.observe(
            client,
            baseline_id,
            dataset_id=CLAUSE.dataset_id,
            dataset_type=CLAUSE.dataset_type,
        )
        renamed_files, mapping = runner.rename_identifiers(source_files)
        renamed_id = runner.execute_bundle(
            client,
            renamed_files,
            name="clause-driven renamed",
            dataset_id=CLAUSE.dataset_id,
            dataset_type=CLAUSE.dataset_type,
        )
        renamed = runner.observe(
            client,
            renamed_id,
            dataset_id=CLAUSE.dataset_id,
            dataset_type=CLAUSE.dataset_type,
        )
        shuffled_files = runner.shuffle_rows(source_files, seed=20260829)
        shuffled_id = runner.execute_bundle(
            client,
            shuffled_files,
            name="clause-driven shuffled",
            dataset_id=CLAUSE.dataset_id,
            dataset_type=CLAUSE.dataset_type,
        )
        shuffled = runner.observe(
            client,
            shuffled_id,
            dataset_id=CLAUSE.dataset_id,
            dataset_type=CLAUSE.dataset_type,
        )
        relabeled_id = runner.execute_bundle(
            client,
            source_files,
            name="clause-driven metadata variant",
            dataset_id="independent_dataset_identity_v2",
            dataset_type="OTHER_LABELED_FIXTURE",
        )
        relabeled = runner.observe(
            client,
            relabeled_id,
            dataset_id="independent_dataset_identity_v2",
            dataset_type="OTHER_LABELED_FIXTURE",
        )

    # Only now open evaluation files.  This ordering is the isolation contract.
    truth = load_truth(truth_path)
    index = SourceIndex.from_paths(CLAUSE.source_paths)
    base_report = build_report(baseline, truth, index, CLAUSE.manifest)
    invariance_baseline = runner.financial_conclusions(baseline)
    invariance = {
        "id_rename": {
            "identifiers_renamed": len(mapping),
            "equivalent": runner.financial_conclusions(baseline, rename=mapping)
            == runner.financial_conclusions(renamed),
        },
        "row_order": {
            "seed": 20260829,
            "equivalent": invariance_baseline == runner.financial_conclusions(shuffled),
        },
        "dataset_metadata": {
            "equivalent": invariance_baseline == runner.financial_conclusions(relabeled),
            "metadata_changed_to": {
                "dataset_id": relabeled.dataset_id,
                "dataset_type": relabeled.dataset_type,
            },
        },
        "all_pass": all(
            item["equivalent"]
            for item in (
                {
                    "equivalent": runner.financial_conclusions(baseline, rename=mapping)
                    == runner.financial_conclusions(renamed)
                },
                {"equivalent": invariance_baseline == runner.financial_conclusions(shuffled)},
                {"equivalent": invariance_baseline == runner.financial_conclusions(relabeled)},
            )
        ),
    }
    base_report["dataset"].update(
        {
            "dataset_id": CLAUSE.dataset_id,
            "dataset_type": CLAUSE.dataset_type,
            "agreement_id": CLAUSE.manifest["agreement_id"],
            "ground_truth_read_only_after_execution": True,
        }
    )
    base_report["manifest_integrity"] = _manifest_integrity(CLAUSE)
    base_report["clause_extraction"] = _clause_extraction_result(CLAUSE)
    base_report["clause_coverage"] = _clause_coverage(CLAUSE, truth, index, baseline)
    base_report["relationship_resolution"] = _relationship_result(CLAUSE, baseline)
    base_report["settlement_level"] = _settlement_result(CLAUSE, baseline)
    base_report["control_versioning"] = _control_versioning(
        base_report["control_versioning"], CLAUSE, baseline
    )
    base_report["lineage"] = _lineage_result(base_report["lineage"], CLAUSE, baseline)
    base_report["financial_impact"] = _financial_result(
        truth, base_report["financial_impact"], baseline
    )
    base_report["blind_spots"] = _blind_spots(truth, index, baseline)
    base_report["invariance"] = invariance
    base_report["ground_truth_evaluation"] = {
        "engine_inputs_excluded": sorted(EVALUATION_FILENAMES),
        "evaluation_files_opened_after_run": True,
        "ground_truth_in_runtime_observation": baseline.summary["ground_truth_available"],
    }
    # Keep exact-canonical metrics and add a complete canonical-type view.  The
    # existing scorer remains the source for approved-control accounting.
    expected_by_type = _expected_by_type(truth, index)
    predicted_by_type = _predicted_by_type(baseline)
    requested_types = (
        "MDR_RATE",
        "GST_ON_FEE",
        "UNSUPPORTED_FEE",
        "CHARGEBACK_FEE_OVERCHARGE",
        "SETTLEMENT_SLA",
        "SETTLEMENT_BANK_ARITHMETIC",
        "MISSING_BANK_SETTLEMENT",
        "DUPLICATE_REFUND_DEDUCTION",
        "REFUND_EXCEEDS_PAYMENT",
        "FAILED_PAYMENT_IN_SETTLEMENT",
    )
    base_report["violation_types"] = [
        {
            "violation_type": violation_type,
            "native_entity": CANONICAL_NATIVE_ENTITIES.get(
                violation_type, native_entity(violation_type)
            ),
            "canonical_mapping": CANONICAL_MAPPING.get(
                violation_type,
                {
                    "canonical_type": violation_type,
                    "native_entity": native_entity(violation_type),
                    "engine_type": violation_type,
                },
            ),
            **_confusion(
                expected_by_type.get(violation_type, set()),
                predicted_by_type.get(violation_type, set()),
            ),
        }
        for violation_type in requested_types
    ]
    base_report["planted_anomaly_coverage"] = {
        "scope": (
            "All clause-driven planted instances at their native entity; explicit aliases are "
            "reported separately."
        ),
        "planted_instances": sum(len(value) for value in expected_by_type.values()),
        "detected_exact": sum(
            len(expected_by_type.get(key, set()) & predicted_by_type.get(key, set()))
            for key in expected_by_type
        ),
        "detected_under_explicit_alias": len(
            expected_by_type.get("UNSUPPORTED_FEE", set())
            & predicted_by_type.get("SETTLEMENT_ARITHMETIC", set())
        ),
        "undetected": sum(
            len(expected_by_type.get(key, set()) - predicted_by_type.get(key, set()))
            for key in expected_by_type
        ),
        "approved_governed_scope": {
            "types": [
                key
                for key in expected_by_type
                if key
                not in {
                    "UNSUPPORTED_FEE",
                    "CHARGEBACK_FEE_OVERCHARGE",
                    "FAILED_PAYMENT_IN_SETTLEMENT",
                }
            ],
            "detected_exact": sum(
                len(expected_by_type.get(key, set()) & predicted_by_type.get(key, set()))
                for key in expected_by_type
                if key
                not in {
                    "UNSUPPORTED_FEE",
                    "CHARGEBACK_FEE_OVERCHARGE",
                    "FAILED_PAYMENT_IN_SETTLEMENT",
                }
            ),
        },
    }
    base_report["report_contract"] = {
        "money_fields_are_decimal_strings": True,
        "ground_truth_evaluation_is_post_run_only": True,
        "source_bundle_is_six_files_only": True,
    }
    REPORT_PATH.parent.mkdir(exist_ok=True)
    REPORT_PATH.write_text(json.dumps(_jsonable(base_report), indent=2), encoding="utf-8")
    return {"observation": baseline, "truth": truth, "report": base_report}


def test_clause_manifest_and_engine_input_are_isolated(
    scored_clause_dataset: dict[str, Any],
) -> None:
    report = scored_clause_dataset["report"]
    integrity = report["manifest_integrity"]
    assert integrity["all_counts_match"]
    assert integrity["identity"]["dataset_id"] == "novacart_clause_driven_test_v1"
    assert integrity["identity"]["dataset_type"] == "LABELED_CLAUSE_TEST"
    assert integrity["identity"]["agreement_id"] == "MPT-NC-2026-041"
    assert integrity["evaluation_files_excluded_from_engine"]
    assert report["ground_truth_evaluation"]["ground_truth_in_runtime_observation"] is False


def test_clause_proposals_are_complete_and_provenance_aligned(
    scored_clause_dataset: dict[str, Any],
) -> None:
    extraction = scored_clause_dataset["report"]["clause_extraction"]
    assert extraction["controls_proposed"] == 9
    assert extraction["all_expected_proposals_present_and_aligned"]
    assert extraction["cover_page_provenance_rejected"]
    assert extraction["validation_warnings"] == []
    assert extraction["unnumbered_sections_not_controls"]
    assert extraction["needs_review_label"] == "Needs review"


def test_clause_dataset_metrics_and_relationships_are_reported(
    scored_clause_dataset: dict[str, Any],
) -> None:
    report = scored_clause_dataset["report"]
    payment = report["payment_primary_detection"]
    assert payment["predicted_positive"] == payment["true_positive"] + payment["false_positive"]
    assert payment["precision"] == 1.0
    assert payment["recall"] == 1.0
    assert report["relationship_resolution"]["correctly_unresolved"] == 2
    assert report["relationship_resolution"]["missed_unresolved"] == 0
    assert report["relationship_resolution"]["forced_incorrect_matches"] == 0
    assert len(report["settlement_level"]["by_type"]) == 2
    assert len(report["clause_coverage"]) == 14


def test_clause_invariance_is_a_hard_guardrail(scored_clause_dataset: dict[str, Any]) -> None:
    assert scored_clause_dataset["report"]["invariance"]["all_pass"]


def test_clause_report_is_machine_readable_and_decimal_safe(
    scored_clause_dataset: dict[str, Any],
) -> None:
    report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    for key in (
        "dataset",
        "manifest_integrity",
        "clause_extraction",
        "clause_coverage",
        "payment_primary_detection",
        "violation_types",
        "relationship_resolution",
        "settlement_level",
        "control_versioning",
        "lineage",
        "financial_impact",
        "approved_control_execution",
        "planted_anomaly_coverage",
        "blind_spots",
        "invariance",
        "performance",
    ):
        assert key in report
    assert isinstance(report["financial_impact"]["expected_verified_loss"], str)
    assert isinstance(report["financial_impact"]["predicted_attributable_loss"], str)
    assert all(isinstance(item.expected_loss, Decimal) for item in load_truth(CLAUSE.ground_truth))


def test_clause_dataset_fixture_loader_is_explicit() -> None:
    assert load_dataset_fixture("clause_driven").dataset_id == CLAUSE.dataset_id
    assert set(load_dataset_fixture("clause_driven").source_paths) == {
        "orders",
        "payments",
        "settlements",
        "bank",
        "refunds",
        "chargebacks",
    }
