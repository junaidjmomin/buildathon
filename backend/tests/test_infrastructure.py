from __future__ import annotations

import asyncio
from decimal import Decimal

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.ai.provider import build_ai_runtime
from app.core.config import Settings
from app.ingestion.csv import parse_source_csv
from app.main import app
from app.persistence.orm import ArtifactRecord, Base
from app.persistence.repository import canonical_records
from app.storage.service import ArtifactService
from app.storage.supabase import StorageNotConfiguredError, SupabaseStorage
from app.synthetic.generator import generate_dataset


def test_canonical_seeded_graph_matches_manifest() -> None:
    events, edges = canonical_records("RUN_TEST", generate_dataset())
    assert len(events) == 1179
    assert len(edges) == 1495
    assert all(isinstance(event.amount, Decimal) for event in events)
    assert all(isinstance(edge.confidence, Decimal) for edge in edges)


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


def test_storage_requires_backend_credentials() -> None:
    storage = SupabaseStorage(Settings(SUPABASE_URL="", SUPABASE_SERVICE_ROLE_KEY=""))
    try:
        asyncio.run(
            storage.upload(
                "runs/RUN_001/payments.csv", b"id,amount", content_type="text/csv"
            )
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
    assert captured["url"].endswith(
        "/storage/v1/object/sl3dge-private/runs/RUN_001/payments.csv"
    )
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
