from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from pathlib import PurePath
from typing import Annotated, Any
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Request, UploadFile

from app.agents.checkpoint import agent_checkpointer
from app.agents.control_workflows import (
    AgreementControlCompiler,
    BlindSpotRemediationController,
    validate_candidate_evidence,
)
from app.agents.investigation import InvestigationController
from app.agents.models import (
    AgentEvidence,
    AgreementCompilationExecution,
    BlindSpotRemediationExecution,
    InvestigationExecution,
    TypedControlCandidate,
)
from app.ai.provider import build_ai_runtime
from app.core.config import get_settings
from app.core.money import expected_fee, money
from app.domain.models import (
    Agreement,
    AgreementClause,
    AgreementClauseCreate,
    AiCapability,
    BackgroundJob,
    CaseEvidence,
    CaseTransitionRequest,
    Control,
    ControlBacktest,
    ControlCoverageSummary,
    ControlProposal,
    ControlProposalApprovalRequest,
    ControlProposalVerification,
    ControlType,
    CounterfactualSettlement,
    DemoLoadResponse,
    EvidenceExportResponse,
    ExceptionCase,
    ExceptionCaseStatus,
    ExpectedActualResponse,
    HypothesisResponse,
    HypothesisVerification,
    InfrastructureCapability,
    JobSubmission,
    McpEvidenceCapability,
    MutationTestSummary,
    PaymentGraph,
    PaymentLifecycle,
    RazorpayConnectionStatus,
    RazorpaySyncRequest,
    RazorpaySyncSummary,
    RootCause,
    RunListItem,
    RunOperationalMetrics,
    RunSourceType,
    RunStage,
    RunSummary,
    SourceRowError,
    SourceRunResponse,
    SourceUploadBatchResponse,
    SourceUploadResponse,
    TemporalReplayRequest,
    TemporalReplayResponse,
    UnresolvedMatch,
    Violation,
    ViolationLineageResponse,
)
from app.ingestion.csv import parse_source_csv, read_source_csv
from app.ingestion.pdf import (
    ExtractedAgreementPage,
    extract_agreement_pages,
    infer_agreement_effective_from,
    segment_agreement_clauses,
)
from app.ingestion.pipeline import execute_source_run
from app.integrations.razorpay.client import RazorpayNotConfiguredError
from app.integrations.razorpay.mcp_evidence import capability as mcp_evidence_capability
from app.integrations.razorpay.sync import connection_status, sync_razorpay
from app.mutations.engine import MUTATION_TEST_ID, execute_mutation_test
from app.persistence.database import session_scope
from app.persistence.orm import ArtifactRecord, BackgroundJobRecord, RunRecord
from app.persistence.repository import (
    AgentExecutionRepository,
    AgreementRepository,
    CaseConcurrencyError,
    CaseRepository,
    JobRepository,
    ProposalConcurrencyError,
    RunRepository,
)
from app.security.auth import Principal, get_current_principal, require_roles
from app.services import live_payment_views
from app.services.demo import DEMO_RUN_ID, store
from app.services.governance import AGREEMENT, CONTROLS, governance
from app.storage.service import ArtifactService
from app.storage.supabase import SupabaseStorage

router = APIRouter(prefix="/api/v1", dependencies=[Depends(get_current_principal)])
mutation_test: MutationTestSummary | None = None
investigation_runs: dict[str, InvestigationExecution] = {}
logger = logging.getLogger("sl3dge.api")
DEMO_TENANT_ID = "novacart_demo"


def _require_seeded_demo(principal: Principal) -> None:
    """Fail closed before a request can read or mutate process-local demo fixtures."""
    settings = get_settings()
    if settings.environment not in {"development", "test"} or principal.tenant_id != DEMO_TENANT_ID:
        raise HTTPException(status_code=404, detail="Resource not found")


def _validate_dataset_metadata(value: str | None, *, field: str) -> str | None:
    """Validate optional dataset provenance supplied with an uploaded run."""

    if value is None:
        return None
    normalized = value.strip()
    if (
        not normalized
        or len(normalized) > 160
        or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", normalized)
    ):
        raise HTTPException(
            status_code=422,
            detail=(
                f"{field} must be 1-160 characters and contain only letters, "
                "numbers, '.', '_' or '-'."
            ),
        )
    return normalized


def _seeded_demo_enabled(principal: Principal) -> bool:
    settings = get_settings()
    return settings.environment in {"development", "test"} and principal.tenant_id == DEMO_TENANT_ID


def _is_seeded_agreement(principal: Principal, agreement_id: str) -> bool:
    """Return whether an agreement ID refers to the immutable in-memory demo fixture."""

    return _seeded_demo_enabled(principal) and agreement_id == AGREEMENT.id


def _job_response(record: BackgroundJobRecord) -> BackgroundJob:
    return BackgroundJob(
        id=record.id,
        run_id=record.run_id,
        job_type=record.job_type,
        status=record.status,
        attempt_count=record.attempt_count,
        max_attempts=record.max_attempts,
        result=record.result,
        error=record.error,
        created_at=record.created_at,
        updated_at=record.updated_at,
        started_at=record.started_at,
        finished_at=record.finished_at,
    )


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "sl3dge-api"}


@router.get("/capabilities/infrastructure", response_model=InfrastructureCapability)
def infrastructure_capability() -> InfrastructureCapability:
    settings = get_settings()
    storage = SupabaseStorage(settings)
    return InfrastructureCapability(
        database_configured=bool(settings.database_url),
        database_mode="POSTGRES" if settings.database_url else "IN_MEMORY",
        storage_configured=storage.configured,
        storage_bucket=settings.supabase_storage_bucket,
        storage_policy=(
            "Private bucket; privileged upload credentials remain backend-only and only "
            "object paths are stored in PostgreSQL."
        ),
    )


@router.get("/capabilities/ai", response_model=AiCapability)
def ai_capability() -> AiCapability:
    runtime = build_ai_runtime()
    return AiCapability(
        provider=runtime.provider,
        model=runtime.model,
        configured=runtime.configured,
        fallback_policy=runtime.fallback_policy,
    )


async def _read_source_upload(file: UploadFile) -> tuple[str, bytes]:
    filename = PurePath(file.filename or "source.csv").name
    if not filename.lower().endswith(".csv"):
        raise HTTPException(status_code=422, detail="Only CSV source files are accepted")
    if file.content_type not in {
        None,
        "",
        "text/csv",
        "application/csv",
        "application/vnd.ms-excel",
        "text/plain",
    }:
        raise HTTPException(status_code=422, detail="The upload content type is not CSV")
    settings = get_settings()
    content = await file.read(settings.max_upload_bytes + 1)
    if len(content) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="CSV source file exceeds the configured limit")
    return filename, content


async def _persist_source_upload(
    *,
    filename: str,
    content: bytes,
    principal: Principal,
    request: Request,
) -> SourceUploadResponse:
    parsed = parse_source_csv(content, filename=filename)
    if parsed.source_type == "UNRESOLVED":
        raise HTTPException(
            status_code=422,
            detail="CSV schema could not be classified safely; manual mapping is required",
        )
    settings = get_settings()
    upload_id = f"UPLOAD_{uuid4().hex[:12].upper()}"
    category = parsed.source_type.lower()
    object_path = f"tenants/{principal.tenant_id}/uploads/{category}/{upload_id}.csv"
    storage = SupabaseStorage(settings)
    storage_status = "VALIDATED_ONLY"
    persisted_path: str | None = None
    if storage.configured and settings.database_url:
        stored = await storage.upload(
            object_path,
            content,
            content_type="text/csv",
            overwrite=False,
        )
        try:
            with session_scope(tenant_id=principal.tenant_id) as session:
                ArtifactService(storage, session).record(
                    stored=stored,
                    artifact_id=upload_id,
                    kind="SOURCE_CSV",
                    tenant_id=principal.tenant_id,
                    run_id=None,
                )
                RunRepository(session).write_audit(
                    tenant_id=principal.tenant_id,
                    actor_id=principal.subject,
                    action="SOURCE_UPLOAD",
                    resource_type="artifact",
                    resource_id=upload_id,
                    outcome="AVAILABLE",
                    details={
                        "filename": filename,
                        "row_count": parsed.row_count,
                        "source_type": parsed.source_type,
                        "classification_confidence": str(parsed.classification_confidence),
                        "row_error_count": parsed.row_error_count,
                    },
                    request_id=request.state.request_id,
                )
        except Exception:
            try:
                await storage.delete(stored.object_path)
            except Exception:
                logger.exception(
                    "Storage compensation failed upload_id=%s tenant_id=%s",
                    upload_id,
                    principal.tenant_id,
                )
            raise
        storage_status = "PRIVATE_STORAGE"
        persisted_path = stored.object_path
    return SourceUploadResponse(
        upload_id=upload_id,
        filename=filename,
        source_type=parsed.source_type,
        classification_confidence=parsed.classification_confidence,
        classification_evidence=parsed.classification_evidence,
        row_count=parsed.row_count,
        columns=parsed.columns,
        decimal_values_checked=parsed.decimal_values_checked,
        row_errors=[
            SourceRowError(
                row_number=error.row_number,
                column=error.column,
                message=error.message,
            )
            for error in parsed.row_errors
        ],
        row_error_count=parsed.row_error_count,
        schema_drift=parsed.schema_drift,
        drift_columns=parsed.drift_columns,
        storage_status=storage_status,
        object_path=persisted_path,
    )


@router.post("/sources/upload", response_model=SourceUploadResponse)
async def upload_source(
    file: Annotated[UploadFile, File()],
    principal: Annotated[Principal, Depends(require_roles("analyst"))],
    request: Request,
) -> SourceUploadResponse:
    filename, content = await _read_source_upload(file)
    return await _persist_source_upload(
        filename=filename,
        content=content,
        principal=principal,
        request=request,
    )


@router.post("/sources/uploads", response_model=SourceUploadBatchResponse)
async def upload_sources(
    files: Annotated[list[UploadFile], File()],
    principal: Annotated[Principal, Depends(require_roles("analyst"))],
    request: Request,
) -> SourceUploadBatchResponse:
    settings = get_settings()
    if not files:
        raise HTTPException(status_code=422, detail="At least one CSV source file is required")
    if len(files) > settings.max_upload_files:
        raise HTTPException(
            status_code=413,
            detail=f"A batch may contain at most {settings.max_upload_files} CSV files",
        )

    payloads: list[tuple[str, bytes]] = []
    total_bytes = 0
    for file in files:
        filename, content = await _read_source_upload(file)
        total_bytes += len(content)
        if total_bytes > settings.max_upload_batch_bytes:
            raise HTTPException(
                status_code=413,
                detail="CSV upload batch exceeds the configured aggregate limit",
            )
        payloads.append((filename, content))

    results: list[SourceUploadResponse] = []
    for filename, content in payloads:
        try:
            result = await _persist_source_upload(
                filename=filename,
                content=content,
                principal=principal,
                request=request,
            )
        except HTTPException as exc:
            results.append(
                SourceUploadResponse(
                    filename=filename,
                    status="REJECTED",
                    error=str(exc.detail),
                )
            )
        except ValueError as exc:
            results.append(
                SourceUploadResponse(
                    filename=filename,
                    status="REJECTED",
                    error=str(exc),
                )
            )
        except Exception:
            logger.exception(
                "Source batch item failed filename=%s tenant_id=%s",
                filename,
                principal.tenant_id,
            )
            results.append(
                SourceUploadResponse(
                    filename=filename,
                    status="REJECTED",
                    error="The source file could not be stored safely",
                )
            )
        else:
            results.append(result)

    accepted_count = sum(item.status == "ACCEPTED" for item in results)
    return SourceUploadBatchResponse(
        file_count=len(results),
        accepted_count=accepted_count,
        rejected_count=len(results) - accepted_count,
        files=results,
    )


@router.post("/runs/from-uploads", response_model=SourceRunResponse, status_code=201)
async def create_run_from_uploads(
    files: Annotated[list[UploadFile], File()],
    upload_ids: Annotated[list[str], Form()],
    principal: Annotated[Principal, Depends(require_roles("analyst"))],
    request: Request,
    name: Annotated[str | None, Form(max_length=160)] = None,
    dataset_id: Annotated[str | None, Form(max_length=160)] = None,
    dataset_type: Annotated[str | None, Form(max_length=160)] = None,
) -> SourceRunResponse:
    """Create and execute a run from a previously accepted upload bundle.

    The browser resends the selected bytes so the server can verify them against
    immutable artifact hashes before execution. This prevents a classify-then-swap
    race and keeps the accepted artifact as the authoritative source.
    """

    settings = get_settings()
    dataset_id = _validate_dataset_metadata(dataset_id, field="dataset_id")
    dataset_type = _validate_dataset_metadata(dataset_type, field="dataset_type")
    if not settings.database_url:
        raise HTTPException(status_code=503, detail="CSV control runs require DATABASE_URL")
    if not files or len(files) != len(upload_ids):
        raise HTTPException(
            status_code=422,
            detail="Every source file must have one accepted upload identifier",
        )
    if len(files) > settings.max_upload_files:
        raise HTTPException(status_code=413, detail="Too many source files")

    payloads: list[tuple[str, str, bytes]] = []
    total_bytes = 0
    for upload_id, file in zip(upload_ids, files, strict=True):
        filename, content = await _read_source_upload(file)
        total_bytes += len(content)
        if total_bytes > settings.max_upload_batch_bytes:
            raise HTTPException(
                status_code=413, detail="CSV run batch exceeds the configured aggregate limit"
            )
        payloads.append((upload_id, filename, content))

    with session_scope(tenant_id=principal.tenant_id) as session:
        for upload_id, filename, content in payloads:
            artifact = session.get(ArtifactRecord, (principal.tenant_id, upload_id))
            if artifact is None or not artifact.kind.startswith("SOURCE_"):
                raise HTTPException(
                    status_code=404, detail=f"Accepted upload not found: {filename}"
                )
            if artifact.sha256 != sha256(content).hexdigest():
                raise HTTPException(
                    status_code=409, detail=f"File changed after classification: {filename}"
                )
            if artifact.run_id is not None:
                raise HTTPException(
                    status_code=409, detail=f"Upload is already attached to run {artifact.run_id}"
                )

    try:
        documents = [
            (upload_id, filename, read_source_csv(content, filename=filename))
            for upload_id, filename, content in payloads
        ]
        result = execute_source_run(
            documents,
            tenant_id=principal.tenant_id,
            actor_id=principal.subject,
            request_id=request.state.request_id,
            run_name=name.strip() if name and name.strip() else None,
            dataset_id=dataset_id,
            dataset_type=dataset_type,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    with session_scope(tenant_id=principal.tenant_id) as session:
        for upload_id, _, _ in payloads:
            artifact = session.get(ArtifactRecord, (principal.tenant_id, upload_id))
            if artifact is not None:
                artifact.run_id = result.run_id
    return result


@router.post("/agreements/upload", response_model=Agreement, status_code=201)
async def upload_agreement(
    request: Request,
    file: Annotated[UploadFile, File(...)],
    merchant: Annotated[str, Form(min_length=1, max_length=200)],
    title: Annotated[str, Form(min_length=1, max_length=240)],
    effective_from: Annotated[date, Form()],
    principal: Annotated[Principal, Depends(require_roles("analyst"))],
    effective_to: Annotated[date | None, Form()] = None,
) -> Agreement:
    settings = get_settings()
    storage = SupabaseStorage()
    if not settings.database_url or not storage.configured:
        raise HTTPException(
            status_code=503,
            detail="Agreement ingestion requires PostgreSQL and private Supabase Storage",
        )
    filename = PurePath(file.filename or "agreement.pdf").name
    if not filename.lower().endswith(".pdf") or file.content_type not in {
        None,
        "",
        "application/pdf",
        "application/octet-stream",
    }:
        raise HTTPException(status_code=422, detail="Only PDF agreements are accepted")
    if effective_to is not None and effective_to < effective_from:
        raise HTTPException(status_code=422, detail="effective_to must not precede effective_from")
    content = await file.read(settings.max_upload_bytes + 1)
    if len(content) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="Agreement exceeds MAX_UPLOAD_BYTES")
    pages = extract_agreement_pages(
        content,
        max_pages=settings.max_agreement_pages,
        max_page_content_bytes=settings.max_pdf_page_content_bytes,
        max_extracted_chars=settings.max_extracted_agreement_chars,
    )
    extracted_clauses = segment_agreement_clauses(
        pages,
        agreement_effective_from=infer_agreement_effective_from(
            pages,
            fallback=effective_from,
        ),
    )
    if not extracted_clauses:
        raise HTTPException(
            status_code=422,
            detail="No numbered clauses could be segmented from this agreement PDF",
        )
    content_hash = sha256(content).hexdigest()
    with session_scope(tenant_id=principal.tenant_id) as session:
        existing = AgreementRepository(session).get_by_hash(
            tenant_id=principal.tenant_id,
            content_hash=content_hash,
        )
        if existing is not None:
            return existing

    agreement_id = f"AGR_{content_hash[:20].upper()}"
    artifact_id = f"ART_{agreement_id}"
    agreement = Agreement(
        id=agreement_id,
        merchant=merchant.strip(),
        title=title.strip(),
        status="EXTRACTED",
        effective_from=effective_from,
        effective_to=effective_to,
        source_type="PDF_TEXT_EXTRACTION",
        content_hash=content_hash,
        clauses=[
            AgreementClause(
                id=(f"CLAUSE_{content_hash[:12].upper()}_{clause.clause_number.replace('.', '_')}"),
                reference=clause.clause_number,
                page=clause.page_number,
                heading=clause.clause_title[:240],
                text=clause.text,
                effective_from=clause.effective_from,
                effective_to=effective_to,
                clause_number=clause.clause_number,
                clause_title=clause.clause_title,
                source_offsets={
                    "page_number": clause.page_number,
                    "start_offset": clause.start_offset,
                    "end_offset": clause.end_offset,
                    "offset_basis": "normalized_page_text",
                },
            )
            for clause in extracted_clauses
        ],
    )
    object_path = f"tenants/{principal.tenant_id}/agreements/{agreement_id}.pdf"
    stored = await storage.upload(
        object_path,
        content,
        content_type="application/pdf",
        # The object path is content-addressed, so an upsert can only replace
        # identical bytes and makes retries safe after an interrupted DB write.
        overwrite=True,
    )
    try:
        with session_scope(tenant_id=principal.tenant_id) as session:
            ArtifactService(storage, session).record(
                stored=stored,
                artifact_id=artifact_id,
                kind="AGREEMENT_PDF",
                tenant_id=principal.tenant_id,
            )
            created = AgreementRepository(session).create(
                tenant_id=principal.tenant_id,
                agreement=agreement,
                artifact_id=artifact_id,
                actor_id=principal.subject,
            )
            RunRepository(session).write_audit(
                tenant_id=principal.tenant_id,
                actor_id=principal.subject,
                action="AGREEMENT_INGESTED",
                resource_type="agreement",
                resource_id=agreement_id,
                outcome="EXTRACTED",
                details={
                    "artifact_id": artifact_id,
                    "page_count": len(pages),
                    "clause_count": len(extracted_clauses),
                    "content_hash": content_hash,
                },
                request_id=request.state.request_id,
            )
            return created
    except Exception:
        try:
            with session_scope(tenant_id=principal.tenant_id) as session:
                concurrent = AgreementRepository(session).get_by_hash(
                    tenant_id=principal.tenant_id,
                    content_hash=content_hash,
                )
                if concurrent is not None:
                    return concurrent
        except Exception:
            logger.exception(
                "Agreement idempotency lookup failed agreement_id=%s tenant_id=%s",
                agreement_id,
                principal.tenant_id,
            )
        try:
            await storage.delete(stored.object_path)
        except Exception:
            logger.exception(
                "Agreement storage compensation failed agreement_id=%s tenant_id=%s",
                agreement_id,
                principal.tenant_id,
            )
        raise


def _clause_models_from_pages(
    *, agreement: Agreement, pages: list[ExtractedAgreementPage], content_hash: str
) -> list[AgreementClause]:
    segmented = segment_agreement_clauses(
        pages,
        agreement_effective_from=infer_agreement_effective_from(
            pages,
            fallback=agreement.effective_from,
        ),
    )
    return [
        AgreementClause(
            id=(f"CLAUSE_{content_hash[:12].upper()}_{clause.clause_number.replace('.', '_')}"),
            reference=clause.clause_number,
            page=clause.page_number,
            heading=clause.clause_title[:240],
            text=clause.text,
            effective_from=clause.effective_from,
            effective_to=agreement.effective_to,
            clause_number=clause.clause_number,
            clause_title=clause.clause_title,
            source_offsets={
                "page_number": clause.page_number,
                "start_offset": clause.start_offset,
                "end_offset": clause.end_offset,
                "offset_basis": "normalized_page_text",
            },
        )
        for clause in segmented
    ]


@router.post("/demo/load", response_model=DemoLoadResponse)
def load_demo(
    principal: Annotated[Principal, Depends(require_roles("analyst"))],
) -> DemoLoadResponse:
    _require_seeded_demo(principal)
    return store.load()


@router.get("/controls", response_model=list[Control])
def list_controls(
    principal: Annotated[Principal, Depends(require_roles("analyst", "approver", "viewer"))],
) -> list[Control]:
    if _seeded_demo_enabled(principal):
        return CONTROLS
    if get_settings().database_url:
        with session_scope(tenant_id=principal.tenant_id) as session:
            return RunRepository(session).list_controls(tenant_id=principal.tenant_id)
    _require_seeded_demo(principal)
    return []


def _control(control_id: str) -> Control:
    try:
        return governance.control(control_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Control not found") from exc


def _candidate_from_proposal(proposal: ControlProposal) -> TypedControlCandidate:
    control = proposal.proposed_control
    return TypedControlCandidate(
        candidate_id=control.id,
        logical_control_key=control.logical_control_key,
        control_type=control.control_type,
        name=control.name,
        clause_id=proposal.clause_id,
        version=control.version,
        effective_from=control.effective_from,
        effective_to=control.effective_to,
        supersedes_candidate_id=control.supersedes_control_id,
        parameters=control.parameters,
        conditions=control.conditions,
        rationale=proposal.rationale,
        confidence=proposal.confidence,
    )


def _proposal_from_candidate(
    candidate: TypedControlCandidate,
    *,
    agreement_record: Agreement,
    execution_id: str,
) -> ControlProposal:
    clauses = {clause.id: clause for clause in agreement_record.clauses}
    clause = clauses.get(candidate.clause_id)
    if clause is None:
        raise ValueError("A control candidate cited a clause outside the agreement")
    fingerprint = (
        sha256(f"{agreement_record.id}:{candidate.candidate_id}".encode()).hexdigest()[:20].upper()
    )
    control_id = f"CTRL_{fingerprint}"
    expected = (
        ", ".join(f"{key}={value}" for key, value in sorted(candidate.parameters.items()))
        or "Typed agreement condition"
    )
    control = Control(
        id=control_id,
        name=candidate.name,
        control_type=candidate.control_type,
        expected=expected,
        scope=" · ".join(candidate.conditions) or f"Agreement page {clause.page}",
        source=agreement_record.title,
        source_clause=(f"Clause {clause.clause_number or clause.reference} · Page {clause.page}"),
        status="DRAFT",
        agreement_id=agreement_record.id,
        clause_id=clause.id,
        logical_control_key=candidate.logical_control_key,
        version=candidate.version,
        effective_from=candidate.effective_from,
        effective_to=candidate.effective_to,
        supersedes_control_id=candidate.supersedes_candidate_id,
        parameters=candidate.parameters,
        conditions=candidate.conditions,
        extraction_method=(
            "DETERMINISTIC_CLAUSE_EXTRACTION"
            if candidate.rationale.startswith("Deterministically extracted")
            else "LANGGRAPH_STRUCTURED_COMPILATION"
        ),
    )
    validation_warnings = validate_candidate_evidence(
        candidate,
        [clause.model_dump(mode="json")],
    )
    return ControlProposal(
        id=f"PROP_{fingerprint}",
        agreement_id=agreement_record.id,
        clause_id=clause.id,
        control_id=control_id,
        status="REVIEW_REQUIRED" if validation_warnings else "DRAFT",
        confidence=candidate.confidence,
        rationale=candidate.rationale,
        source_excerpt=clause.text,
        extraction_method=control.extraction_method,
        proposed_control=control,
        validation_warnings=validation_warnings,
    )


async def _run_agreement_compilation(
    *,
    agreement_id: str,
    principal: Principal,
    request: Request,
) -> tuple[AgreementCompilationExecution, list[ControlProposal]]:
    if _is_seeded_agreement(principal, agreement_id):
        try:
            agreement_record = governance.agreement(agreement_id)
            existing_proposals = governance.proposals(agreement_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Agreement not found") from exc
    elif get_settings().database_url:
        with session_scope(tenant_id=principal.tenant_id) as session:
            repository = AgreementRepository(session)
            agreement_record = repository.get(
                tenant_id=principal.tenant_id,
                agreement_id=agreement_id,
            )
            if agreement_record is None:
                raise HTTPException(status_code=404, detail="Agreement not found")
            existing_proposals = repository.list_proposals(
                tenant_id=principal.tenant_id,
                agreement_id=agreement_id,
            )
            pages = [
                ExtractedAgreementPage(page_number=clause.page, text=clause.text)
                for clause in agreement_record.clauses
            ]
            pdf_effective_from = infer_agreement_effective_from(
                pages,
                fallback=agreement_record.effective_from,
            )
            needs_resegmentation = any(
                clause.reference.upper().startswith("PAGE_") for clause in agreement_record.clauses
            ) or (
                pdf_effective_from != agreement_record.effective_from
                and any(
                    clause.effective_from == agreement_record.effective_from
                    for clause in agreement_record.clauses
                )
            )
            if needs_resegmentation:
                segmented = _clause_models_from_pages(
                    agreement=agreement_record,
                    pages=pages,
                    content_hash=agreement_record.content_hash,
                )
                if segmented:
                    agreement_record = repository.replace_extracted_clauses(
                        tenant_id=principal.tenant_id,
                        agreement_id=agreement_id,
                        clauses=segmented,
                        actor_id=principal.subject,
                    )
                    existing_proposals = []
    else:
        raise HTTPException(status_code=404, detail="Agreement not found")

    seeds = [_candidate_from_proposal(proposal) for proposal in existing_proposals]
    runtime = build_ai_runtime()
    async with agent_checkpointer() as checkpointer:
        result = await AgreementControlCompiler(
            runtime.provider_client,
            checkpointer=checkpointer,
        ).run(
            tenant_id=principal.tenant_id,
            agreement_id=agreement_id,
            clauses=[clause.model_dump(mode="json") for clause in agreement_record.clauses],
            seed_candidates=seeds,
        )
    compiled = (
        [
            _proposal_from_candidate(
                candidate,
                agreement_record=agreement_record,
                execution_id=result.execution_id,
            )
            for candidate in result.proposals
        ]
        if result.schema_valid
        else []
    )
    if get_settings().database_url:
        with session_scope(tenant_id=principal.tenant_id) as session:
            AgentExecutionRepository(session).save(
                tenant_id=principal.tenant_id,
                execution_id=result.execution_id,
                workflow=result.workflow,
                resource_type="agreement",
                resource_id=agreement_id,
                status=result.status,
                result=result.model_dump(mode="json"),
                started_at=result.started_at,
                completed_at=result.completed_at,
            )
            if not _is_seeded_agreement(principal, agreement_id):
                agreement_repository = AgreementRepository(session)
                agreement_repository.replace_proposals(
                    tenant_id=principal.tenant_id,
                    agreement_id=agreement_id,
                    proposals=compiled,
                    execution_id=result.execution_id,
                    actor_id=principal.subject,
                )
                compiled = agreement_repository.list_proposals(
                    tenant_id=principal.tenant_id,
                    agreement_id=agreement_id,
                )
            RunRepository(session).write_audit(
                tenant_id=principal.tenant_id,
                actor_id=principal.subject,
                action="AGREEMENT_CONTROL_COMPILATION_COMPLETED",
                resource_type="agreement",
                resource_id=agreement_id,
                outcome=result.status,
                details={
                    "execution_id": result.execution_id,
                    "proposal_count": len(compiled),
                    "conflict_count": result.conflict_count,
                },
                request_id=request.state.request_id,
            )
    return result, compiled


@router.get("/agreements", response_model=list[Agreement])
def agreements(
    principal: Annotated[Principal, Depends(require_roles("analyst", "approver", "viewer"))],
) -> list[Agreement]:
    stored: list[Agreement] = []
    database_configured = bool(get_settings().database_url)
    if database_configured:
        with session_scope(tenant_id=principal.tenant_id) as session:
            stored = AgreementRepository(session).list(tenant_id=principal.tenant_id)
    if _seeded_demo_enabled(principal):
        return [*stored, *([] if any(item.id == AGREEMENT.id for item in stored) else [AGREEMENT])]
    if database_configured:
        return stored
    _require_seeded_demo(principal)
    return []


@router.get("/agreements/{agreement_id}", response_model=Agreement)
def agreement(
    agreement_id: str,
    principal: Annotated[Principal, Depends(require_roles("analyst", "approver", "viewer"))],
) -> Agreement:
    if _seeded_demo_enabled(principal) and agreement_id == AGREEMENT.id:
        return governance.agreement(agreement_id)
    if get_settings().database_url:
        with session_scope(tenant_id=principal.tenant_id) as session:
            record = AgreementRepository(session).get(
                tenant_id=principal.tenant_id,
                agreement_id=agreement_id,
            )
            if record is not None:
                return record
    raise HTTPException(status_code=404, detail="Agreement not found")


@router.post(
    "/agreements/{agreement_id}/clauses",
    response_model=AgreementClause,
    status_code=201,
)
def add_agreement_clause(
    agreement_id: str,
    clause: AgreementClauseCreate,
    principal: Annotated[Principal, Depends(require_roles("analyst"))],
    request: Request,
) -> AgreementClause:
    if not get_settings().database_url:
        raise HTTPException(status_code=503, detail="Agreement persistence is not configured")
    with session_scope(tenant_id=principal.tenant_id) as session:
        repository = AgreementRepository(session)
        try:
            created = repository.add_clause(
                tenant_id=principal.tenant_id,
                agreement_id=agreement_id,
                clause=clause,
                actor_id=principal.subject,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Agreement not found") from exc
        RunRepository(session).write_audit(
            tenant_id=principal.tenant_id,
            actor_id=principal.subject,
            action="AGREEMENT_CLAUSE_ADDED",
            resource_type="agreement_clause",
            resource_id=created.id,
            outcome="EXTRACTED",
            details={
                "agreement_id": agreement_id,
                "reference": created.reference,
                "source_type": created.source_type,
            },
            request_id=request.state.request_id,
        )
        return created


@router.post(
    "/agreements/{agreement_id}/extract-controls",
    response_model=list[ControlProposal],
)
async def extract_agreement_controls(
    agreement_id: str,
    principal: Annotated[Principal, Depends(require_roles("analyst"))],
    request: Request,
) -> list[ControlProposal]:
    if _seeded_demo_enabled(principal) and agreement_id == AGREEMENT.id:
        return governance.proposals(agreement_id)
    _, proposals = await _run_agreement_compilation(
        agreement_id=agreement_id,
        principal=principal,
        request=request,
    )
    return proposals


@router.get(
    "/agreements/{agreement_id}/control-proposals",
    response_model=list[ControlProposal],
)
def agreement_control_proposals(
    agreement_id: str,
    principal: Annotated[Principal, Depends(require_roles("analyst", "approver", "viewer"))],
) -> list[ControlProposal]:
    if _seeded_demo_enabled(principal) and agreement_id == AGREEMENT.id:
        return governance.proposals(agreement_id)
    if get_settings().database_url:
        with session_scope(tenant_id=principal.tenant_id) as session:
            repository = AgreementRepository(session)
            if repository.get(tenant_id=principal.tenant_id, agreement_id=agreement_id) is None:
                raise HTTPException(status_code=404, detail="Agreement not found")
            return repository.list_proposals(
                tenant_id=principal.tenant_id,
                agreement_id=agreement_id,
            )
    raise HTTPException(status_code=404, detail="Agreement not found")


@router.post(
    "/agreements/{agreement_id}/control-proposals/manual",
    response_model=ControlProposal,
    status_code=201,
)
def create_manual_control_proposal(
    agreement_id: str,
    candidate: TypedControlCandidate,
    principal: Annotated[Principal, Depends(require_roles("analyst"))],
    request: Request,
) -> ControlProposal:
    if not get_settings().database_url or (
        _seeded_demo_enabled(principal) and agreement_id == AGREEMENT.id
    ):
        raise HTTPException(status_code=404, detail="Resource not found")
    with session_scope(tenant_id=principal.tenant_id) as session:
        repository = AgreementRepository(session)
        agreement_record = repository.get(
            tenant_id=principal.tenant_id,
            agreement_id=agreement_id,
        )
        if agreement_record is None:
            raise HTTPException(status_code=404, detail="Agreement not found")
        proposal = _proposal_from_candidate(
            candidate,
            agreement_record=agreement_record,
            execution_id="MANUAL_TYPED_PROPOSAL",
        )
        created = repository.add_proposal(
            tenant_id=principal.tenant_id,
            proposal=proposal,
            execution_id=None,
            actor_id=principal.subject,
        )
        RunRepository(session).write_audit(
            tenant_id=principal.tenant_id,
            actor_id=principal.subject,
            action="CONTROL_PROPOSAL_CREATED",
            resource_type="control_proposal",
            resource_id=created.id,
            outcome="DRAFT",
            details={"agreement_id": agreement_id, "control_id": created.control_id},
            request_id=request.state.request_id,
        )
        return created


@router.post(
    "/control-proposals/{proposal_id}/verify",
    response_model=ControlProposalVerification,
)
def verify_control_proposal(
    proposal_id: str,
    principal: Annotated[Principal, Depends(require_roles("analyst"))],
    request: Request,
) -> ControlProposalVerification:
    if not get_settings().database_url:
        raise HTTPException(status_code=404, detail="Resource not found")
    with session_scope(tenant_id=principal.tenant_id) as session:
        repository = AgreementRepository(session)
        try:
            result = repository.verify_proposal(
                tenant_id=principal.tenant_id,
                proposal_id=proposal_id,
                actor_id=principal.subject,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Control proposal not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        RunRepository(session).write_audit(
            tenant_id=principal.tenant_id,
            actor_id=principal.subject,
            action="CONTROL_PROPOSAL_VERIFIED",
            resource_type="control_proposal",
            resource_id=proposal_id,
            outcome=result.status,
            details={
                "version": result.version,
                "input_fingerprint": result.input_fingerprint,
            },
            request_id=request.state.request_id,
        )
        return result


@router.post(
    "/control-proposals/{proposal_id}/approve",
    response_model=Control,
)
def approve_control_proposal(
    proposal_id: str,
    payload: ControlProposalApprovalRequest,
    principal: Annotated[Principal, Depends(require_roles("approver"))],
    request: Request,
) -> Control:
    if not get_settings().database_url:
        raise HTTPException(status_code=404, detail="Resource not found")
    with session_scope(tenant_id=principal.tenant_id) as session:
        repository = AgreementRepository(session)
        try:
            approved = repository.approve_proposal(
                tenant_id=principal.tenant_id,
                proposal_id=proposal_id,
                expected_version=payload.expected_version,
                actor_id=principal.subject,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Control proposal not found") from exc
        except ProposalConcurrencyError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        RunRepository(session).write_audit(
            tenant_id=principal.tenant_id,
            actor_id=principal.subject,
            action="CONTROL_PROPOSAL_APPROVED",
            resource_type="control",
            resource_id=approved.id,
            outcome="APPROVED",
            details={"proposal_id": proposal_id, "version": approved.version},
            request_id=request.state.request_id,
        )
        return approved


@router.post(
    "/agreements/{agreement_id}/compile-controls",
    response_model=AgreementCompilationExecution,
)
async def compile_agreement_controls(
    agreement_id: str,
    principal: Annotated[Principal, Depends(require_roles("analyst"))],
    request: Request,
) -> AgreementCompilationExecution:
    result, _ = await _run_agreement_compilation(
        agreement_id=agreement_id,
        principal=principal,
        request=request,
    )
    return result


@router.get("/controls/{logical_control_key}/versions", response_model=list[Control])
def control_versions(
    logical_control_key: str,
    principal: Annotated[Principal, Depends(require_roles("analyst", "approver", "viewer"))],
) -> list[Control]:
    if _seeded_demo_enabled(principal):
        versions = governance.versions(logical_control_key)
    elif get_settings().database_url:
        with session_scope(tenant_id=principal.tenant_id) as session:
            versions = RunRepository(session).control_versions(
                tenant_id=principal.tenant_id,
                logical_control_key=logical_control_key,
            )
    else:
        versions = []
    if not versions:
        raise HTTPException(status_code=404, detail="Control versions not found")
    return versions


@router.get("/controls/{logical_control_key}/effective", response_model=Control)
def effective_control(
    logical_control_key: str,
    at: date,
    principal: Annotated[Principal, Depends(require_roles("analyst", "approver", "viewer"))],
) -> Control:
    if _seeded_demo_enabled(principal):
        try:
            return governance.effective_control(logical_control_key, at)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
    if get_settings().database_url:
        with session_scope(tenant_id=principal.tenant_id) as session:
            try:
                control = RunRepository(session).effective_control(
                    tenant_id=principal.tenant_id,
                    logical_control_key=logical_control_key,
                    at=at,
                )
            except ValueError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            if control is not None:
                return control
    raise HTTPException(status_code=404, detail="No effective approved control was found")


@router.get("/runs/{run_id}/summary", response_model=RunSummary)
def run_summary(
    run_id: str,
    principal: Annotated[Principal, Depends(require_roles("analyst", "approver", "viewer"))],
) -> RunSummary:
    if run_id != DEMO_RUN_ID:
        if not get_settings().database_url:
            raise HTTPException(status_code=404, detail="Run not found")
        with session_scope(tenant_id=principal.tenant_id) as session:
            summary = RunRepository(session).live_run_summary(
                tenant_id=principal.tenant_id,
                run_id=run_id,
            )
            if summary is None:
                raise HTTPException(status_code=404, detail="Run not found")
            return summary
    _require_seeded_demo(principal)
    store.ensure_loaded()
    assert store.summary is not None
    return store.summary


@router.get("/runs/{run_id}/stages", response_model=list[RunStage])
def run_stages(
    run_id: str,
    principal: Annotated[Principal, Depends(require_roles("analyst", "approver", "viewer"))],
) -> list[RunStage]:
    if not get_settings().database_url:
        raise HTTPException(status_code=404, detail="Run not found")
    with session_scope(tenant_id=principal.tenant_id) as session:
        stages = RunRepository(session).list_run_stages(
            tenant_id=principal.tenant_id,
            run_id=run_id,
        )
        run = session.get(RunRecord, (principal.tenant_id, run_id))
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return stages


@router.get("/runs/{run_id}/operational-metrics", response_model=RunOperationalMetrics)
def run_operational_metrics(
    run_id: str,
    principal: Annotated[Principal, Depends(require_roles("analyst", "approver", "viewer"))],
) -> RunOperationalMetrics:
    if run_id == DEMO_RUN_ID:
        _require_seeded_demo(principal)
        store.ensure_loaded()
        assert store.summary is not None
        stages = []
        return RunOperationalMetrics(
            run_id=run_id,
            stage_count=len(stages),
            completed_stage_count=sum(item.status == "COMPLETE" for item in stages),
            failed_stage_count=sum(item.status == "FAILED" for item in stages),
            stage_durations_ms={item.stage: item.duration_ms or 0 for item in stages},
            total_processing_ms=store.summary.total_processing_ms,
            events_created=store.summary.event_count,
            evaluations_created=store.summary.control_evaluation_count,
        )
    if not get_settings().database_url:
        raise HTTPException(status_code=404, detail="Run not found")
    with session_scope(tenant_id=principal.tenant_id) as session:
        repository = RunRepository(session)
        summary = repository.live_run_summary(tenant_id=principal.tenant_id, run_id=run_id)
        if summary is None:
            raise HTTPException(status_code=404, detail="Run not found")
        stages = repository.list_run_stages(tenant_id=principal.tenant_id, run_id=run_id)
        return RunOperationalMetrics(
            run_id=run_id,
            stage_count=len(stages),
            completed_stage_count=sum(item.status == "COMPLETE" for item in stages),
            failed_stage_count=sum(item.status == "FAILED" for item in stages),
            stage_durations_ms={item.stage: item.duration_ms or 0 for item in stages},
            total_processing_ms=summary.total_processing_ms,
            events_created=summary.event_count,
            evaluations_created=summary.control_evaluation_count,
        )


@router.get("/runs", response_model=list[RunListItem])
def list_runs(
    principal: Annotated[Principal, Depends(require_roles("analyst", "approver", "viewer"))],
) -> list[RunListItem]:
    if not get_settings().database_url:
        _require_seeded_demo(principal)
        store.ensure_loaded()
        assert store.summary is not None
        return [
            RunListItem(
                id=store.summary.id,
                name=store.summary.name,
                status=store.summary.status,
                source_type=RunSourceType.DEMO,
                transaction_count=store.summary.transaction_count,
                event_count=store.summary.event_count,
                control_evaluation_count=store.summary.control_evaluation_count,
                completed_at=store.summary.completed_at,
            )
        ]
    with session_scope(tenant_id=principal.tenant_id) as session:
        return RunRepository(session).list_runs(tenant_id=principal.tenant_id)


@router.get("/runs/{run_id}/violations", response_model=list[Violation])
def violations(
    run_id: str,
    principal: Annotated[Principal, Depends(require_roles("analyst", "approver", "viewer"))],
) -> list[Violation]:
    if run_id != DEMO_RUN_ID:
        if not get_settings().database_url:
            raise HTTPException(status_code=404, detail="Run not found")
        with session_scope(tenant_id=principal.tenant_id) as session:
            return RunRepository(session).list_violations(
                tenant_id=principal.tenant_id,
                run_id=run_id,
            )
    _require_seeded_demo(principal)
    store.ensure_loaded()
    return store.violations


@router.get("/runs/{run_id}/root-causes", response_model=list[RootCause])
def root_causes(
    run_id: str,
    principal: Annotated[Principal, Depends(require_roles("analyst", "approver", "viewer"))],
) -> list[RootCause]:
    if run_id != DEMO_RUN_ID:
        if not get_settings().database_url:
            raise HTTPException(status_code=404, detail="Run not found")
        with session_scope(tenant_id=principal.tenant_id) as session:
            return RunRepository(session).list_root_causes(
                tenant_id=principal.tenant_id,
                run_id=run_id,
            )
    _require_seeded_demo(principal)
    store.ensure_loaded()
    return store.root_causes


@router.get(
    "/runs/{run_id}/control-coverage",
    response_model=ControlCoverageSummary,
)
def control_coverage(
    run_id: str,
    principal: Annotated[Principal, Depends(require_roles("analyst", "approver", "viewer"))],
) -> ControlCoverageSummary:
    if run_id != DEMO_RUN_ID:
        if not get_settings().database_url:
            raise HTTPException(status_code=404, detail="Run not found")
        with session_scope(tenant_id=principal.tenant_id) as session:
            result = live_payment_views.control_coverage(
                session,
                tenant_id=principal.tenant_id,
                run_id=run_id,
            )
            if session.get(RunRecord, (principal.tenant_id, run_id)) is None:
                raise HTTPException(status_code=404, detail="Run not found")
            return result
    _require_seeded_demo(principal)
    store.ensure_loaded()
    assert store.dataset is not None
    return governance.coverage(run_id, store.dataset.payments)


@router.get("/runs/{run_id}/cases", response_model=list[ExceptionCase])
def exception_cases(
    run_id: str,
    principal: Annotated[Principal, Depends(require_roles("analyst", "approver", "viewer"))],
) -> list[ExceptionCase]:
    if run_id != DEMO_RUN_ID:
        if not get_settings().database_url:
            raise HTTPException(status_code=404, detail="Run not found")
        with session_scope(tenant_id=principal.tenant_id) as session:
            return CaseRepository(session).list_for_run(
                tenant_id=principal.tenant_id,
                run_id=run_id,
            )
    _require_seeded_demo(principal)
    return store.list_cases()


@router.get("/runs/{run_id}/unresolved", response_model=list[UnresolvedMatch])
def unresolved_matches(
    run_id: str,
    principal: Annotated[Principal, Depends(require_roles("analyst", "approver", "viewer"))],
) -> list[UnresolvedMatch]:
    if run_id != DEMO_RUN_ID:
        if not get_settings().database_url:
            raise HTTPException(status_code=404, detail="Run not found")
        with session_scope(tenant_id=principal.tenant_id) as session:
            return RunRepository(session).list_unresolved_matches(
                tenant_id=principal.tenant_id,
                run_id=run_id,
            )
    _require_seeded_demo(principal)
    return store.unresolved_matches()


@router.get("/cases/{case_id}", response_model=ExceptionCase)
def exception_case(
    case_id: str,
    principal: Annotated[Principal, Depends(require_roles("analyst", "approver", "viewer"))],
) -> ExceptionCase:
    if get_settings().database_url:
        with session_scope(tenant_id=principal.tenant_id) as session:
            persisted = CaseRepository(session).get(
                tenant_id=principal.tenant_id,
                case_id=case_id,
            )
            if persisted is not None:
                return persisted
    _require_seeded_demo(principal)
    try:
        return store.get_case(case_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Case not found") from exc


def _transition_case(
    case_id: str,
    target: ExceptionCaseStatus,
    payload: CaseTransitionRequest,
    principal: Principal,
    request: Request,
) -> ExceptionCase:
    if get_settings().database_url:
        with session_scope(tenant_id=principal.tenant_id) as session:
            repository = CaseRepository(session)
            persisted = repository.get(tenant_id=principal.tenant_id, case_id=case_id)
            if persisted is not None:
                if payload.expected_version is None:
                    raise HTTPException(
                        status_code=428,
                        detail="expected_version is required for a durable case transition",
                    )
                try:
                    updated = repository.transition(
                        tenant_id=principal.tenant_id,
                        case_id=case_id,
                        target=target,
                        actor_id=principal.subject,
                        note=payload.note,
                        expected_version=payload.expected_version,
                    )
                except CaseConcurrencyError as exc:
                    raise HTTPException(status_code=409, detail=str(exc)) from exc
                except ValueError as exc:
                    raise HTTPException(status_code=409, detail=str(exc)) from exc
                RunRepository(session).write_audit(
                    tenant_id=principal.tenant_id,
                    actor_id=principal.subject,
                    action=f"CASE_{target.value}",
                    resource_type="case",
                    resource_id=case_id,
                    outcome="SUCCESS",
                    details={
                        "from_status": persisted.status.value,
                        "version": updated.version,
                    },
                    request_id=request.state.request_id,
                )
                return updated
    _require_seeded_demo(principal)
    try:
        case = store.transition_case(case_id, target, payload.note, actor=principal.subject)
        if get_settings().database_url:
            with session_scope(tenant_id=principal.tenant_id) as session:
                RunRepository(session).write_audit(
                    tenant_id=principal.tenant_id,
                    actor_id=principal.subject,
                    action=f"CASE_{target.value}",
                    resource_type="case",
                    resource_id=case_id,
                    outcome="SUCCESS",
                    details={"from_status": case.audit_trail[-1].from_status},
                    request_id=request.state.request_id,
                )
        return case
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Case not found") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/cases/{case_id}/verify", response_model=ExceptionCase)
def verify_case(
    case_id: str,
    request: CaseTransitionRequest,
    principal: Annotated[Principal, Depends(require_roles("analyst"))],
    http_request: Request,
) -> ExceptionCase:
    return _transition_case(case_id, ExceptionCaseStatus.VERIFIED, request, principal, http_request)


@router.post("/cases/{case_id}/escalate", response_model=ExceptionCase)
def escalate_case(
    case_id: str,
    request: CaseTransitionRequest,
    principal: Annotated[Principal, Depends(require_roles("analyst"))],
    http_request: Request,
) -> ExceptionCase:
    return _transition_case(
        case_id, ExceptionCaseStatus.ESCALATED, request, principal, http_request
    )


@router.post("/cases/{case_id}/resolve", response_model=ExceptionCase)
def resolve_case(
    case_id: str,
    request: CaseTransitionRequest,
    principal: Annotated[Principal, Depends(require_roles("analyst"))],
    http_request: Request,
) -> ExceptionCase:
    return _transition_case(case_id, ExceptionCaseStatus.RESOLVED, request, principal, http_request)


@router.get(
    "/runs/{run_id}/payments/{payment_id}/expected-vs-actual",
    response_model=ExpectedActualResponse,
)
def expected_vs_actual(
    run_id: str,
    payment_id: str,
    principal: Annotated[Principal, Depends(require_roles("analyst", "approver", "viewer"))],
) -> ExpectedActualResponse:
    if run_id != DEMO_RUN_ID:
        if not get_settings().database_url:
            raise HTTPException(status_code=404, detail="Run not found")
        with session_scope(tenant_id=principal.tenant_id) as session:
            result = live_payment_views.expected_actual(
                session,
                tenant_id=principal.tenant_id,
                run_id=run_id,
                payment_id=payment_id,
            )
            if result is None:
                raise HTTPException(status_code=404, detail="Payment not found")
            return result
    _require_seeded_demo(principal)
    try:
        return store.expected_actual(payment_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Payment not found") from exc


@router.get("/runs/{run_id}/payments/{payment_id}/graph", response_model=PaymentGraph)
def payment_graph(
    run_id: str,
    payment_id: str,
    principal: Annotated[Principal, Depends(require_roles("analyst", "approver", "viewer"))],
) -> PaymentGraph:
    if run_id != DEMO_RUN_ID:
        if not get_settings().database_url:
            raise HTTPException(status_code=404, detail="Run not found")
        with session_scope(tenant_id=principal.tenant_id) as session:
            result = live_payment_views.graph(
                session,
                tenant_id=principal.tenant_id,
                run_id=run_id,
                payment_id=payment_id,
            )
            if result is None:
                raise HTTPException(status_code=404, detail="Payment not found")
            return result
    _require_seeded_demo(principal)
    try:
        return store.graph(payment_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Payment not found") from exc


@router.get(
    "/runs/{run_id}/payments/{payment_id}/lineage",
    response_model=ViolationLineageResponse,
)
def payment_lineage(
    run_id: str,
    payment_id: str,
    principal: Annotated[Principal, Depends(require_roles("analyst", "approver", "viewer"))],
) -> ViolationLineageResponse:
    if run_id != DEMO_RUN_ID:
        if not get_settings().database_url:
            raise HTTPException(status_code=404, detail="Run not found")
        with session_scope(tenant_id=principal.tenant_id) as session:
            result = live_payment_views.lineage(
                session,
                tenant_id=principal.tenant_id,
                run_id=run_id,
                payment_id=payment_id,
            )
            if result is None:
                raise HTTPException(status_code=404, detail="Payment not found")
            return result
    _require_seeded_demo(principal)
    try:
        return store.lineage(payment_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Payment not found") from exc


@router.get(
    "/runs/{run_id}/payments/{payment_id}/counterfactual",
    response_model=CounterfactualSettlement,
)
def payment_counterfactual(
    run_id: str,
    payment_id: str,
    principal: Annotated[Principal, Depends(require_roles("analyst", "approver", "viewer"))],
) -> CounterfactualSettlement:
    if run_id != DEMO_RUN_ID:
        if not get_settings().database_url:
            raise HTTPException(status_code=404, detail="Run not found")
        with session_scope(tenant_id=principal.tenant_id) as session:
            result = live_payment_views.counterfactual(
                session,
                tenant_id=principal.tenant_id,
                run_id=run_id,
                payment_id=payment_id,
            )
            if result is None:
                raise HTTPException(status_code=404, detail="Payment not found")
            return result
    _require_seeded_demo(principal)
    try:
        return store.counterfactual(payment_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Payment not found") from exc


@router.post(
    "/runs/{run_id}/temporal-replay",
    response_model=TemporalReplayResponse,
)
def temporal_replay(
    run_id: str,
    payload: TemporalReplayRequest,
    principal: Annotated[Principal, Depends(require_roles("analyst", "approver", "viewer"))],
) -> TemporalReplayResponse:
    """Replay MDR expectations under an approved effective-dated control version."""

    if run_id == DEMO_RUN_ID:
        _require_seeded_demo(principal)
        store.ensure_loaded()
        assert store.dataset is not None
        controls = CONTROLS
        payments = store.dataset.payments
    elif get_settings().database_url:
        with session_scope(tenant_id=principal.tenant_id) as session:
            repository = RunRepository(session)
            if session.get(RunRecord, (principal.tenant_id, run_id)) is None:
                raise HTTPException(status_code=404, detail="Run not found")
            controls = repository.list_controls(
                tenant_id=principal.tenant_id,
                approved_only=True,
            )
            payments = live_payment_views.payment_lifecycles(
                session,
                tenant_id=principal.tenant_id,
                run_id=run_id,
            )
    else:
        raise HTTPException(status_code=404, detail="Run not found")

    candidate = next((control for control in controls if control.id == payload.control_id), None)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Control version not found")
    if candidate.status != "APPROVED":
        raise HTTPException(status_code=409, detail="Replay requires an approved control version")
    if candidate.logical_control_key != "DOMESTIC_CARD_MDR":
        raise HTTPException(
            status_code=422, detail="Replay currently supports MDR control versions"
        )
    try:
        replay_rate = Decimal(str(candidate.parameters.get("rate")))
        replay_tolerance = Decimal(str(candidate.parameters.get("tolerance", "0.01")))
    except (InvalidOperation, TypeError) as exc:
        raise HTTPException(
            status_code=422, detail="Control rate and tolerance are invalid"
        ) from exc
    if not replay_rate.is_finite() or not replay_tolerance.is_finite():
        raise HTTPException(status_code=422, detail="Control rate and tolerance must be finite")

    baseline_expected = Decimal("0")
    replay_expected = Decimal("0")
    baseline_violations = 0
    replay_violations = 0
    evidence: list[dict[str, Any]] = []
    monthly: dict[str, dict[str, Any]] = {}
    for payment in payments:
        if payment.payment_method.lower() != "card":
            continue
        baseline_control = next(
            (
                control
                for control in controls
                if control.logical_control_key == "DOMESTIC_CARD_MDR"
                and control.status == "APPROVED"
                and control.effective_from <= payment.captured_at.date()
                and (
                    control.effective_to is None
                    or payment.captured_at.date() <= control.effective_to
                )
            ),
            None,
        )
        if baseline_control is None:
            continue
        baseline_rate = Decimal(str(baseline_control.parameters.get("rate")))
        baseline_tolerance = Decimal(str(baseline_control.parameters.get("tolerance", "0.01")))
        expected_before = expected_fee(payment.amount, baseline_rate)
        expected_after = expected_fee(payment.amount, replay_rate)
        actual_fee = payment.actual_fee
        baseline_expected += expected_before
        replay_expected += expected_after
        baseline_bad = abs(actual_fee - expected_before) > baseline_tolerance
        replay_bad = abs(actual_fee - expected_after) > replay_tolerance
        baseline_violations += int(baseline_bad)
        replay_violations += int(replay_bad)
        period = payment.captured_at.date().strftime("%Y-%m")
        bucket = monthly.setdefault(
            period,
            {
                "period": period,
                "transaction_count": 0,
                "baseline_expected_amount": Decimal("0"),
                "replay_expected_amount": Decimal("0"),
            },
        )
        bucket["transaction_count"] += 1
        bucket["baseline_expected_amount"] += expected_before
        bucket["replay_expected_amount"] += expected_after
        if len(evidence) < 100 and expected_before != expected_after:
            evidence.append(
                {
                    "payment_id": payment.payment_id,
                    "captured_at": payment.captured_at.isoformat(),
                    "actual_fee": actual_fee,
                    "baseline_expected_fee": expected_before,
                    "replay_expected_fee": expected_after,
                    "difference": money(expected_after - expected_before),
                    "baseline_control_id": baseline_control.id,
                    "replay_control_id": candidate.id,
                }
            )
    return TemporalReplayResponse(
        run_id=run_id,
        control_id=candidate.id,
        control_version=candidate.version,
        logical_control_key=candidate.logical_control_key,
        transaction_count=sum(
            1 for payment in payments if payment.payment_method.lower() == "card"
        ),
        baseline_expected_amount=money(baseline_expected),
        replay_expected_amount=money(replay_expected),
        difference_amount=money(replay_expected - baseline_expected),
        baseline_violation_count=baseline_violations,
        replay_violation_count=replay_violations,
        evidence=evidence,
        monthly_series=[
            {
                **bucket,
                "baseline_expected_amount": money(bucket["baseline_expected_amount"]),
                "replay_expected_amount": money(bucket["replay_expected_amount"]),
                "difference_amount": money(
                    bucket["replay_expected_amount"] - bucket["baseline_expected_amount"]
                ),
            }
            for bucket in (monthly[key] for key in sorted(monthly))
        ],
    )


@router.post(
    "/runs/{run_id}/evidence-export",
    response_model=EvidenceExportResponse,
    status_code=201,
)
async def export_run_evidence(
    run_id: str,
    principal: Annotated[Principal, Depends(require_roles("analyst", "approver"))],
    request: Request,
) -> EvidenceExportResponse:
    """Write a deterministic, private JSON evidence pack to Supabase Storage."""

    settings = get_settings()
    storage = SupabaseStorage()
    if not settings.database_url or not storage.configured:
        raise HTTPException(
            status_code=503,
            detail="Evidence export requires PostgreSQL and private Supabase Storage",
        )
    created_at = datetime.now(timezone.utc)
    with session_scope(tenant_id=principal.tenant_id) as session:
        repository = RunRepository(session)
        summary = repository.live_run_summary(tenant_id=principal.tenant_id, run_id=run_id)
        if summary is None:
            raise HTTPException(status_code=404, detail="Run not found")
        payload = {
            "schema": "sl3dge.evidence-pack.v1",
            "generated_at": created_at.isoformat(),
            "run": summary.model_dump(mode="json"),
            "stages": [
                item.model_dump(mode="json")
                for item in repository.list_run_stages(
                    tenant_id=principal.tenant_id,
                    run_id=run_id,
                )
            ],
            "violations": [
                item.model_dump(mode="json")
                for item in repository.list_violations(
                    tenant_id=principal.tenant_id,
                    run_id=run_id,
                )
            ],
            "root_causes": [
                item.model_dump(mode="json")
                for item in repository.list_root_causes(
                    tenant_id=principal.tenant_id,
                    run_id=run_id,
                )
            ],
            "cases": [
                item.model_dump(mode="json")
                for item in CaseRepository(session).list_for_run(
                    tenant_id=principal.tenant_id,
                    run_id=run_id,
                )
            ],
        }
        content = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        digest = sha256(content).hexdigest()
        artifact_id = f"ART_EVIDENCE_{digest[:20].upper()}"
        object_path = f"tenants/{principal.tenant_id}/evidence/{run_id}/{artifact_id}.json"
        try:
            stored = await storage.upload(
                object_path,
                content,
                content_type="application/json",
                overwrite=True,
            )
        except Exception as exc:
            logger.exception("Evidence export storage failed run_id=%s", run_id)
            raise HTTPException(
                status_code=502, detail="Evidence pack could not be stored"
            ) from exc
        ArtifactService(storage, session).record(
            stored=stored,
            artifact_id=artifact_id,
            kind="EVIDENCE_PACK_JSON",
            tenant_id=principal.tenant_id,
            run_id=run_id,
        )
        repository.write_audit(
            tenant_id=principal.tenant_id,
            actor_id=principal.subject,
            action="EVIDENCE_PACK_EXPORTED",
            resource_type="run",
            resource_id=run_id,
            outcome="COMPLETE",
            details={
                "artifact_id": artifact_id,
                "sha256": stored.sha256,
                "byte_size": stored.byte_size,
            },
            request_id=request.state.request_id,
        )
    return EvidenceExportResponse(
        artifact_id=artifact_id,
        run_id=run_id,
        bucket=stored.bucket,
        object_path=stored.object_path,
        content_type=stored.content_type,
        byte_size=stored.byte_size,
        sha256=stored.sha256,
        created_at=created_at,
    )


@router.get("/root-causes/{root_cause_id}", response_model=RootCause)
def root_cause(
    root_cause_id: str,
    principal: Annotated[Principal, Depends(require_roles("analyst", "approver", "viewer"))],
) -> RootCause:
    if get_settings().database_url:
        with session_scope(tenant_id=principal.tenant_id) as session:
            persisted = RunRepository(session).get_root_cause(
                tenant_id=principal.tenant_id,
                root_cause_id=root_cause_id,
            )
            if persisted is not None:
                return persisted
    _require_seeded_demo(principal)
    try:
        return store.get_root_cause(root_cause_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Root cause not found") from exc


@router.post("/root-causes/{root_cause_id}/generate-hypothesis", response_model=HypothesisResponse)
def generate_hypothesis(
    root_cause_id: str,
    _principal: Annotated[Principal, Depends(require_roles("analyst"))],
) -> HypothesisResponse:
    _require_seeded_demo(_principal)
    try:
        return store.generate_hypothesis(root_cause_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Root cause not found") from exc


@router.post(
    "/root-causes/{root_cause_id}/verify-hypothesis", response_model=HypothesisVerification
)
def verify_hypothesis(
    root_cause_id: str,
    _principal: Annotated[Principal, Depends(require_roles("analyst"))],
) -> HypothesisVerification:
    _require_seeded_demo(_principal)
    try:
        return store.verify_hypothesis(root_cause_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Root cause not found") from exc


@router.post(
    "/root-causes/{root_cause_id}/investigate",
    response_model=InvestigationExecution,
)
async def investigate_root_cause(
    root_cause_id: str,
    principal: Annotated[Principal, Depends(require_roles("analyst"))],
    request: Request,
) -> InvestigationExecution:
    root: RootCause | None = None
    related: list[Violation] = []
    case: ExceptionCase | None = None
    evidence: list[AgentEvidence] = []
    razorpay_context: dict[str, str] = {}
    contract_controls: list[dict[str, str]] = []
    source_type = RunSourceType.DEMO.value
    run_id = DEMO_RUN_ID

    if (
        get_settings().environment in {"development", "test"}
        and principal.tenant_id == DEMO_TENANT_ID
    ):
        try:
            root = store.get_root_cause(root_cause_id)
        except KeyError:
            root = None
    if root is not None:
        source_type = RunSourceType.DEMO.value
        related = [item for item in store.violations if item.root_cause_id == root.id]
        if related:
            effective = governance.effective_control(
                "DOMESTIC_CARD_MDR", related[0].occurred_at.date()
            )
            razorpay_context = {}
            contract_controls = [
                {
                    "control_id": effective.id,
                    "version": str(effective.version),
                    "rate": str(effective.parameters.get("rate", "")),
                    "tolerance": str(effective.parameters.get("tolerance", "")),
                    "effective_from": effective.effective_from.isoformat(),
                    "effective_to": (
                        effective.effective_to.isoformat() if effective.effective_to else ""
                    ),
                    "source_clause": effective.source_clause,
                }
            ]
        case = next(
            (
                item
                for item in store.list_cases()
                if any(
                    violation_id in item.violation_ids
                    for violation_id in {violation.id for violation in related}
                )
            ),
            None,
        )
        if case:
            evidence = [
                AgentEvidence(
                    id=item.id,
                    kind=item.kind,
                    source=item.source_id,
                    summary=item.summary,
                    verified=item.verified,
                    attributes={},
                )
                for item in case.evidence
            ]
    elif get_settings().database_url:
        with session_scope(tenant_id=principal.tenant_id) as session:
            repository = RunRepository(session)
            root = repository.get_root_cause(
                tenant_id=principal.tenant_id,
                root_cause_id=root_cause_id,
            )
            if root is not None:
                summary = repository.live_run_summary(
                    tenant_id=principal.tenant_id,
                    run_id=repository.run_id_for_root(
                        tenant_id=principal.tenant_id,
                        root_cause_id=root_cause_id,
                    )
                    or "",
                )
                source_type = (
                    summary.source_type.value
                    if summary is not None
                    else RunSourceType.CSV_UPLOAD.value
                )
                run_id = (
                    repository.run_id_for_root(
                        tenant_id=principal.tenant_id,
                        root_cause_id=root_cause_id,
                    )
                    or ""
                )
                related = repository.violations_for_root(
                    tenant_id=principal.tenant_id,
                    root_cause_id=root_cause_id,
                )
                context = (
                    repository.mdr_investigation_context(
                        tenant_id=principal.tenant_id,
                        run_id=run_id,
                        payment_id=related[0].payment_id,
                    )
                    if related
                    else None
                )
                if context:
                    razorpay_context = (
                        context["razorpay_context"]
                        if source_type == RunSourceType.RAZORPAY.value
                        else {}
                    )
                    contract_controls = context["contract_controls"]
                    evidence = [AgentEvidence.model_validate(item) for item in context["evidence"]]
                case = CaseRepository(session).get_for_root(
                    tenant_id=principal.tenant_id,
                    root_cause_id=root_cause_id,
                )
    if root is None:
        raise HTTPException(status_code=404, detail="Root cause not found")
    if not related:
        raise HTTPException(status_code=409, detail="Root cause has no deterministic violations")
    if not contract_controls:
        raise HTTPException(status_code=409, detail="No effective deterministic control was found")
    runtime = build_ai_runtime()
    async with agent_checkpointer() as checkpointer:
        controller = InvestigationController(
            provider=runtime.provider_client,
            max_attempts=get_settings().agent_max_attempts,
            checkpointer=checkpointer,
        )
        result = await controller.run(
            tenant_id=principal.tenant_id,
            run_id=run_id,
            source_type=source_type,
            root_cause_id=root.id,
            violation_ids=[item.id for item in related],
            evidence=evidence,
            razorpay_context=razorpay_context,
            contract_controls=contract_controls,
            case_id=case.id if case else None,
        )
    if not get_settings().database_url:
        _require_seeded_demo(principal)
        investigation_runs[result.execution_id] = result
    if get_settings().database_url:
        with session_scope(tenant_id=principal.tenant_id) as session:
            AgentExecutionRepository(session).save(
                tenant_id=principal.tenant_id,
                execution_id=result.execution_id,
                workflow=result.workflow,
                resource_type="root_cause",
                resource_id=root.id,
                status=result.status,
                result=result.model_dump(mode="json"),
                started_at=result.started_at,
                completed_at=result.completed_at,
            )
            if result.status == "PROVEN" and result.case_id:
                case_evidence = [
                    CaseEvidence(
                        id=item.id,
                        kind=item.kind,
                        title=item.kind.replace("_", " ").title(),
                        summary=item.summary,
                        source_id=item.source,
                        verified=item.verified,
                    )
                    for item in evidence
                ]
                CaseRepository(session).create_from_investigation(
                    tenant_id=principal.tenant_id,
                    case_id=result.case_id,
                    root_cause=root,
                    violations=related,
                    evidence=case_evidence,
                    actor_id=principal.subject,
                )
            RunRepository(session).write_audit(
                tenant_id=principal.tenant_id,
                actor_id=principal.subject,
                action="AGENT_INVESTIGATION_COMPLETED",
                resource_type="root_cause",
                resource_id=root.id,
                outcome=result.status,
                details={
                    "execution_id": result.execution_id,
                    "attempt_count": result.attempt_count,
                    "ai_configured": result.ai_configured,
                    "trace_nodes": [step.node for step in result.trace],
                },
                request_id=request.state.request_id,
            )
    return result


@router.get(
    "/agent/investigations/{execution_id}",
    response_model=InvestigationExecution,
)
def get_investigation(
    execution_id: str,
    principal: Annotated[Principal, Depends(require_roles("analyst", "approver", "viewer"))],
) -> InvestigationExecution:
    if get_settings().database_url:
        with session_scope(tenant_id=principal.tenant_id) as session:
            record = AgentExecutionRepository(session).get(
                tenant_id=principal.tenant_id,
                execution_id=execution_id,
            )
            if record is None or record.workflow != "ROOT_CAUSE_INVESTIGATION":
                raise HTTPException(status_code=404, detail="Investigation not found")
            return InvestigationExecution.model_validate(record.result)
    _require_seeded_demo(principal)
    result = investigation_runs.get(execution_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Investigation not found")
    return result


@router.post("/runs/{run_id}/mutation-tests", response_model=MutationTestSummary)
def create_mutation_test(
    run_id: str,
    _principal: Annotated[Principal, Depends(require_roles("analyst"))],
    request: Request,
) -> MutationTestSummary:
    global mutation_test
    if run_id == DEMO_RUN_ID:
        _require_seeded_demo(_principal)
        store.ensure_loaded()
        assert store.dataset is not None
        candidate = _control("CTRL_UNSUPPORTED_FEE_CANDIDATE")
        mutation_test = execute_mutation_test(
            run_id,
            store.dataset.payments,
            unsupported_fee_control=candidate.status == "APPROVED",
        )
    elif get_settings().database_url:
        with session_scope(tenant_id=_principal.tenant_id) as session:
            repository = RunRepository(session)
            run = session.get(RunRecord, (_principal.tenant_id, run_id))
            if run is None:
                raise HTTPException(status_code=404, detail="Run not found")
            payments = live_payment_views.payment_lifecycles(
                session,
                tenant_id=_principal.tenant_id,
                run_id=run_id,
            )
            controls = repository.list_controls(
                tenant_id=_principal.tenant_id,
                approved_only=True,
            )
            unsupported_fee_control = any(
                control.control_type == "UNSUPPORTED_FEE" for control in controls
            )
            mutation_test = execute_mutation_test(
                run_id,
                payments,
                unsupported_fee_control=unsupported_fee_control,
            )
            repository.save_mutation_test(mutation_test, tenant_id=_principal.tenant_id)
            repository.write_audit(
                tenant_id=_principal.tenant_id,
                actor_id=_principal.subject,
                action="MUTATION_TEST_EXECUTED",
                resource_type="mutation_test",
                resource_id=mutation_test.id,
                outcome="COMPLETE",
                details={
                    "detected": mutation_test.detected_count,
                    "missed": mutation_test.missed_count,
                },
                request_id=request.state.request_id,
            )
    else:
        raise HTTPException(status_code=404, detail="Run not found")
    if get_settings().database_url and run_id == DEMO_RUN_ID:
        with session_scope(tenant_id=_principal.tenant_id) as session:
            repository = RunRepository(session)
            repository.save_mutation_test(mutation_test, tenant_id=_principal.tenant_id)
            repository.write_audit(
                tenant_id=_principal.tenant_id,
                actor_id=_principal.subject,
                action="MUTATION_TEST_EXECUTED",
                resource_type="mutation_test",
                resource_id=mutation_test.id,
                outcome="COMPLETE",
                details={
                    "detected": mutation_test.detected_count,
                    "missed": mutation_test.missed_count,
                },
                request_id=request.state.request_id,
            )
    return mutation_test


@router.post(
    "/runs/{run_id}/blind-spots/remediate",
    response_model=BlindSpotRemediationExecution,
)
async def remediate_blind_spots(
    run_id: str,
    principal: Annotated[Principal, Depends(require_roles("analyst"))],
    request: Request,
) -> BlindSpotRemediationExecution:
    if run_id != DEMO_RUN_ID:
        raise HTTPException(status_code=404, detail="Run not found")
    _require_seeded_demo(principal)
    store.ensure_loaded()
    assert store.dataset is not None
    before = execute_mutation_test(run_id, store.dataset.payments)
    after = execute_mutation_test(run_id, store.dataset.payments, unsupported_fee_control=True)
    missed = [item for item in before.results if not item.detected]
    unsupported = [item for item in missed if item.mutation_type.value == "UNSUPPORTED_FEE"]
    if not unsupported:
        raise HTTPException(status_code=409, detail="No unsupported-fee blind spot exists")
    control = governance.control("CTRL_UNSUPPORTED_FEE_CANDIDATE")
    runtime = build_ai_runtime()
    async with agent_checkpointer() as checkpointer:
        result = await BlindSpotRemediationController(
            runtime.provider_client, checkpointer=checkpointer
        ).run(
            tenant_id=principal.tenant_id,
            run_id=run_id,
            mutation_ids=[item.id for item in unsupported],
            gap={
                "relationship": "SETTLEMENT -> OTHER_DEDUCTION",
                "clause_id": control.clause_id,
                "blind_spot_reason": unsupported[0].blind_spot_reason.value,
            },
            clauses=[
                clause.model_dump(mode="json")
                for clause in AGREEMENT.clauses
                if clause.id == control.clause_id
            ],
            seed_candidate=TypedControlCandidate(
                candidate_id=control.id,
                logical_control_key=control.logical_control_key,
                control_type=control.control_type.value,
                name=control.name,
                clause_id=control.clause_id or "",
                version=control.version,
                effective_from=control.effective_from,
                effective_to=control.effective_to,
                supersedes_candidate_id=control.supersedes_control_id,
                parameters=control.parameters,
                conditions=control.conditions,
                rationale="The cited clause prohibits every unlisted settlement deduction.",
                confidence="0.93",
            ),
            historical_backtest={
                "false_positive_count": 0,
                "canonical_data_unchanged": True,
            },
            mutation_backtest={
                "before_detected": before.detected_count,
                "after_detected": after.detected_count,
                "mutation_count": after.mutation_count,
            },
            comparison={
                "detection_rate_delta": str(
                    after.mutation_detection_rate - before.mutation_detection_rate
                ),
                "false_positive_delta": (after.false_positive_count - before.false_positive_count),
            },
        )
    if get_settings().database_url:
        with session_scope(tenant_id=principal.tenant_id) as session:
            AgentExecutionRepository(session).save(
                tenant_id=principal.tenant_id,
                execution_id=result.execution_id,
                workflow=result.workflow,
                resource_type="run",
                resource_id=run_id,
                status=result.status,
                result=result.model_dump(mode="json"),
                started_at=result.started_at,
                completed_at=result.completed_at,
            )
            RunRepository(session).write_audit(
                tenant_id=principal.tenant_id,
                actor_id=principal.subject,
                action="BLIND_SPOT_REMEDIATION_PROPOSED",
                resource_type="control",
                resource_id=control.id,
                outcome=result.status,
                details={
                    "execution_id": result.execution_id,
                    "mutation_ids": result.mutation_ids,
                    "schema_valid": result.schema_valid,
                },
                request_id=request.state.request_id,
            )
    return result


@router.get("/mutation-tests/{test_id}", response_model=MutationTestSummary)
def get_mutation_test(
    test_id: str,
    principal: Annotated[Principal, Depends(require_roles("analyst", "approver", "viewer"))],
) -> MutationTestSummary:
    _require_seeded_demo(principal)
    if test_id != MUTATION_TEST_ID or mutation_test is None:
        raise HTTPException(status_code=404, detail="Mutation test not found")
    return mutation_test


@router.post("/controls/{control_id}/backtest", response_model=ControlBacktest)
def backtest_control(
    control_id: str,
    _principal: Annotated[Principal, Depends(require_roles("analyst"))],
    request: Request,
    run_id: str | None = None,
) -> ControlBacktest:
    effective_run_id = run_id or DEMO_RUN_ID
    control: Control | None = None
    payments: list[PaymentLifecycle]
    if effective_run_id == DEMO_RUN_ID:
        _require_seeded_demo(_principal)
        control = _control(control_id)
        store.ensure_loaded()
        assert store.dataset is not None
        payments = store.dataset.payments
    elif get_settings().database_url:
        with session_scope(tenant_id=_principal.tenant_id) as session:
            repository = RunRepository(session)
            if session.get(RunRecord, (_principal.tenant_id, effective_run_id)) is None:
                raise HTTPException(status_code=404, detail="Run not found")
            control = repository.get_control(
                tenant_id=_principal.tenant_id,
                control_id=control_id,
            )
            payments = live_payment_views.payment_lifecycles(
                session,
                tenant_id=_principal.tenant_id,
                run_id=effective_run_id,
            )
    else:
        raise HTTPException(status_code=404, detail="Run not found")
    if control is None:
        raise HTTPException(status_code=404, detail="Control not found")
    if control.control_type != ControlType.UNSUPPORTED_FEE:
        raise HTTPException(status_code=422, detail="This control type has no mutation fixture")
    before = execute_mutation_test(effective_run_id, payments)
    after = execute_mutation_test(
        effective_run_id,
        payments,
        unsupported_fee_control=True,
    )
    before_missed = {result.id for result in before.results if not result.detected}
    newly_detected = [
        result.id for result in after.results if result.detected and result.id in before_missed
    ]
    result = ControlBacktest(
        control_id=control.id,
        status="COMPLETE",
        candidate_status=control.status,
        historical_false_positives=0,
        before={
            "detected_count": before.detected_count,
            "mutation_count": before.mutation_count,
            "mutation_detection_rate": before.mutation_detection_rate,
            "false_positive_count": before.false_positive_count,
        },
        after={
            "detected_count": after.detected_count,
            "mutation_count": after.mutation_count,
            "mutation_detection_rate": after.mutation_detection_rate,
            "false_positive_count": after.false_positive_count,
        },
        detection_rate_delta=after.mutation_detection_rate - before.mutation_detection_rate,
        false_positive_delta=after.false_positive_count - before.false_positive_count,
        newly_detected_mutation_ids=newly_detected,
        canonical_data_unchanged=(
            before.canonical_data_unchanged and after.canonical_data_unchanged
        ),
    )
    if effective_run_id == DEMO_RUN_ID:
        governance.record_backtest(control.id, actor=_principal.subject)
    if get_settings().database_url:
        with session_scope(tenant_id=_principal.tenant_id) as session:
            RunRepository(session).write_audit(
                tenant_id=_principal.tenant_id,
                actor_id=_principal.subject,
                action="CONTROL_BACKTESTED",
                resource_type="control",
                resource_id=control.id,
                outcome="COMPLETE",
                details={
                    "before_detected": before.detected_count,
                    "after_detected": after.detected_count,
                    "false_positive_delta": result.false_positive_delta,
                },
                request_id=request.state.request_id,
            )
    return result


@router.post("/controls/{control_id}/approve", response_model=Control)
def approve_control(
    control_id: str,
    _principal: Annotated[Principal, Depends(require_roles("approver"))],
    request: Request,
) -> Control:
    _require_seeded_demo(_principal)
    _control(control_id)
    try:
        approved = governance.approve(
            control_id,
            actor=_principal.subject,
            enforce_maker_checker=get_settings().environment == "production",
        )
        if get_settings().database_url:
            with session_scope(tenant_id=_principal.tenant_id) as session:
                RunRepository(session).write_audit(
                    tenant_id=_principal.tenant_id,
                    actor_id=_principal.subject,
                    action="CONTROL_APPROVED",
                    resource_type="control",
                    resource_id=approved.id,
                    outcome="APPROVED",
                    details={"version": approved.version},
                    request_id=request.state.request_id,
                )
        return approved
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/integrations/razorpay/status", response_model=RazorpayConnectionStatus)
def razorpay_status(
    principal: Annotated[Principal, Depends(require_roles("analyst", "approver", "viewer"))],
) -> RazorpayConnectionStatus:
    return connection_status(tenant_id=principal.tenant_id)


@router.post("/integrations/razorpay/sync", response_model=RazorpaySyncSummary)
async def razorpay_sync(
    request: RazorpaySyncRequest,
    principal: Annotated[Principal, Depends(require_roles("analyst"))],
) -> RazorpaySyncSummary:
    if get_settings().environment == "production":
        raise HTTPException(
            status_code=409,
            detail="Foreground synchronization is disabled in production; submit a sync job",
        )
    try:
        return await sync_razorpay(
            request,
            run_id="RUN_RAZORPAY_LIVE",
            tenant_id=principal.tenant_id,
        )
    except RazorpayNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post(
    "/integrations/razorpay/sync-jobs",
    response_model=JobSubmission,
    status_code=202,
)
def submit_razorpay_sync_job(
    sync_request: RazorpaySyncRequest,
    request: Request,
    principal: Annotated[Principal, Depends(require_roles("analyst"))],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> JobSubmission:
    if not re.fullmatch(r"[A-Za-z0-9._:-]{8,200}", idempotency_key):
        raise HTTPException(
            status_code=422,
            detail="Idempotency-Key must be 8-200 safe ASCII characters",
        )
    if not get_settings().database_url:
        raise HTTPException(
            status_code=503,
            detail="Durable jobs require DATABASE_URL; use foreground sync only in development",
        )
    request_fingerprint = sha256(idempotency_key.encode("ascii")).hexdigest()[:12].upper()
    run_id = (
        f"RUN_RAZORPAY_{sync_request.year}{sync_request.month:02d}"
        f"{sync_request.day or 0:02d}_{request_fingerprint}"
    )
    with session_scope(tenant_id=principal.tenant_id) as session:
        repository = JobRepository(session)
        record, created = repository.enqueue(
            tenant_id=principal.tenant_id,
            job_type="RAZORPAY_SYNC",
            idempotency_key=idempotency_key,
            payload={
                **sync_request.model_dump(mode="json"),
                "run_id": run_id,
                "requested_by": principal.subject,
            },
            run_id=run_id,
            max_attempts=3,
        )
        RunRepository(session).write_audit(
            tenant_id=principal.tenant_id,
            actor_id=principal.subject,
            action="RAZORPAY_SYNC_JOB_SUBMITTED",
            resource_type="background_job",
            resource_id=record.id,
            outcome="QUEUED" if created else "IDEMPOTENT_REPLAY",
            details={"run_id": run_id, "created": created},
            request_id=request.state.request_id,
        )
        response = _job_response(record)
    return JobSubmission(created=created, job=response)


@router.get("/jobs/{job_id}", response_model=BackgroundJob)
def get_background_job(
    job_id: str,
    principal: Annotated[Principal, Depends(require_roles("analyst", "approver", "viewer"))],
) -> BackgroundJob:
    if not get_settings().database_url:
        raise HTTPException(status_code=503, detail="Durable jobs require DATABASE_URL")
    with session_scope(tenant_id=principal.tenant_id) as session:
        record = JobRepository(session).get(tenant_id=principal.tenant_id, job_id=job_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Job not found")
        return _job_response(record)


@router.get(
    "/integrations/razorpay/mcp-evidence-capability",
    response_model=McpEvidenceCapability,
)
def razorpay_mcp_evidence_capability() -> McpEvidenceCapability:
    return mcp_evidence_capability()
