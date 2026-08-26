import json
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient

from app.controls.engine import evaluate_payment
from app.main import app
from app.services.demo import DEMO_RUN_ID, store

client = TestClient(app)


def test_seeded_demo_proves_hidden_overcharge() -> None:
    loaded = client.post("/api/v1/demo/load")
    assert loaded.status_code == 200
    assert loaded.json()["counts"]["payments"] == 500

    response = client.get(f"/api/v1/runs/{DEMO_RUN_ID}/payments/PAY_82HD9/expected-vs-actual")
    assert response.status_code == 200
    body = response.json()
    assert body["gateway_net"] == body["bank_credit"] == "9793.50"
    assert body["expected_net"] == "9817.10"
    assert body["verified_leakage"] == "23.60"


def test_seeded_generator_matches_authoritative_manifest_and_ids() -> None:
    loaded = client.post("/api/v1/demo/load").json()
    manifest_path = Path(__file__).parents[2] / "data" / "demo" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert loaded["known_demo_ids"] == manifest["known_demo_ids"]
    assert loaded["counts"] == {
        key: manifest["records"][key]
        for key in ["orders", "payments", "settlements", "bank_entries", "refunds", "chargebacks"]
    }
    assert store.summary is not None
    assert store.dataset is not None
    assert store.summary.event_count == manifest["records"]["financial_events"]
    assert store.summary.relationship_count == manifest["records"]["event_edges"]
    assert store.summary.control_evaluation_count == manifest["records"]["control_evaluations"]
    scenarios = Counter(store.dataset.ground_truth.values())
    assert scenarios == {
        "PASS": manifest["ground_truth"]["pass"],
        "MDR_RATE_DEVIATION": manifest["ground_truth"]["mdr_rate_deviation"],
        "INCORRECT_GST": manifest["ground_truth"]["incorrect_gst"],
        "DUPLICATE_REFUND": manifest["ground_truth"]["duplicate_refund"],
        "SETTLEMENT_SLA": manifest["ground_truth"]["settlement_sla"],
        "UNSUPPORTED_FEE": manifest["ground_truth"]["unsupported_fee"],
        "UNRESOLVED": manifest["ground_truth"]["unresolved"],
    }
    assert any(payment.refund_id == "REF_91" for payment in store.dataset.payments)
    assert any(payment.settlement_id == "SET_1042" for payment in store.dataset.payments)
    assert any(payment.unresolved_case_id == "UNR_003" for payment in store.dataset.payments)


def test_demo_metrics_are_measured_from_separate_ground_truth() -> None:
    client.post("/api/v1/demo/load")
    response = client.get(f"/api/v1/runs/{DEMO_RUN_ID}/summary")
    body = response.json()
    assert Decimal(body["precision"]) >= Decimal("0.98")
    assert Decimal(body["recall"]) >= Decimal("0.95")
    assert body["unresolved_count"] == 5


def test_hypothesis_is_independently_rejected() -> None:
    client.post("/api/v1/demo/load")
    hypothesis = client.post("/api/v1/root-causes/RC_MDR_01/generate-hypothesis")
    assert hypothesis.json()["status"] == "UNVERIFIED"
    verification = client.post("/api/v1/root-causes/RC_MDR_01/verify-hypothesis")
    assert verification.json()["status"] == "REJECTED"


def test_mutation_suite_preserves_canonical_data_and_exposes_blind_spots() -> None:
    client.post("/api/v1/demo/load")
    before = client.get(f"/api/v1/runs/{DEMO_RUN_ID}/payments/PAY_0100/expected-vs-actual").json()
    response = client.post(f"/api/v1/runs/{DEMO_RUN_ID}/mutation-tests")
    assert response.status_code == 200
    body = response.json()
    assert body["mutation_count"] == 50
    assert body["detected_count"] == 47
    assert body["missed_count"] == 3
    assert body["mutation_detection_rate"] == "0.94"
    assert body["canonical_data_unchanged"] is True
    assert len({result["mutation_type"] for result in body["results"]}) >= 8
    assert all(
        result["blind_spot_reason"] in {"NO_APPLICABLE_CONTROL", "UNGOVERNED_LIFECYCLE_EDGE"}
        for result in body["results"]
        if not result["detected"]
    )
    after = client.get(f"/api/v1/runs/{DEMO_RUN_ID}/payments/PAY_0100/expected-vs-actual").json()
    assert before == after


def test_candidate_control_backtest_is_read_only_and_improves_coverage() -> None:
    client.post("/api/v1/demo/load")
    response = client.post("/api/v1/controls/CTRL_UNSUPPORTED_FEE_CANDIDATE/backtest")
    assert response.status_code == 200
    body = response.json()
    assert body["candidate_status"] == "DRAFT"
    assert body["before"]["detected_count"] == 47
    assert body["after"]["detected_count"] == 49
    assert body["false_positive_delta"] == 0
    assert body["detection_rate_delta"] == "0.04"
    assert body["canonical_data_unchanged"] is True


def test_hidden_overcharge_has_lineage_and_counterfactual_cash_flow() -> None:
    client.post("/api/v1/demo/load")
    lineage = client.get(f"/api/v1/runs/{DEMO_RUN_ID}/payments/PAY_82HD9/lineage").json()
    assert lineage["primary_violation_count"] == 1
    assert lineage["downstream_effect_count"] == 3
    assert lineage["nodes"][0]["lineage_type"] == "PRIMARY"
    assert all(node["root_violation_id"] == lineage["nodes"][0]["id"] for node in lineage["nodes"])

    counterfactual = client.get(
        f"/api/v1/runs/{DEMO_RUN_ID}/payments/PAY_82HD9/counterfactual"
    ).json()
    assert counterfactual["actual"]["net"] == "9793.50"
    assert counterfactual["expected"]["net"] == "9817.10"
    assert counterfactual["difference"] == "23.60"
    assert counterfactual["drivers"] == [
        {"type": "EXCESS_MDR", "amount": "20.00"},
        {"type": "EXCESS_GST", "amount": "3.60"},
    ]


def test_agreement_provenance_and_time_versioned_control_selection() -> None:
    client.post("/api/v1/demo/load")
    agreement = client.get("/api/v1/agreements/AGR_NOVACART_2026").json()
    assert agreement["status"] == "APPROVED"
    assert agreement["content_hash"]
    assert any(clause["id"] == "CLAUSE_4_2" for clause in agreement["clauses"])

    proposals = client.post("/api/v1/agreements/AGR_NOVACART_2026/extract-controls").json()
    mdr_v1 = next(item for item in proposals if item["control_id"] == "CTRL_MDR_DOMESTIC")
    assert mdr_v1["status"] == "APPROVED"
    assert mdr_v1["clause_id"] == "CLAUSE_4_2"
    assert mdr_v1["proposed_control"]["parameters"]["rate"] == "0.0155"

    august = client.get("/api/v1/controls/DOMESTIC_CARD_MDR/effective?at=2026-08-31").json()
    september = client.get("/api/v1/controls/DOMESTIC_CARD_MDR/effective?at=2026-09-01").json()
    assert august["id"] == "CTRL_MDR_DOMESTIC"
    assert september["id"] == "CTRL_MDR_DOMESTIC_V2"

    assert store.dataset is not None
    september_payment = store.dataset.payments[100].model_copy(
        update={
            "amount": Decimal("10000"),
            "actual_fee": Decimal("165.00"),
            "actual_tax": Decimal("29.70"),
            "actual_net": Decimal("9805.30"),
            "bank_credit": Decimal("9805.30"),
            "captured_at": datetime(2026, 9, 1, 9, 0, tzinfo=timezone.utc),
            "settled_at": datetime(2026, 9, 3, 9, 0, tzinfo=timezone.utc),
        }
    )
    assert evaluate_payment(september_payment).expected_fee == Decimal("165.00")


def test_control_coverage_updates_only_after_backtest_and_explicit_approval() -> None:
    client.post("/api/v1/demo/load")
    before = client.get(f"/api/v1/runs/{DEMO_RUN_ID}/control-coverage").json()
    assert before["ungoverned_edges"] == 9
    assert any(item["id"] == "COV_OTHER_DEDUCTION" for item in before["items"])

    premature = client.post("/api/v1/controls/CTRL_UNSUPPORTED_FEE_CANDIDATE/approve")
    assert premature.status_code == 409
    assert "backtest" in premature.json()["detail"].lower()

    client.post("/api/v1/controls/CTRL_UNSUPPORTED_FEE_CANDIDATE/backtest")
    approved = client.post("/api/v1/controls/CTRL_UNSUPPORTED_FEE_CANDIDATE/approve")
    assert approved.status_code == 200
    assert approved.json()["status"] == "APPROVED"
    after = client.get(f"/api/v1/runs/{DEMO_RUN_ID}/control-coverage").json()
    assert after["ungoverned_edges"] == 1
    assert Decimal(after["coverage_percentage"]) > Decimal(before["coverage_percentage"])


def test_exception_case_requires_verified_evidence_and_preserves_audit_trail() -> None:
    client.post("/api/v1/demo/load")
    invalid = client.post(
        "/api/v1/cases/CASE_PAY_82HD9/resolve",
        json={"note": "Should not skip verification"},
    )
    assert invalid.status_code == 409

    verified = client.post("/api/v1/cases/CASE_PAY_82HD9/verify", json={"note": ""}).json()
    assert verified["status"] == "VERIFIED"
    assert len(verified["evidence"]) == 4
    assert all(item["verified"] for item in verified["evidence"])

    escalated = client.post(
        "/api/v1/cases/CASE_PAY_82HD9/escalate",
        json={"note": "Escalated to the gateway finance owner with the evidence pack."},
    ).json()
    assert escalated["status"] == "ESCALATED"
    resolved = client.post(
        "/api/v1/cases/CASE_PAY_82HD9/resolve",
        json={"note": "Gateway accepted the ₹23.60 recovery adjustment."},
    ).json()
    assert resolved["status"] == "RESOLVED"
    assert [entry["to_status"] for entry in resolved["audit_trail"]] == [
        "OPEN",
        "VERIFIED",
        "ESCALATED",
        "RESOLVED",
    ]


def test_unresolved_matches_and_optional_mcp_remain_non_authoritative() -> None:
    client.post("/api/v1/demo/load")
    unresolved = client.get(f"/api/v1/runs/{DEMO_RUN_ID}/unresolved").json()
    assert len(unresolved) == 5
    assert all(item["status"] == "UNRESOLVED" for item in unresolved)
    assert all("without guessing" in item["safe_conclusion"] for item in unresolved)

    mcp = client.get("/api/v1/integrations/razorpay/mcp-evidence-capability").json()
    assert mcp["authoritative"] is False
    assert "fetch_payment" in mcp["allowed_tools"]
    assert "refund_initiation" in mcp["prohibited_tool_classes"]
