import base64
import os
from datetime import date, datetime, timezone
from decimal import Decimal
from importlib import import_module
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.domain.models import (
    Agreement,
    AgreementClause,
    AgreementClauseCreate,
    Control,
    ControlProposal,
    ControlType,
)
from app.ingestion.pdf import AgreementPdfError, extract_agreement_pages
from app.main import app
from app.persistence.database import get_engine, get_session_factory
from app.persistence.orm import ArtifactRecord, Base
from app.persistence.repository import AgreementRepository, ProposalConcurrencyError
from app.storage.supabase import StoredObject

api_router = import_module("app.api.router")

AGREEMENT_PDF_BASE64 = (
    "JVBERi0xLjMKJZOMi54gUmVwb3J0TGFiIEdlbmVyYXRlZCBQREYgZG9jdW1lbnQgaHR0cDov"
    "L3d3dy5yZXBvcnRsYWIuY29tCjEgMCBvYmoKPDwKL0YxIDIgMCBSCj4+CmVuZG9iagoyIDAg"
    "b2JqCjw8Ci9CYXNlRm9udCAvSGVsdmV0aWNhIC9FbmNvZGluZyAvV2luQW5zaUVuY29kaW5n"
    "IC9OYW1lIC9GMSAvU3VidHlwZSAvVHlwZTEgL1R5cGUgL0ZvbnQKPj4KZW5kb2JqCjMgMCBv"
    "YmoKPDwKL0NvbnRlbnRzIDcgMCBSIC9NZWRpYUJveCBbIDAgMCA1OTUuMjc1NiA4NDEuODg5"
    "OCBdIC9QYXJlbnQgNiAwIFIgL1Jlc291cmNlcyA8PAovRm9udCAxIDAgUiAvUHJvY1NldCBb"
    "IC9QREYgL1RleHQgL0ltYWdlQiAvSW1hZ2VDIC9JbWFnZUkgXQo+PiAvUm90YXRlIDAgL1Ry"
    "YW5zIDw8Cgo+PiAKICAvVHlwZSAvUGFnZQo+PgplbmRvYmoKNCAwIG9iago8PAovUGFnZU1v"
    "ZGUgL1VzZU5vbmUgL1BhZ2VzIDYgMCBSIC9UeXBlIC9DYXRhbG9nCj4+CmVuZG9iago1IDAg"
    "b2JqCjw8Ci9BdXRob3IgKGFub255bW91cykgL0NyZWF0aW9uRGF0ZSAoRDoyMDI2MDgyNzIw"
    "MjA1NC0wNScwMCcpIC9DcmVhdG9yIChSZXBvcnRMYWIgUERGIExpYnJhcnkgLSB3d3cucmVw"
    "b3J0bGFiLmNvbSkgL0tleXdvcmRzICgpIC9Nb2REYXRlIChEOjIwMjYwODI3MjAyMDU0LTA1"
    "JzAwJykgL1Byb2R1Y2VyIChSZXBvcnRMYWIgUERGIExpYnJhcnkgLSB3d3cucmVwb3J0bGFi"
    "LmNvbSkgCiAgL1N1YmplY3QgKHVuc3BlY2lmaWVkKSAvVGl0bGUgKHVudGl0bGVkKSAvVHJh"
    "cHBlZCAvRmFsc2UKPj4KZW5kb2JqCjYgMCBvYmoKPDwKL0NvdW50IDEgL0tpZHMgWyAzIDAg"
    "UiBdIC9UeXBlIC9QYWdlcwo+PgplbmRvYmoKNyAwIG9iago8PAovRmlsdGVyIFsgL0FTQ0lJ"
    "ODVEZWNvZGUgL0ZsYXRlRGVjb2RlIF0gL0xlbmd0aCAxNzYKPj4Kc3RyZWFtCkdhclcwWW4i"
    "VykkcTBpPWBKcVlFaWkzX0wjYWYhI3MkMmdbJj5aW3UnLVpvPyJPcXUncTtnTFZtaCdAcnFM"
    "ME47KkZqTEM6XnVoWU5HNjBVKjRSSV1jLW9CbUBfaVk3WmAoWE4rbGInSyRzalJUMlxoMClq"
    "PGFSJT9OIj0iYmpJLFxRTlxPYDlcWCMrWjMkYUIoIzldUWpsIypnRypxKE5VSjBmP01XdFo+"
    "by5mLH4+ZW5kc3RyZWFtCmVuZG9iagp4cmVmCjAgOAowMDAwMDAwMDAwIDY1NTM1IGYgCjAw"
    "MDAwMDAwNzMgMDAwMDAgbiAKMDAwMDAwMDEwNCAwMDAwMCBuIAowMDAwMDAwMjExIDAwMDAw"
    "IG4gCjAwMDAwMDA0MTQgMDAwMDAgbiAKMDAwMDAwMDQ4MiAwMDAwMCBuIAowMDAwMDAwNzc4"
    "IDAwMDAwIG4gCjAwMDAwMDA4MzcgMDAwMDAgbiAKdHJhaWxlcgo8PAovSUQgCls8NDBmZWVh"
    "Y2YzNGRmM2E5NjIwNzA4ZGJjNTgyYjJlYWI+PDQwZmVlYWNmMzRkZjNhOTYyMDcwOGRiYzU4"
    "MmIyZWFiPl0KJSBSZXBvcnRMYWIgZ2VuZXJhdGVkIFBERiBkb2N1bWVudCAtLSBkaWdlc3Qg"
    "KGh0dHA6Ly93d3cucmVwb3J0bGFiLmNvbSkKCi9JbmZvIDUgMCBSCi9Sb290IDQgMCBSCi9T"
    "aXplIDgKPj4Kc3RhcnR4cmVmCjExMDMKJSVFT0YK"
)


def test_pdf_agreement_extraction_is_bounded_and_provenance_preserving() -> None:
    pages = extract_agreement_pages(
        base64.b64decode(AGREEMENT_PDF_BASE64),
        max_pages=10,
        max_page_content_bytes=100_000,
        max_extracted_chars=10_000,
    )
    assert len(pages) == 1
    assert pages[0].page_number == 1
    assert "Merchant Services Agreement" in pages[0].text
    assert "1.55 percent" in pages[0].text


def test_pdf_agreement_extraction_rejects_non_pdf_and_tight_limits() -> None:
    with pytest.raises(AgreementPdfError, match="valid PDF"):
        extract_agreement_pages(
            b"not-a-pdf",
            max_pages=10,
            max_page_content_bytes=100_000,
            max_extracted_chars=10_000,
        )


def test_uploaded_demo_tenant_agreements_use_durable_compilation_path() -> None:
    principal = api_router.Principal(
        subject="local-demo-user",
        tenant_id="novacart_demo",
        roles=frozenset({"analyst"}),
        auth_mode="disabled",
    )

    assert api_router._is_seeded_agreement(principal, api_router.AGREEMENT.id)
    assert not api_router._is_seeded_agreement(principal, "AGR_UPLOADED_1")
    with pytest.raises(AgreementPdfError, match="page limit"):
        extract_agreement_pages(
            base64.b64decode(AGREEMENT_PDF_BASE64),
            max_pages=0,
            max_page_content_bytes=100_000,
            max_extracted_chars=10_000,
        )


def test_agreement_and_draft_proposals_are_durable_and_tenant_scoped() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    now = datetime(2026, 8, 27, tzinfo=timezone.utc)
    agreement = Agreement(
        id="AGR_LIVE_1",
        merchant="Merchant A",
        title="Merchant Services Agreement",
        status="EXTRACTED",
        effective_from=date(2026, 1, 1),
        source_type="PDF_TEXT_EXTRACTION",
        content_hash="a" * 64,
        clauses=[
            AgreementClause(
                id="CLAUSE_LIVE_1",
                reference="PAGE_1",
                page=1,
                heading="Fees",
                text="Domestic card MDR is 1.55 percent.",
                effective_from=date(2026, 1, 1),
            )
        ],
    )
    control = Control(
        id="CTRL_LIVE_1",
        name="Domestic card MDR",
        control_type=ControlType.MDR_RATE,
        expected="rate=0.0155",
        scope="Domestic cards",
        source=agreement.title,
        source_clause="Page 1",
        status="DRAFT",
        agreement_id=agreement.id,
        clause_id="CLAUSE_LIVE_1",
        logical_control_key="DOMESTIC_CARD_MDR",
        parameters={"rate": "0.0155", "tolerance": "0.01"},
        conditions=["payment.method == 'card'"],
    )
    proposal = ControlProposal(
        id="PROP_LIVE_1",
        agreement_id=agreement.id,
        clause_id="CLAUSE_LIVE_1",
        control_id=control.id,
        status="DRAFT",
        confidence=Decimal("0.95"),
        rationale="The clause contains an explicit rate and scope.",
        source_excerpt=agreement.clauses[0].text,
        extraction_method="LANGGRAPH_STRUCTURED_COMPILATION",
        proposed_control=control,
    )
    with Session(engine) as session:
        session.add(
            ArtifactRecord(
                tenant_id="merchant_a",
                id="ART_AGR_LIVE_1",
                run_id=None,
                case_id=None,
                kind="AGREEMENT_PDF",
                bucket="private",
                object_path="tenants/merchant_a/agreements/AGR_LIVE_1.pdf",
                content_type="application/pdf",
                byte_size=100,
                sha256="a" * 64,
                created_at=now,
            )
        )
        repository = AgreementRepository(session)
        repository.create(
            tenant_id="merchant_a",
            agreement=agreement,
            artifact_id="ART_AGR_LIVE_1",
            actor_id="analyst-a",
        )
        repository.replace_proposals(
            tenant_id="merchant_a",
            agreement_id=agreement.id,
            proposals=[proposal],
            execution_id="CMP_1",
            actor_id="analyst-a",
        )
        session.flush()

        loaded = repository.get(tenant_id="merchant_a", agreement_id=agreement.id)
        proposals = repository.list_proposals(
            tenant_id="merchant_a",
            agreement_id=agreement.id,
        )
        assert loaded is not None
        assert loaded.clauses[0].page == 1
        assert loaded.content_hash == "a" * 64
        assert proposals == [proposal]
        assert repository.list(tenant_id="merchant_b") == []

        manual = repository.add_clause(
            tenant_id="merchant_a",
            agreement_id=agreement.id,
            clause=AgreementClauseCreate(
                reference="4.2(a)",
                heading="Domestic MDR amendment",
                text="Domestic card MDR changes to 1.60 percent.",
            ),
            actor_id="analyst-a",
        )
        repeated = repository.add_clause(
            tenant_id="merchant_a",
            agreement_id=agreement.id,
            clause=AgreementClauseCreate(
                reference="4.2(a)",
                heading="Domestic MDR amendment",
                text="Domestic card MDR changes to 1.60 percent.",
            ),
            actor_id="analyst-a",
        )
        assert manual == repeated
        assert manual.source_type == "MANUAL_ENTRY"
        assert manual.created_by == "analyst-a"
        assert len(repository.get(tenant_id="merchant_a", agreement_id=agreement.id).clauses) == 2

        with pytest.raises(ValueError, match="verification must pass"):
            repository.approve_proposal(
                tenant_id="merchant_a",
                proposal_id=proposal.id,
                expected_version=1,
                actor_id="checker-a",
            )

        verification = repository.verify_proposal(
            tenant_id="merchant_a",
            proposal_id=proposal.id,
            actor_id="analyst-a",
        )
        assert verification.status == "PASSED"
        assert verification.version == 2
        assert verification.detected_mutation_count == verification.mutation_probe_count
        assert any(check["name"] == "agreement_clause_provenance" for check in verification.checks)

        with pytest.raises(ProposalConcurrencyError, match="refresh before retrying"):
            repository.approve_proposal(
                tenant_id="merchant_a",
                proposal_id=proposal.id,
                expected_version=1,
                actor_id="checker-a",
            )
        with pytest.raises(ValueError, match="different verifier and approver"):
            repository.approve_proposal(
                tenant_id="merchant_a",
                proposal_id=proposal.id,
                expected_version=2,
                actor_id="analyst-a",
            )

        approved = repository.approve_proposal(
            tenant_id="merchant_a",
            proposal_id=proposal.id,
            expected_version=2,
            actor_id="checker-a",
        )
        reviewed = repository.get_proposal(
            tenant_id="merchant_a",
            proposal_id=proposal.id,
        )
        assert approved.status == "APPROVED"
        assert reviewed is not None
        assert reviewed.status == "APPROVED"
        assert reviewed.version == 3
        assert reviewed.verified_by == "analyst-a"
        assert reviewed.approved_by == "checker-a"


def test_agreement_upload_is_content_addressed_and_idempotent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "agreements.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{database_path.as_posix()}")
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()
    engine = get_engine()
    assert engine is not None
    Base.metadata.create_all(engine)
    uploaded: list[str] = []

    class _Storage:
        configured = True

        async def upload(
            self,
            object_path: str,
            content: bytes,
            *,
            content_type: str,
            overwrite: bool,
        ) -> StoredObject:
            assert overwrite is True
            uploaded.append(object_path)
            return StoredObject(
                bucket="private",
                object_path=object_path,
                content_type=content_type,
                byte_size=len(content),
                sha256="a" * 64,
            )

        async def delete(self, _object_path: str) -> None:
            raise AssertionError("Successful metadata writes must not delete agreement bytes")

    monkeypatch.setattr(api_router, "SupabaseStorage", _Storage)
    content = base64.b64decode(AGREEMENT_PDF_BASE64)
    payload = {
        "merchant": "Merchant A",
        "title": "Merchant Services Agreement",
        "effective_from": "2026-01-01",
    }
    try:
        client = TestClient(app)
        first = client.post(
            "/api/v1/agreements/upload",
            data=payload,
            files={"file": ("agreement.pdf", content, "application/pdf")},
        )
        second = client.post(
            "/api/v1/agreements/upload",
            data=payload,
            files={"file": ("agreement.pdf", content, "application/pdf")},
        )
        assert first.status_code == second.status_code == 201
        assert first.json()["id"] == second.json()["id"]
        assert first.json()["clauses"][0]["page"] == 1
        assert len(uploaded) == 1
        clause_payload = {
            "reference": "4.2(a)",
            "heading": "Domestic MDR amendment",
            "text": "Domestic card MDR changes to 1.60 percent.",
        }
        clause = client.post(
            f"/api/v1/agreements/{first.json()['id']}/clauses",
            json=clause_payload,
        )
        repeated_clause = client.post(
            f"/api/v1/agreements/{first.json()['id']}/clauses",
            json=clause_payload,
        )
        assert clause.status_code == repeated_clause.status_code == 201
        assert clause.json()["id"] == repeated_clause.json()["id"]
        assert clause.json()["source_type"] == "MANUAL_ENTRY"
        assert clause.json()["created_by"] == "local-demo-user"
        listed = client.get("/api/v1/agreements")
        proposals = client.get(f"/api/v1/agreements/{first.json()['id']}/control-proposals")
        assert listed.status_code == 200
        assert listed.json()[0]["id"] == first.json()["id"]
        assert len(listed.json()[0]["clauses"]) == 2
        assert proposals.status_code == 200
        assert proposals.json() == []
    finally:
        get_session_factory.cache_clear()
        get_engine.cache_clear()
        get_settings.cache_clear()
        os.environ.pop("DATABASE_URL", None)
