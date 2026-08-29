"""End-to-end API coverage for the six-file CSV upload → control run flow.

The tests drive the real FastAPI app with a scratch sqlite database and an
in-memory stand-in for Supabase Storage, covering classification, the
deterministic run pipeline, every persisted run view, the artifact hash
tamper check and the new live payment drill-down endpoints.

The bundle under test is the documented six-file sample in ``docs/`` — the
canonical published example. Labeled datasets live under ``data/`` and are
scored by ``tests/test_stress_evaluation.py``.
"""
# ruff: noqa: E402

import os
from decimal import Decimal
from hashlib import sha256
from importlib import import_module
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import get_settings
from app.main import app
from app.persistence.database import get_engine, get_session_factory, session_scope
from app.persistence.orm import AuditLogRecord, Base
from app.storage.supabase import StoredObject

api_router = import_module("app.api.router")

DOCS_ROOT = Path(__file__).parents[2] / "docs"
FILE_STEMS = ("orders", "payments", "refunds", "settlements", "chargebacks", "bank")


def _d(value) -> Decimal:
    """Parse a JSON money value regardless of string/float serialization."""

    return Decimal(str(value))


class _Storage:
    """Deterministic storage double that returns true content hashes."""

    configured = True

    def __init__(self, settings=None) -> None:
        pass

    async def upload(
        self,
        object_path: str,
        content: bytes,
        *,
        content_type: str,
        overwrite: bool = False,
    ) -> StoredObject:
        return StoredObject(
            bucket="private",
            object_path=object_path,
            content_type=content_type,
            byte_size=len(content),
            sha256=sha256(content).hexdigest(),
        )

    async def delete(self, _object_path: str) -> None:
        raise AssertionError("A successful source upload must never be deleted")


def _docs_files() -> list[tuple[str, bytes, str]]:
    return [
        (f"{stem}.csv", (DOCS_ROOT / f"{stem}.csv").read_bytes(), "text/csv") for stem in FILE_STEMS
    ]


def _setup(tmp_path, monkeypatch) -> TestClient:
    database_path = tmp_path / "source_run_api.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{database_path.as_posix()}")
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()
    engine = get_engine()
    assert engine is not None
    Base.metadata.create_all(engine)
    monkeypatch.setattr(api_router, "SupabaseStorage", _Storage)
    return TestClient(app)


def _teardown() -> None:
    get_session_factory.cache_clear()
    get_engine.cache_clear()
    get_settings.cache_clear()
    os.environ.pop("DATABASE_URL", None)


def _upload_bundle(client: TestClient, files: list[tuple[str, bytes, str]]):
    return client.post(
        "/api/v1/sources/uploads",
        files=[("files", item) for item in files],
    )


def _create_run(client: TestClient, files: list[tuple[str, bytes, str]], upload_ids: list[str]):
    # Plain form fields ride alongside file parts as (None, value, None)
    # entries; httpx 0.27 cannot mix list-form `data` with `files`.
    parts = [("name", (None, "E2E six-file run", None))]
    parts.extend(("upload_ids", (None, upload_id, None)) for upload_id in upload_ids)
    parts.extend(
        ("files", (filename, content, content_type)) for filename, content, content_type in files
    )
    return client.post("/api/v1/runs/from-uploads", files=parts)


def test_runs_contract_serializes_source_type(tmp_path, monkeypatch) -> None:
    client = _setup(tmp_path, monkeypatch)
    try:
        files = _docs_files()
        uploaded = _upload_bundle(client, files)
        upload_ids = [item["upload_id"] for item in uploaded.json()["files"]]
        created = _create_run(client, files, upload_ids)
        assert created.status_code == 201, created.text
        response = client.get("/api/v1/runs")
        assert response.status_code == 200, response.text
        items = response.json()
        assert items and items[0]["source_type"] == "CSV_UPLOAD"
        assert "source" not in items[0]
    finally:
        _teardown()


def test_six_file_bundle_classifies_uploads_and_executes(tmp_path, monkeypatch) -> None:
    client = _setup(tmp_path, monkeypatch)
    try:
        files = _docs_files()
        uploaded = _upload_bundle(client, files)
        assert uploaded.status_code == 200
        payload = uploaded.json()
        assert payload["accepted_count"] == 6
        assert payload["rejected_count"] == 0
        by_type = {item["filename"]: item for item in payload["files"]}
        assert {item["source_type"] for item in payload["files"]} == {
            "ORDERS",
            "PAYMENTS",
            "REFUNDS",
            "SETTLEMENTS",
            "CHARGEBACKS",
            "BANK_RECONCILIATION",
        }
        assert all(item["status"] == "ACCEPTED" for item in payload["files"])
        assert all(item["row_errors"] == [] for item in payload["files"])
        assert by_type["payments.csv"]["row_count"] == 60
        upload_ids = [item["upload_id"] for item in payload["files"]]
        assert all(upload_ids)

        run = _create_run(client, files, upload_ids)
        assert run.status_code == 201, run.text
        body = run.json()
        assert body["run_id"].startswith("RUN_CSV_")
        assert body["status"] == "COMPLETE"
        assert body["files_ingested"] == 6
        assert body["events_created"] == 145
        assert body["edges_created"] == 132
        # No settlement in the documented bundle is genuinely ambiguous: the one
        # settlement without a bank credit has no amount-compatible candidate,
        # which is an absence finding rather than an unresolved relationship.
        assert body["unresolved_matches"] == 0
        assert body["control_evaluations_created"] > 0
        assert body["violations_created"] > 0
        assert body["persistence_status"] == "POSTGRES"
        stage_names = [stage["stage"] for stage in body["stages"]]
        assert stage_names == [
            "VALIDATE_INPUTS",
            "CANONICALIZE",
            "PERSIST_SNAPSHOTS",
            "PERSIST_CANONICAL",
            "EVALUATE_CONTROLS",
            "PERSIST_OUTCOMES",
            "FINALIZE",
        ]
        assert all(stage["status"] == "COMPLETE" for stage in body["stages"])
        assert all(stage["finished_at"] is not None for stage in body["stages"])

        run_id = body["run_id"]
        stages = client.get(f"/api/v1/runs/{run_id}/stages")
        assert stages.status_code == 200
        persisted_stages = stages.json()
        assert [stage["stage"] for stage in persisted_stages] == stage_names
        assert all(stage["duration_ms"] is not None for stage in persisted_stages)
        finalize = persisted_stages[-1]
        assert (
            finalize["detail"]["total_processing_ms"] >= finalize["detail"]["engine_processing_ms"]
        )
        metrics = client.get(f"/api/v1/runs/{run_id}/operational-metrics")
        assert metrics.status_code == 200
        metrics_body = metrics.json()
        assert metrics_body["stage_count"] == 7
        assert metrics_body["completed_stage_count"] == 7
        assert metrics_body["failed_stage_count"] == 0
        assert metrics_body["events_created"] == 145
        missing = client.get("/api/v1/runs/RUN_CSV_UNKNOWN/stages")
        assert missing.status_code == 404
        summary = client.get(f"/api/v1/runs/{run_id}/summary")
        assert summary.status_code == 200
        summary_body = summary.json()
        assert summary_body["id"] == run_id
        assert summary_body["transaction_count"] == 60
        assert summary_body["event_count"] == 145
        assert summary_body["relationship_count"] == 132
        assert _d(summary_body["verified_leakage"]) > 0
        breakdown = summary_body["breakdown"]
        assert sum(breakdown.values()) == summary_body["control_evaluation_count"]
        # Unresolved control evaluations and unresolved event relationships
        # are separate quantities; the invariant across the breakdown holds.
        assert (
            breakdown["passed"]
            + breakdown["violation"]
            + breakdown["warning"]
            + breakdown["unresolved"]
            == summary_body["control_evaluation_count"]
        )
        assert summary_body["unresolved_control_count"] == breakdown["unresolved"]
        assert summary_body["unresolved_relationship_count"] == 0
        assert summary_body["metrics_note"] == (
            "Precision and recall require labeled ground truth and are not scored for this run."
        )

        coverage = client.get(f"/api/v1/runs/{run_id}/control-coverage")
        assert coverage.status_code == 200, coverage.text
        coverage_body = coverage.json()
        assert coverage_body["run_id"] == run_id
        assert coverage_body["total_material_edges"] > 0
        assert any(item["relationship"] == "PAYMENT → FEE" for item in coverage_body["items"])

        violations = client.get(f"/api/v1/runs/{run_id}/violations")
        assert violations.status_code == 200
        violation_items = violations.json()
        assert any(
            item["payment_id"] == "PAY_82HD9" and item["category"] == "MDR rate deviation"
            for item in violation_items
        )

        roots = client.get(f"/api/v1/runs/{run_id}/root-causes")
        assert roots.status_code == 200
        root_items = roots.json()
        assert len(root_items) > 0
        assert all(
            item["primary_violation_count"] + item["downstream_effect_count"]
            >= item["affected_count"]
            for item in root_items
        )
        assert all(isinstance(item["total_attributable_impact"], str) for item in root_items)
        assert all(item["verification_evidence"]["violation_ids"] for item in root_items)
        assert all(
            item["verification_evidence"]["grouping_basis"] == "PRIMARY_VIOLATION_CANONICAL_TYPE"
            for item in root_items
        )
        assert all(item["primary_violation_count"] >= 1 for item in root_items)
        assert all(
            "unaffected_evaluations" in item["verification_evidence"]["unaffected_comparison"]
            for item in root_items
        )

        cases = client.get(f"/api/v1/runs/{run_id}/cases")
        assert cases.status_code == 200
        assert len(cases.json()) > 0

        # Settlements whose bank credit is absent with no amount-compatible
        # candidate anywhere are deterministic missing-bank findings, not
        # unresolved matches: they surface as MISSING_BANK_SETTLEMENT
        # violations, while only genuinely ambiguous pairings stay in the
        # unresolved endpoint.
        unresolved = client.get(f"/api/v1/runs/{run_id}/unresolved")
        assert unresolved.status_code == 200
        missing_bank = [
            item
            for item in violation_items
            if item.get("violation_type") == "MISSING_BANK_SETTLEMENT"
        ]
        assert missing_bank
        assert all(item["target_type"] == "SETTLEMENT" for item in missing_bank)
        unresolved_settlement_ids = {item["payment_id"] for item in unresolved.json()}
        assert unresolved_settlement_ids.isdisjoint({item["payment_id"] for item in missing_bank})

        mutation = client.post(f"/api/v1/runs/{run_id}/mutation-tests")
        assert mutation.status_code == 200, mutation.text
        mutation_body = mutation.json()
        assert mutation_body["source_run_id"] == run_id
        assert mutation_body["mutation_count"] == 50
        assert mutation_body["canonical_data_unchanged"] is True

        with session_scope(tenant_id="novacart_demo") as session:
            actions = set(
                session.scalars(
                    select(AuditLogRecord.action).where(AuditLogRecord.tenant_id == "novacart_demo")
                )
            )
        assert "SOURCE_UPLOAD" in actions
        assert "CSV_CONTROL_RUN_COMPLETED" in actions
    finally:
        _teardown()


def test_tampered_file_is_rejected_by_artifact_hash(tmp_path, monkeypatch) -> None:
    client = _setup(tmp_path, monkeypatch)
    try:
        files = _docs_files()
        uploaded = _upload_bundle(client, files)
        assert uploaded.status_code == 200
        upload_ids = [item["upload_id"] for item in uploaded.json()["files"]]

        tampered = list(files)
        original = files[1][1]
        tampered[1] = ("payments.csv", original.replace(b"175.00", b"999.00"), "text/csv")
        rejected = _create_run(client, tampered, upload_ids)
        assert rejected.status_code == 409
        assert "File changed after classification" in rejected.text

        clean = _create_run(client, files, upload_ids)
        assert clean.status_code == 201, clean.text
    finally:
        _teardown()


def test_payment_drill_downs_serve_live_runs(tmp_path, monkeypatch) -> None:
    client = _setup(tmp_path, monkeypatch)
    try:
        files = _docs_files()
        uploaded = _upload_bundle(client, files)
        upload_ids = [item["upload_id"] for item in uploaded.json()["files"]]
        run = _create_run(client, files, upload_ids)
        assert run.status_code == 201, run.text
        run_id = run.json()["run_id"]

        base = f"/api/v1/runs/{run_id}/payments/PAY_82HD9"
        expected = client.get(f"{base}/expected-vs-actual")
        assert expected.status_code == 200, expected.text
        body = expected.json()
        assert body["payment_id"] == "PAY_82HD9"
        assert _d(body["amount"]) == Decimal("10000.00")
        assert body["applied_control_id"] == "CTRL_MDR_DOMESTIC"
        assert _d(body["verified_leakage"]) == Decimal("23.60")
        assert _d(body["gateway_net"]) == Decimal("9793.50")
        assert _d(body["expected_net"]) == Decimal("9817.10")
        rows = {row["label"]: row for row in body["rows"]}
        assert rows["MDR"]["status"] == "VIOLATION"
        assert _d(rows["MDR"]["expected"]) == Decimal("155.00")
        assert _d(rows["MDR"]["actual"]) == Decimal("175.00")
        assert rows["GST"]["status"] == "VIOLATION"
        assert body["status"] == "VIOLATION"
        assert any(item["control"] == "CTRL_MDR_DOMESTIC" for item in body["evidence"])

        graph = client.get(f"{base}/graph")
        assert graph.status_code == 200, graph.text
        graph_body = graph.json()
        node_ids = [node["id"] for node in graph_body["nodes"]]
        assert "PAY_82HD9" in node_ids
        assert "FEE_PAY_82HD9" in node_ids
        assert "TAX_PAY_82HD9" in node_ids
        relationships = {edge["relationship"] for edge in graph_body["edges"]}
        assert "CHARGED_FEE" in relationships
        assert "CHARGED_TAX" in relationships
        assert "PAID_BY" in relationships

        lineage = client.get(f"{base}/lineage")
        assert lineage.status_code == 200, lineage.text
        lineage_body = lineage.json()
        assert lineage_body["primary_violation_count"] >= 1
        assert any(
            node["lineage_type"] == "PRIMARY" and node["category"] == "MDR rate deviation"
            for node in lineage_body["nodes"]
        )
        assert all(node["root_violation_id"] for node in lineage_body["nodes"])

        counterfactual = client.get(f"{base}/counterfactual")
        assert counterfactual.status_code == 200, counterfactual.text
        cf = counterfactual.json()
        assert _d(cf["actual"]["mdr"]) == Decimal("175.00")
        assert _d(cf["expected"]["mdr"]) == Decimal("155.00")
        drivers = {item["type"]: _d(item["amount"]) for item in cf["drivers"]}
        assert drivers["EXCESS_MDR"] == Decimal("20.00")
        assert drivers["EXCESS_GST"] == Decimal("3.60")
        assert _d(cf["difference"]) == Decimal("23.60")

        missing = client.get(f"/api/v1/runs/{run_id}/payments/PAY_NOPE/expected-vs-actual")
        assert missing.status_code == 404
        unknown_run = client.get(
            "/api/v1/runs/RUN_CSV_UNKNOWN/payments/PAY_82HD9/expected-vs-actual"
        )
        assert unknown_run.status_code == 404
    finally:
        _teardown()


def test_row_level_errors_are_reported_without_blocking_valid_rows(tmp_path, monkeypatch) -> None:
    client = _setup(tmp_path, monkeypatch)
    try:
        lines = (DOCS_ROOT / "payments.csv").read_text().splitlines()
        # CSV row 3 gets an unparsable fee; CSV row 4 loses its payment_id.
        payment_fields = lines[2].split(",")
        payment_fields[8] = "not-a-decimal"
        lines[2] = ",".join(payment_fields)
        fields = lines[3].split(",")
        lines[3] = ",".join(["", *fields[1:]])
        bad_payments = ("\n".join(lines) + "\n").encode()

        uploaded = client.post(
            "/api/v1/sources/upload",
            files={"file": ("payments.csv", bad_payments, "text/csv")},
        )
        assert uploaded.status_code == 200, uploaded.text
        payload = uploaded.json()
        assert payload["status"] == "ACCEPTED"
        assert payload["source_type"] == "PAYMENTS"
        errors = {(item["row_number"], item["column"]) for item in payload["row_errors"]}
        assert (3, "fee") in errors
        assert (4, "payment_id") in errors
        assert payload["row_error_count"] >= 2

        settlements = (
            "settlements.csv",
            (DOCS_ROOT / "settlements.csv").read_bytes(),
            "text/csv",
        )
        bundle = _upload_bundle(client, [("payments.csv", bad_payments, "text/csv"), settlements])
        assert bundle.status_code == 200
        upload_ids = [item["upload_id"] for item in bundle.json()["files"]]
        run = _create_run(
            client,
            [("payments.csv", bad_payments, "text/csv"), settlements],
            upload_ids,
        )
        assert run.status_code == 201, run.text
        body = run.json()
        assert body["status"] == "COMPLETE"
        assert body["events_created"] > 0
        validation_stage = next(
            stage for stage in body["stages"] if stage["stage"] == "VALIDATE_INPUTS"
        )
        assert validation_stage["detail"]["invalid_rows_dropped"] == 2
    finally:
        _teardown()
