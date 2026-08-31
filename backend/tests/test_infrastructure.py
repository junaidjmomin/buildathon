from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from threading import Barrier
from time import perf_counter, sleep

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session

from app.agents import checkpoint
from app.ai.provider import build_ai_runtime
from app.core.config import Settings, get_settings
from app.domain.models import (
    CaseEvidence,
    ControlType,
    ExceptionCaseStatus,
    RootCause,
    Violation,
)
from app.ingestion.csv import parse_source_csv
from app.main import REQUIRED_SCHEMA_REVISION, app
from app.mutations.engine import execute_mutation_test
from app.persistence.database import get_engine, get_session_factory
from app.persistence.orm import (
    AgentExecutionRecord,
    ArtifactRecord,
    Base,
    EventEdgeRecord,
    EventRecord,
    MutationTestRecord,
    RootCauseRecord,
    RunRecord,
    SourceSnapshotRecord,
    ViolationRecord,
)
from app.persistence.repository import (
    AgentExecutionRepository,
    CaseConcurrencyError,
    CaseRepository,
    JobRepository,
    LeaseOwnershipError,
    RunRepository,
    SourceSnapshotRepository,
    canonical_records,
)
from app.services.demo import DemoStore
from app.services.governance import CONTROLS
from app.storage.service import ArtifactService
from app.storage.supabase import StorageNotConfiguredError, SupabaseStorage
from app.synthetic.generator import generate_dataset


def test_checkpoint_cli_selects_psycopg_compatible_windows_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configured_policy = object()
    selected: list[object] = []
    monkeypatch.setattr(checkpoint.sys, "platform", "win32")
    monkeypatch.setattr(
        checkpoint.asyncio,
        "WindowsSelectorEventLoopPolicy",
        lambda: configured_policy,
        raising=False,
    )
    monkeypatch.setattr(checkpoint.asyncio, "set_event_loop_policy", selected.append)

    checkpoint._configure_windows_event_loop()

    assert selected == [configured_policy]


def test_canonical_seeded_graph_matches_manifest() -> None:
    events, edges = canonical_records("RUN_TEST", generate_dataset())
    assert len(events) == 1179
    assert len(edges) == 1495
    assert all(isinstance(event.amount, Decimal) for event in events)
    assert all(isinstance(edge.confidence, Decimal) for edge in edges)


def test_demo_run_parent_is_flushed_before_foreign_key_children() -> None:
    engine = create_engine("sqlite://")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, _connection_record) -> None:  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    dataset = generate_dataset()
    store = DemoStore()
    summary = store._build_summary(dataset, perf_counter())

    with Session(engine) as session:
        event_count, edge_count = RunRepository(session).replace_demo_run(
            run_id="RUN_NOVACART_AUG_2026",
            dataset=dataset,
            summary=summary,
            violations=[],
            root_causes=[],
            controls=[],
        )
        session.flush()

        assert session.scalar(select(func.count()).select_from(RunRecord)) == 1
        assert session.scalar(select(func.count()).select_from(EventRecord)) == event_count
        assert session.scalar(select(func.count()).select_from(EventEdgeRecord)) == edge_count


def test_reloading_the_demo_run_replaces_everything_without_cascade() -> None:
    """A second demo load must replace the run even where ON DELETE CASCADE is
    not enforced. SQLite only honours FK cascades with PRAGMA foreign_keys=ON,
    which the production engine never sets — so replace_demo_run must delete
    the run-scoped children explicitly. Without that, the re-insert fails with
    an IntegrityError on every duplicate event id.
    """
    # Deliberately no foreign_keys pragma: mirrors the production SQLite engine.
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    dataset = generate_dataset()
    store = DemoStore()
    summary = store._build_summary(dataset, perf_counter())

    with Session(engine) as session:
        first_events, first_edges = RunRepository(session).replace_demo_run(
            run_id="RUN_NOVACART_AUG_2026",
            dataset=dataset,
            summary=summary,
            violations=[],
            root_causes=[],
            controls=[],
        )
        session.flush()
        # Reload: same run id, same content — must succeed, not IntegrityError.
        second_events, second_edges = RunRepository(session).replace_demo_run(
            run_id="RUN_NOVACART_AUG_2026",
            dataset=dataset,
            summary=summary,
            violations=[],
            root_causes=[],
            controls=[],
        )
        session.flush()
        assert (second_events, second_edges) == (first_events, first_edges)
        assert session.scalar(select(func.count()).select_from(RunRecord)) == 1
        assert session.scalar(select(func.count()).select_from(EventRecord)) == first_events
        assert session.scalar(select(func.count()).select_from(EventEdgeRecord)) == first_edges


def test_concurrent_first_demo_reads_initialize_the_seed_only_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = DemoStore()
    gate = Barrier(8)
    load_calls: list[int] = []

    def fake_load_unlocked() -> None:
        load_calls.append(1)
        sleep(0.05)
        store.dataset = generate_dataset()

    def ensure_loaded(_: int) -> None:
        gate.wait()
        store.ensure_loaded()

    monkeypatch.setattr(store, "_load_unlocked", fake_load_unlocked)
    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(ensure_loaded, range(8)))

    assert len(load_calls) == 1


def test_mutation_test_persistence_is_retry_safe() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    result = execute_mutation_test("RUN_TEST", generate_dataset().payments)
    now = datetime.now(timezone.utc)

    with Session(engine) as session:
        session.add(
            RunRecord(
                tenant_id="novacart_demo",
                id="RUN_TEST",
                name="Retry-safe mutation run",
                status="COMPLETE",
                seed=20260825,
                manifest={},
                completed_at=now,
                created_at=now,
            )
        )
        session.flush()
        repository = RunRepository(session)
        repository.save_mutation_test(result)
        session.flush()
        repository.save_mutation_test(result)
        session.flush()

        assert session.scalar(select(func.count()).select_from(MutationTestRecord)) == 1


def test_settlement_and_bank_events_store_batch_aggregates() -> None:
    dataset = generate_dataset()
    events, _ = canonical_records("RUN_TEST", dataset)
    event_index = {event.id: event for event in events}
    members = [payment for payment in dataset.payments if payment.settlement_id == "SET_000"]
    expected_settlement = sum((payment.actual_net for payment in members), Decimal("0.00"))
    expected_bank = sum(
        (payment.bank_credit for payment in members if payment.bank_credit is not None),
        Decimal("0.00"),
    )
    assert event_index["EVT_SETTLEMENT_SET_000"].amount == expected_settlement
    assert event_index["EVT_BANK_BANK_000"].amount == expected_bank


def test_composite_tenant_identity_prevents_cross_merchant_collisions() -> None:
    dataset = generate_dataset()
    first, _ = canonical_records("RUN_SHARED", dataset, tenant_id="merchant_a")
    second, _ = canonical_records("RUN_SHARED", dataset, tenant_id="merchant_b")
    identities = {(event.tenant_id, event.run_id, event.id) for event in first + second}
    assert len(identities) == 2358


def test_polars_csv_ingestion_keeps_money_in_decimal_text_semantics() -> None:
    parsed = parse_source_csv(
        b"payment_id,amount,actual_fee,actual_tax\nPAY_1,10000.00,155.00,27.90\n"
    )
    assert parsed.row_count == 1
    assert parsed.decimal_values_checked == 3


def test_csv_schema_drift_is_reported_without_rejecting_valid_source() -> None:
    parsed = parse_source_csv(
        b"payment_id,amount,currency,vendor_extension\nPAY_1,100.00,INR,alpha\n",
        filename="payments.csv",
    )
    assert parsed.source_type == "PAYMENTS"
    assert parsed.schema_drift is True
    assert parsed.drift_columns == ["vendor_extension"]
    assert any("Schema drift detected" in item for item in parsed.classification_evidence)


def test_bulk_upsert_bypasses_orm_session_insert_grouping() -> None:
    """Bulk writes must execute on the connection, not the ORM session.

    ``Session.execute`` routes Core INSERT executemany through the ORM bulk
    insert path, which splits rows with different NULL-column patterns into
    separate statements. Against a hosted PostgreSQL one round trip is emitted
    per group, which previously dominated end-to-end run latency (250
    evaluations took 84 seconds). See ``_bulk_upsert`` for the full rationale.
    """

    from unittest.mock import MagicMock

    from app.persistence.repository import _bulk_upsert

    session = MagicMock()
    session.get_bind.return_value.dialect.name = "postgresql"

    values = [{"tenant_id": "t", "id": f"row_{index}", "amount": None} for index in range(8)] + [
        {"tenant_id": "t", "id": f"row_{index}", "amount": Decimal("1.00")}
        for index in range(8, 10)
    ]

    _bulk_upsert(
        session,
        ViolationRecord,
        values,
        conflict_columns=["tenant_id", "run_id", "id"],
        update_columns=["payment_id"],
    )

    session.connection.return_value.execute.assert_called_once()
    session.execute.assert_not_called()


def test_source_upload_validates_locally_without_storage_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The developer shell may have real Supabase credentials configured.  This
    # test explicitly exercises the documented no-storage fallback instead of
    # relying on whichever .env happens to be present on the machine.
    monkeypatch.setenv("SUPABASE_URL", "")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "")
    get_settings.cache_clear()
    response = TestClient(app).post(
        "/api/v1/sources/upload",
        files={"file": ("payments.csv", b"payment_id,amount\nPAY_1,100.00\n", "text/csv")},
    )
    assert response.status_code == 200
    assert response.json()["row_count"] == 1
    assert response.json()["decimal_values_checked"] == 1
    assert response.json()["storage_status"] == "VALIDATED_ONLY"
    assert response.json()["object_path"] is None
    get_settings.cache_clear()


@pytest.mark.parametrize(
    ("filename", "source_type"),
    [
        ("orders.csv", "ORDERS"),
        ("payments.csv", "PAYMENTS"),
        ("refunds.csv", "REFUNDS"),
        ("settlements.csv", "SETTLEMENTS"),
        ("chargebacks.csv", "CHARGEBACKS"),
        ("bank.csv", "BANK_RECONCILIATION"),
    ],
)
def test_documented_csv_sources_are_classified_by_content(
    filename: str,
    source_type: str,
) -> None:
    source_path = Path(__file__).parents[2] / "docs" / filename
    parsed = parse_source_csv(source_path.read_bytes(), filename=filename)
    assert parsed.source_type == source_type
    assert parsed.classification_confidence == Decimal("0.99")
    assert parsed.classification_evidence


def test_source_batch_upload_classifies_each_file_independently() -> None:
    response = TestClient(app).post(
        "/api/v1/sources/uploads",
        files=[
            ("files", ("payments.csv", b"payment_id,amount\nPAY_1,100.00\n", "text/csv")),
            (
                "files",
                ("refunds.csv", b"refund_id,payment_id,amount\nREF_1,PAY_1,10.00\n", "text/csv"),
            ),
            ("files", ("unknown.csv", b"foo,bar\n1,2\n", "text/csv")),
        ],
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["accepted_count"] == 2
    assert payload["rejected_count"] == 1
    assert [item["source_type"] for item in payload["files"][:2]] == ["PAYMENTS", "REFUNDS"]
    assert payload["files"][2]["status"] == "REJECTED"


def test_http_errors_use_stable_machine_readable_envelope() -> None:
    response = TestClient(app).get(
        "/api/v1/runs/DOES_NOT_EXIST/summary",
        headers={"X-Request-ID": "contract-test-request"},
    )

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "NOT_FOUND",
            "message": "Run not found",
            "details": {},
            "request_id": "contract-test-request",
        }
    }


def test_ai_runtime_gracefully_degrades_without_key() -> None:
    runtime = build_ai_runtime(
        Settings(
            LLM_PROVIDER="groq",
            LLM_MODEL="openai/gpt-oss-120b",
            GROQ_API_KEY="",
        )
    )
    assert runtime.provider == "groq"
    assert runtime.model == "openai/gpt-oss-120b"
    assert runtime.configured is False
    assert runtime.provider_client is None
    assert "deterministic" in runtime.fallback_policy.lower()


def test_production_configuration_fails_closed_without_identity_and_infrastructure() -> None:
    settings = Settings(ENVIRONMENT="production")
    with pytest.raises(RuntimeError, match="unsafe or incomplete"):
        settings.validate_runtime()


@pytest.mark.parametrize("scheme", ["postgresql", "postgres"])
def test_provider_postgres_urls_select_the_installed_psycopg3_driver(scheme: str) -> None:
    settings = Settings(
        DATABASE_URL=f"{scheme}://application@pooler.example.test:6543/postgres",
        MIGRATION_DATABASE_URL=f"{scheme}://migrator@database.example.test:5432/postgres",
    )

    assert settings.sqlalchemy_database_url == (
        "postgresql+psycopg://application@pooler.example.test:6543/postgres"
    )
    assert settings.effective_migration_url == (
        "postgresql+psycopg://migrator@database.example.test:5432/postgres"
    )


def test_readiness_treats_engine_configuration_failure_as_dependency_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_to_create_engine() -> None:
        raise RuntimeError("database driver is unavailable")

    monkeypatch.setattr("app.main.get_engine", fail_to_create_engine)

    response = TestClient(app).get("/health/ready")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "DEPENDENCY_UNAVAILABLE"
    assert response.json()["error"]["message"] == "Database is unavailable"


def test_storage_requires_backend_credentials() -> None:
    storage = SupabaseStorage(Settings(SUPABASE_URL="", SUPABASE_SERVICE_ROLE_KEY=""))
    try:
        asyncio.run(
            storage.upload("runs/RUN_001/payments.csv", b"id,amount", content_type="text/csv")
        )
    except StorageNotConfiguredError:
        pass
    else:
        raise AssertionError("Storage upload should require backend credentials")


def test_storage_upload_is_private_backend_request() -> None:
    captured: dict[str, str] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers["Authorization"]
        captured["apikey"] = request.headers["apikey"]
        return httpx.Response(200, json={"Key": "runs/RUN_001/payments.csv"})

    settings = Settings(
        SUPABASE_URL="https://demo.supabase.co",
        SUPABASE_SERVICE_ROLE_KEY="backend-secret",
        SUPABASE_STORAGE_BUCKET="sl3dge-private",
    )
    storage = SupabaseStorage(settings, transport=httpx.MockTransport(handler))
    stored = asyncio.run(
        storage.upload(
            "runs/RUN_001/payments.csv",
            b"id,amount",
            content_type="text/csv",
        )
    )
    assert captured["url"].endswith("/storage/v1/object/sl3dge-private/runs/RUN_001/payments.csv")
    assert captured["authorization"] == "Bearer backend-secret"
    assert captured["apikey"] == "backend-secret"
    assert stored.bucket == "sl3dge-private"
    assert stored.byte_size == 9


def test_storage_compensation_deletes_only_the_exact_object_path() -> None:
    captured: dict[str, str] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["url"] = str(request.url)
        captured["body"] = request.content.decode()
        return httpx.Response(200, json=[])

    settings = Settings(
        SUPABASE_URL="https://demo.supabase.co",
        SUPABASE_SERVICE_ROLE_KEY="backend-secret",
        SUPABASE_STORAGE_BUCKET="sl3dge-private",
    )
    storage = SupabaseStorage(settings, transport=httpx.MockTransport(handler))
    asyncio.run(storage.delete("tenants/merchant_a/uploads/UPLOAD_1.csv"))
    assert captured["method"] == "DELETE"
    assert captured["url"].endswith("/storage/v1/object/sl3dge-private")
    assert json.loads(captured["body"]) == {"prefixes": ["tenants/merchant_a/uploads/UPLOAD_1.csv"]}
    with pytest.raises(ValueError, match="safe relative path"):
        asyncio.run(storage.delete("tenants/merchant_a/../merchant_b/source.csv"))


def test_artifact_service_stores_only_private_object_metadata_in_postgres() -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"Key": "agreements/novacart-v1.pdf"})

    settings = Settings(
        SUPABASE_URL="https://demo.supabase.co",
        SUPABASE_SERVICE_ROLE_KEY="backend-secret",
        SUPABASE_STORAGE_BUCKET="sl3dge-private",
    )
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        service = ArtifactService(
            SupabaseStorage(settings, transport=httpx.MockTransport(handler)), session
        )
        asyncio.run(
            service.store(
                artifact_id="ART_AGREEMENT_1",
                kind="MERCHANT_AGREEMENT",
                object_path="agreements/novacart-v1.pdf",
                content=b"synthetic-pdf",
                content_type="application/pdf",
                tenant_id="novacart_demo",
            )
        )
        session.commit()
        record = session.scalar(
            select(ArtifactRecord).where(ArtifactRecord.id == "ART_AGREEMENT_1")
        )
        assert record is not None
        assert record.object_path == "agreements/novacart-v1.pdf"
        assert record.bucket == "sl3dge-private"
        assert record.byte_size == len(b"synthetic-pdf")


def test_capabilities_never_expose_privileged_credentials() -> None:
    client = TestClient(app)
    infrastructure = client.get("/api/v1/capabilities/infrastructure")
    ai = client.get("/api/v1/capabilities/ai")
    assert infrastructure.status_code == 200
    assert ai.status_code == 200
    payload = infrastructure.text + ai.text
    assert "service_role" not in payload
    assert "GROQ_API_KEY" not in payload


def test_source_snapshots_are_content_addressed_and_idempotent() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    captured_at = datetime(2026, 8, 26, tzinfo=timezone.utc)
    with Session(engine) as session:
        repository = SourceSnapshotRepository(session)
        first = repository.capture(
            tenant_id="merchant_a",
            source_system="RAZORPAY",
            resource_type="payment",
            external_id="pay_123",
            payload={"id": "pay_123", "amount": 10000},
            provenance={"endpoint": "/payments", "read_only": True},
            captured_at=captured_at,
        )
        second = repository.capture(
            tenant_id="merchant_a",
            source_system="RAZORPAY",
            resource_type="payment",
            external_id="pay_123",
            payload={"amount": 10000, "id": "pay_123"},
            provenance={"endpoint": "/payments", "read_only": True},
            captured_at=captured_at,
        )
        assert first.id == second.id
        assert session.query(SourceSnapshotRecord).count() == 1


def test_background_jobs_are_idempotent_leased_and_bounded() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        repository = JobRepository(session)
        first, created = repository.enqueue(
            tenant_id="merchant_a",
            job_type="RAZORPAY_SYNC",
            idempotency_key="2026-08",
            payload={"year": 2026, "month": 8},
            max_attempts=2,
        )
        duplicate, duplicate_created = repository.enqueue(
            tenant_id="merchant_a",
            job_type="RAZORPAY_SYNC",
            idempotency_key="2026-08",
            payload={"year": 2026, "month": 8},
            max_attempts=2,
        )
        assert created is True
        assert duplicate_created is False
        assert first.id == duplicate.id
        claimed = repository.claim_next(tenant_id="merchant_a", worker_id="worker-1")
        assert claimed is not None
        assert claimed.status == "RUNNING"
        assert claimed.attempt_count == 1
        repository.fail(
            claimed,
            error_code="UPSTREAM_TIMEOUT",
            safe_message="Upstream timed out",
            worker_id="worker-1",
            retry_delay_seconds=0,
        )
        assert claimed.status == "RETRYABLE"
        claimed_again = repository.claim_next(tenant_id="merchant_a", worker_id="worker-2")
        assert claimed_again is not None
        assert claimed_again.attempt_count == 2
        repository.succeed(
            claimed_again,
            {"sync_id": "SYNC_1"},
            worker_id="worker-2",
        )
        assert claimed_again.status == "SUCCEEDED"
        assert claimed_again.result == {"sync_id": "SYNC_1"}
        assert (
            repository.latest(tenant_id="merchant_a", job_type="RAZORPAY_SYNC", status="SUCCEEDED")
            is claimed_again
        )


def test_agent_execution_results_are_durable_and_tenant_scoped() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    now = datetime(2026, 8, 26, tzinfo=timezone.utc)
    with Session(engine) as session:
        repository = AgentExecutionRepository(session)
        saved = repository.save(
            tenant_id="merchant_a",
            execution_id="INV_001",
            workflow="ROOT_CAUSE_INVESTIGATION",
            resource_type="root_cause",
            resource_id="RC_MDR_01",
            status="PROVEN",
            result={"execution_id": "INV_001", "trace": []},
            started_at=now,
            completed_at=now,
        )
        session.flush()
        assert saved.id == "INV_001"
        assert repository.get(tenant_id="merchant_a", execution_id="INV_001") is saved
        assert repository.get(tenant_id="merchant_b", execution_id="INV_001") is None
        assert session.query(AgentExecutionRecord).count() == 1


def test_tenant_control_registry_round_trips_decimal_strings() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        from app.persistence.repository import RunRepository

        repository = RunRepository(session)
        repository.save_controls(CONTROLS, tenant_id="merchant_a")
        session.flush()
        loaded = repository.list_controls(tenant_id="merchant_a", approved_only=True)

    by_id = {control.id: control for control in loaded}
    assert by_id["CTRL_MDR_DOMESTIC"].parameters["rate"] == "0.0155"
    assert by_id["CTRL_MDR_DOMESTIC"].parameters["tolerance"] == "0.01"
    assert by_id["CTRL_GST_FEE"].parameters["rate"] == "0.18"
    assert "CTRL_UNSUPPORTED_FEE_CANDIDATE" not in by_id


def test_expired_job_leases_are_reclaimed_without_stale_worker_overwrites() -> None:
    from datetime import timedelta

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        repository = JobRepository(session)
        record, _ = repository.enqueue(
            tenant_id="merchant_a",
            job_type="RAZORPAY_SYNC",
            idempotency_key="reclaimable-job",
            payload={"year": 2026, "month": 8},
            max_attempts=3,
        )
        first = repository.claim_next(
            tenant_id="merchant_a", worker_id="worker-old", lease_seconds=60
        )
        assert first is record
        record.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        session.flush()
        second = repository.claim_next(
            tenant_id="merchant_a", worker_id="worker-new", lease_seconds=60
        )
        assert second is record
        assert second.attempt_count == 2
        assert (
            repository.renew_lease(
                tenant_id="merchant_a",
                job_id=record.id,
                worker_id="worker-old",
                lease_seconds=60,
            )
            is False
        )
        with pytest.raises(LeaseOwnershipError):
            repository.succeed(record, {}, worker_id="worker-old")
        repository.succeed(record, {"sync_id": "SYNC_2"}, worker_id="worker-new")
        assert record.status == "SUCCEEDED"


def test_expired_job_at_attempt_limit_is_failed_not_reclaimed() -> None:
    from datetime import timedelta

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        repository = JobRepository(session)
        record, _ = repository.enqueue(
            tenant_id="merchant_a",
            job_type="RAZORPAY_SYNC",
            idempotency_key="exhausted-job",
            payload={"year": 2026, "month": 8},
            max_attempts=1,
        )
        assert repository.claim_next(tenant_id="merchant_a", worker_id="worker-old")
        record.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        session.flush()
        assert repository.claim_next(tenant_id="merchant_a", worker_id="worker-new") is None
        assert record.status == "FAILED"
        assert record.error and record.error["code"] == "LEASE_EXHAUSTED"


def test_durable_case_transitions_use_optimistic_concurrency() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    now = datetime(2026, 8, 27, tzinfo=timezone.utc)
    root = RootCause(
        id="RC_LIVE_1",
        title="Systemic MDR deviation",
        category="MDR rate deviation",
        affected_count=1,
        verified_impact="23.60",
        expected_value="0.0155",
        observed_value="0.0175",
        first_seen=now,
        last_seen=now,
        verification_status="PROVEN",
        primary_violation_count=1,
    )
    violation = Violation(
        id="V_LIVE_1",
        payment_id="pay_live_1",
        category="MDR rate deviation",
        control_type=ControlType.MDR_RATE,
        expected="155.00",
        actual="175.00",
        difference="20.00",
        financial_impact="23.60",
        root_cause_id=root.id,
        occurred_at=now,
    )
    with Session(engine) as session:
        session.add(
            RunRecord(
                tenant_id="merchant_a",
                id="RUN_LIVE_1",
                name="Live run",
                status="COMPLETE",
                seed=None,
                manifest={},
                completed_at=now,
                created_at=now,
            )
        )
        session.add(
            RootCauseRecord(
                tenant_id="merchant_a",
                run_id="RUN_LIVE_1",
                id=root.id,
                title=root.title,
                category=root.category,
                affected_count=1,
                verified_impact=root.verified_impact,
                verification_status="PROVEN",
                evidence={"expected": "0.0155", "observed": "0.0175"},
            )
        )
        session.add(
            ViolationRecord(
                tenant_id="merchant_a",
                run_id="RUN_LIVE_1",
                id=violation.id,
                payment_id=violation.payment_id,
                category=violation.category,
                control_type=violation.control_type.value,
                difference=violation.difference,
                financial_impact=violation.financial_impact,
                confidence=violation.confidence,
                root_cause_id=root.id,
                occurred_at=now,
                evidence={"expected": violation.expected, "actual": violation.actual},
            )
        )
        session.flush()
        repository = CaseRepository(session)
        created = repository.create_from_investigation(
            tenant_id="merchant_a",
            case_id="CASE_LIVE_1",
            root_cause=root,
            violations=[violation],
            evidence=[
                CaseEvidence(
                    id="EVIDENCE_1",
                    kind="DETERMINISTIC_CALCULATION",
                    title="MDR calculation",
                    summary="The effective control was exceeded.",
                    source_id="EVAL_1",
                    verified=True,
                )
            ],
            actor_id="analyst-a",
        )
        assert created.version == 1
        verified = repository.transition(
            tenant_id="merchant_a",
            case_id=created.id,
            target=ExceptionCaseStatus.VERIFIED,
            actor_id="reviewer-b",
            note="",
            expected_version=1,
        )
        assert verified.version == 2
        with pytest.raises(CaseConcurrencyError):
            repository.transition(
                tenant_id="merchant_a",
                case_id=created.id,
                target=ExceptionCaseStatus.ESCALATED,
                actor_id="reviewer-c",
                note="Escalating with evidence.",
                expected_version=1,
            )


def test_migrations_are_immutable_and_upgrade_from_empty_database(tmp_path: Path) -> None:
    backend_dir = Path(__file__).parents[1]
    initial = backend_dir / "alembic" / "versions" / "0001_initial.py"
    migration_source = initial.read_text(encoding="utf-8")
    assert "app.persistence.orm" not in migration_source
    assert "create_all" not in migration_source
    database_path = tmp_path / "migration.db"
    environment = os.environ.copy()
    environment["MIGRATION_DATABASE_URL"] = f"sqlite:///{database_path.as_posix()}"
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=backend_dir,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    table_names = set(Base.metadata.tables)
    from sqlalchemy import inspect

    assert table_names <= set(inspect(engine).get_table_names())
    subprocess.run(
        [sys.executable, "-m", "alembic", "downgrade", "base"],
        cwd=backend_dir,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )


def test_readiness_schema_pin_matches_alembic_head() -> None:
    """The readiness check pins one revision; it must always equal the head.

    A migration merged without bumping REQUIRED_SCHEMA_REVISION leaves every
    deployed container permanently not-ready (503) even though migrations
    succeeded — exactly the CI failure this guards against.
    """
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    backend_dir = Path(__file__).parents[1]
    script = ScriptDirectory.from_config(Config(str(backend_dir / "alembic.ini")))
    head = script.get_current_head()
    assert REQUIRED_SCHEMA_REVISION == head, (
        "app.main.REQUIRED_SCHEMA_REVISION is stale: alembic head is "
        f"{head!r} but readiness requires {REQUIRED_SCHEMA_REVISION!r}. "
        "Update the pin so /health/ready accepts the migrated schema."
    )


def test_sync_job_api_requires_and_honors_idempotency(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_path = tmp_path / "jobs.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{database_path.as_posix()}")
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()
    engine = get_engine()
    assert engine is not None
    Base.metadata.create_all(engine)
    try:
        api_client = TestClient(app)
        missing_key = api_client.post(
            "/api/v1/integrations/razorpay/sync-jobs",
            json={"year": 2026, "month": 8},
        )
        assert missing_key.status_code == 422
        headers = {"Idempotency-Key": "novacart-2026-08-sync"}
        first = api_client.post(
            "/api/v1/integrations/razorpay/sync-jobs",
            json={"year": 2026, "month": 8},
            headers=headers,
        )
        replay = api_client.post(
            "/api/v1/integrations/razorpay/sync-jobs",
            json={"year": 2026, "month": 8},
            headers=headers,
        )
        assert first.status_code == replay.status_code == 202
        assert first.json()["created"] is True
        assert replay.json()["created"] is False
        assert first.json()["job"]["id"] == replay.json()["job"]["id"]
        fetched = api_client.get(f"/api/v1/jobs/{first.json()['job']['id']}")
        assert fetched.status_code == 200
        assert fetched.json()["status"] == "QUEUED"
    finally:
        get_session_factory.cache_clear()
        get_engine.cache_clear()
        get_settings.cache_clear()
