from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.ai.provider import build_ai_runtime
from app.core.config import Settings, get_settings
from app.ingestion.csv import parse_source_csv
from app.main import app
from app.persistence.database import get_engine, get_session_factory
from app.persistence.orm import AgentExecutionRecord, ArtifactRecord, Base, SourceSnapshotRecord
from app.persistence.repository import (
    AgentExecutionRepository,
    JobRepository,
    SourceSnapshotRepository,
    canonical_records,
)
from app.storage.service import ArtifactService
from app.storage.supabase import StorageNotConfiguredError, SupabaseStorage
from app.synthetic.generator import generate_dataset


def test_canonical_seeded_graph_matches_manifest() -> None:
    events, edges = canonical_records("RUN_TEST", generate_dataset())
    assert len(events) == 1179
    assert len(edges) == 1495
    assert all(isinstance(event.amount, Decimal) for event in events)
    assert all(isinstance(edge.confidence, Decimal) for edge in edges)


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


def test_source_upload_validates_locally_without_storage_credentials() -> None:
    response = TestClient(app).post(
        "/api/v1/sources/upload",
        files={"file": ("payments.csv", b"payment_id,amount\nPAY_1,100.00\n", "text/csv")},
    )
    assert response.status_code == 200
    assert response.json()["row_count"] == 1
    assert response.json()["decimal_values_checked"] == 1
    assert response.json()["storage_status"] == "VALIDATED_ONLY"
    assert response.json()["object_path"] is None


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
            retry_delay_seconds=0,
        )
        assert claimed.status == "RETRYABLE"
        claimed_again = repository.claim_next(tenant_id="merchant_a", worker_id="worker-2")
        assert claimed_again is not None
        assert claimed_again.attempt_count == 2
        repository.succeed(claimed_again, {"sync_id": "SYNC_1"})
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
