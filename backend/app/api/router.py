from __future__ import annotations

from datetime import date
from pathlib import PurePath
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile

from app.ai.provider import build_ai_runtime
from app.core.config import get_settings
from app.domain.models import (
    Agreement,
    AiCapability,
    CaseTransitionRequest,
    Control,
    ControlBacktest,
    ControlCoverageSummary,
    ControlProposal,
    CounterfactualSettlement,
    DemoLoadResponse,
    ExceptionCase,
    ExceptionCaseStatus,
    ExpectedActualResponse,
    HypothesisResponse,
    HypothesisVerification,
    InfrastructureCapability,
    McpEvidenceCapability,
    MutationTestSummary,
    PaymentGraph,
    RazorpayConnectionStatus,
    RazorpaySyncRequest,
    RazorpaySyncSummary,
    RootCause,
    RunSummary,
    SourceUploadResponse,
    UnresolvedMatch,
    Violation,
    ViolationLineageResponse,
)
from app.ingestion.csv import parse_source_csv
from app.integrations.razorpay.client import RazorpayNotConfiguredError
from app.integrations.razorpay.mcp_evidence import capability as mcp_evidence_capability
from app.integrations.razorpay.sync import connection_status, sync_razorpay
from app.mutations.engine import MUTATION_TEST_ID, execute_mutation_test
from app.persistence.database import session_scope
from app.persistence.repository import RunRepository
from app.security.auth import Principal, get_current_principal, require_roles
from app.services.demo import DEMO_RUN_ID, store
from app.services.governance import AGREEMENT, CONTROLS, governance
from app.storage.service import ArtifactService
from app.storage.supabase import SupabaseStorage

router = APIRouter(prefix="/api/v1", dependencies=[Depends(get_current_principal)])
mutation_test: MutationTestSummary | None = None


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


@router.post("/sources/upload", response_model=SourceUploadResponse)
async def upload_source(
    file: Annotated[UploadFile, File()],
    principal: Annotated[Principal, Depends(require_roles("analyst"))],
    request: Request,
) -> SourceUploadResponse:
    filename = PurePath(file.filename or "source.csv").name
    if not filename.lower().endswith(".csv"):
        raise HTTPException(status_code=422, detail="Only CSV source files are accepted")
    settings = get_settings()
    content = await file.read(settings.max_upload_bytes + 1)
    if len(content) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="CSV source file exceeds the configured limit")
    parsed = parse_source_csv(content)
    upload_id = f"UPLOAD_{uuid4().hex[:12].upper()}"
    object_path = f"tenants/{principal.tenant_id}/uploads/{upload_id}.csv"
    storage = SupabaseStorage(settings)
    storage_status = "VALIDATED_ONLY"
    persisted_path: str | None = None
    if storage.configured and settings.database_url:
        with session_scope(tenant_id=principal.tenant_id) as session:
            stored = await ArtifactService(storage, session).store(
                artifact_id=upload_id,
                kind="SOURCE_CSV",
                object_path=object_path,
                content=content,
                content_type="text/csv",
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
                details={"filename": filename, "row_count": parsed.row_count},
                request_id=request.state.request_id,
            )
        storage_status = "PRIVATE_STORAGE"
        persisted_path = stored.object_path
    return SourceUploadResponse(
        upload_id=upload_id,
        filename=filename,
        row_count=parsed.row_count,
        columns=parsed.columns,
        decimal_values_checked=parsed.decimal_values_checked,
        storage_status=storage_status,
        object_path=persisted_path,
    )


@router.post("/demo/load", response_model=DemoLoadResponse)
def load_demo(
    _principal: Annotated[Principal, Depends(require_roles("analyst"))],
) -> DemoLoadResponse:
    if get_settings().environment == "production":
        raise HTTPException(status_code=404, detail="Demo loading is disabled in production")
    return store.load()


@router.get("/controls", response_model=list[Control])
def list_controls() -> list[Control]:
    return CONTROLS


def _control(control_id: str) -> Control:
    try:
        return governance.control(control_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Control not found") from exc


@router.get("/agreements", response_model=list[Agreement])
def agreements() -> list[Agreement]:
    return [AGREEMENT]


@router.get("/agreements/{agreement_id}", response_model=Agreement)
def agreement(agreement_id: str) -> Agreement:
    try:
        return governance.agreement(agreement_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Agreement not found") from exc


@router.post(
    "/agreements/{agreement_id}/extract-controls",
    response_model=list[ControlProposal],
)
def extract_agreement_controls(
    agreement_id: str,
    _principal: Annotated[Principal, Depends(require_roles("analyst"))],
) -> list[ControlProposal]:
    try:
        return governance.proposals(agreement_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Agreement not found") from exc


@router.get(
    "/agreements/{agreement_id}/control-proposals",
    response_model=list[ControlProposal],
)
def agreement_control_proposals(agreement_id: str) -> list[ControlProposal]:
    try:
        return governance.proposals(agreement_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Agreement not found") from exc


@router.get("/controls/{logical_control_key}/versions", response_model=list[Control])
def control_versions(logical_control_key: str) -> list[Control]:
    versions = governance.versions(logical_control_key)
    if not versions:
        raise HTTPException(status_code=404, detail="Control versions not found")
    return versions


@router.get("/controls/{logical_control_key}/effective", response_model=Control)
def effective_control(logical_control_key: str, at: date) -> Control:
    try:
        return governance.effective_control(logical_control_key, at)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/runs/{run_id}/summary", response_model=RunSummary)
def run_summary(run_id: str) -> RunSummary:
    if run_id != DEMO_RUN_ID:
        raise HTTPException(status_code=404, detail="Run not found")
    store.ensure_loaded()
    assert store.summary is not None
    return store.summary


@router.get("/runs/{run_id}/violations", response_model=list[Violation])
def violations(run_id: str) -> list[Violation]:
    if run_id != DEMO_RUN_ID:
        raise HTTPException(status_code=404, detail="Run not found")
    store.ensure_loaded()
    return store.violations


@router.get("/runs/{run_id}/root-causes", response_model=list[RootCause])
def root_causes(run_id: str) -> list[RootCause]:
    if run_id != DEMO_RUN_ID:
        raise HTTPException(status_code=404, detail="Run not found")
    store.ensure_loaded()
    return store.root_causes


@router.get(
    "/runs/{run_id}/control-coverage",
    response_model=ControlCoverageSummary,
)
def control_coverage(run_id: str) -> ControlCoverageSummary:
    if run_id != DEMO_RUN_ID:
        raise HTTPException(status_code=404, detail="Run not found")
    store.ensure_loaded()
    assert store.dataset is not None
    return governance.coverage(run_id, store.dataset.payments)


@router.get("/runs/{run_id}/cases", response_model=list[ExceptionCase])
def exception_cases(run_id: str) -> list[ExceptionCase]:
    if run_id != DEMO_RUN_ID:
        raise HTTPException(status_code=404, detail="Run not found")
    return store.list_cases()


@router.get("/runs/{run_id}/unresolved", response_model=list[UnresolvedMatch])
def unresolved_matches(run_id: str) -> list[UnresolvedMatch]:
    if run_id != DEMO_RUN_ID:
        raise HTTPException(status_code=404, detail="Run not found")
    return store.unresolved_matches()


@router.get("/cases/{case_id}", response_model=ExceptionCase)
def exception_case(case_id: str) -> ExceptionCase:
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
    return _transition_case(
        case_id, ExceptionCaseStatus.VERIFIED, request, principal, http_request
    )


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
    return _transition_case(
        case_id, ExceptionCaseStatus.RESOLVED, request, principal, http_request
    )


@router.get(
    "/runs/{run_id}/payments/{payment_id}/expected-vs-actual",
    response_model=ExpectedActualResponse,
)
def expected_vs_actual(run_id: str, payment_id: str) -> ExpectedActualResponse:
    if run_id != DEMO_RUN_ID:
        raise HTTPException(status_code=404, detail="Run not found")
    try:
        return store.expected_actual(payment_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Payment not found") from exc


@router.get("/runs/{run_id}/payments/{payment_id}/graph", response_model=PaymentGraph)
def payment_graph(run_id: str, payment_id: str) -> PaymentGraph:
    if run_id != DEMO_RUN_ID:
        raise HTTPException(status_code=404, detail="Run not found")
    try:
        return store.graph(payment_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Payment not found") from exc


@router.get(
    "/runs/{run_id}/payments/{payment_id}/lineage",
    response_model=ViolationLineageResponse,
)
def payment_lineage(run_id: str, payment_id: str) -> ViolationLineageResponse:
    if run_id != DEMO_RUN_ID:
        raise HTTPException(status_code=404, detail="Run not found")
    try:
        return store.lineage(payment_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Payment not found") from exc


@router.get(
    "/runs/{run_id}/payments/{payment_id}/counterfactual",
    response_model=CounterfactualSettlement,
)
def payment_counterfactual(run_id: str, payment_id: str) -> CounterfactualSettlement:
    if run_id != DEMO_RUN_ID:
        raise HTTPException(status_code=404, detail="Run not found")
    try:
        return store.counterfactual(payment_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Payment not found") from exc


@router.get("/root-causes/{root_cause_id}", response_model=RootCause)
def root_cause(root_cause_id: str) -> RootCause:
    try:
        return store.get_root_cause(root_cause_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Root cause not found") from exc


@router.post("/root-causes/{root_cause_id}/generate-hypothesis", response_model=HypothesisResponse)
def generate_hypothesis(
    root_cause_id: str,
    _principal: Annotated[Principal, Depends(require_roles("analyst"))],
) -> HypothesisResponse:
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
    try:
        return store.verify_hypothesis(root_cause_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Root cause not found") from exc


@router.post("/runs/{run_id}/mutation-tests", response_model=MutationTestSummary)
def create_mutation_test(
    run_id: str,
    _principal: Annotated[Principal, Depends(require_roles("analyst"))],
    request: Request,
) -> MutationTestSummary:
    global mutation_test
    if run_id != DEMO_RUN_ID:
        raise HTTPException(status_code=404, detail="Run not found")
    store.ensure_loaded()
    assert store.dataset is not None
    candidate = _control("CTRL_UNSUPPORTED_FEE_CANDIDATE")
    mutation_test = execute_mutation_test(
        run_id,
        store.dataset.payments,
        unsupported_fee_control=candidate.status == "APPROVED",
    )
    if get_settings().database_url:
        with session_scope(tenant_id=_principal.tenant_id) as session:
            RunRepository(session).save_mutation_test(
                mutation_test, tenant_id=_principal.tenant_id
            )
            RunRepository(session).write_audit(
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


@router.get("/mutation-tests/{test_id}", response_model=MutationTestSummary)
def get_mutation_test(test_id: str) -> MutationTestSummary:
    if test_id != MUTATION_TEST_ID or mutation_test is None:
        raise HTTPException(status_code=404, detail="Mutation test not found")
    return mutation_test


@router.post("/controls/{control_id}/backtest", response_model=ControlBacktest)
def backtest_control(
    control_id: str,
    _principal: Annotated[Principal, Depends(require_roles("analyst"))],
    request: Request,
) -> ControlBacktest:
    control = _control(control_id)
    if control.id != "CTRL_UNSUPPORTED_FEE_CANDIDATE":
        raise HTTPException(status_code=422, detail="No backtest fixture for this control")
    store.ensure_loaded()
    assert store.dataset is not None
    before = execute_mutation_test(DEMO_RUN_ID, store.dataset.payments)
    after = execute_mutation_test(DEMO_RUN_ID, store.dataset.payments, unsupported_fee_control=True)
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
def razorpay_status() -> RazorpayConnectionStatus:
    return connection_status()


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


@router.get(
    "/integrations/razorpay/mcp-evidence-capability",
    response_model=McpEvidenceCapability,
)
def razorpay_mcp_evidence_capability() -> McpEvidenceCapability:
    return mcp_evidence_capability()
