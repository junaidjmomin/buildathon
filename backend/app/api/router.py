from __future__ import annotations

import re
from datetime import date
from pathlib import PurePath
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Header, HTTPException, Request, UploadFile

from app.agents.checkpoint import agent_checkpointer
from app.agents.control_workflows import AgreementControlCompiler, BlindSpotRemediationController
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
from app.domain.models import (
    Agreement,
    AiCapability,
    BackgroundJob,
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
    JobSubmission,
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
from app.persistence.orm import BackgroundJobRecord
from app.persistence.repository import (
    AgentExecutionRepository,
    JobRepository,
    RunRepository,
)
from app.security.auth import Principal, get_current_principal, require_roles
from app.services.demo import DEMO_RUN_ID, store
from app.services.governance import AGREEMENT, CONTROLS, governance
from app.storage.service import ArtifactService
from app.storage.supabase import SupabaseStorage

router = APIRouter(prefix="/api/v1", dependencies=[Depends(get_current_principal)])
mutation_test: MutationTestSummary | None = None
investigation_runs: dict[str, InvestigationExecution] = {}


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


@router.post(
    "/agreements/{agreement_id}/compile-controls",
    response_model=AgreementCompilationExecution,
)
async def compile_agreement_controls(
    agreement_id: str,
    principal: Annotated[Principal, Depends(require_roles("analyst"))],
    request: Request,
) -> AgreementCompilationExecution:
    try:
        agreement_record = governance.agreement(agreement_id)
        proposals = governance.proposals(agreement_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Agreement not found") from exc
    seeds = [
        TypedControlCandidate(
            candidate_id=proposal.control_id,
            logical_control_key=proposal.proposed_control.logical_control_key,
            control_type=proposal.proposed_control.control_type.value,
            name=proposal.proposed_control.name,
            clause_id=proposal.clause_id,
            version=proposal.proposed_control.version,
            effective_from=proposal.proposed_control.effective_from,
            effective_to=proposal.proposed_control.effective_to,
            supersedes_candidate_id=proposal.proposed_control.supersedes_control_id,
            parameters=proposal.proposed_control.parameters,
            conditions=proposal.proposed_control.conditions,
            rationale=proposal.rationale,
            confidence=proposal.confidence,
        )
        for proposal in proposals
    ]
    runtime = build_ai_runtime()
    async with agent_checkpointer() as checkpointer:
        result = await AgreementControlCompiler(
            runtime.provider_client, checkpointer=checkpointer
        ).run(
            tenant_id=principal.tenant_id,
            agreement_id=agreement_id,
            clauses=[clause.model_dump(mode="json") for clause in agreement_record.clauses],
            seed_candidates=seeds,
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
            RunRepository(session).write_audit(
                tenant_id=principal.tenant_id,
                actor_id=principal.subject,
                action="AGREEMENT_CONTROL_COMPILATION_COMPLETED",
                resource_type="agreement",
                resource_id=agreement_id,
                outcome=result.status,
                details={
                    "execution_id": result.execution_id,
                    "proposal_count": len(result.proposals),
                    "conflict_count": result.conflict_count,
                },
                request_id=request.state.request_id,
            )
    return result


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


@router.post(
    "/root-causes/{root_cause_id}/investigate",
    response_model=InvestigationExecution,
)
async def investigate_root_cause(
    root_cause_id: str,
    principal: Annotated[Principal, Depends(require_roles("analyst"))],
    request: Request,
) -> InvestigationExecution:
    try:
        root = store.get_root_cause(root_cause_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Root cause not found") from exc
    related = [item for item in store.violations if item.root_cause_id == root.id]
    if not related:
        raise HTTPException(status_code=409, detail="Root cause has no deterministic violations")
    sample = store.expected_actual(related[0].payment_id)
    mdr_row = next((row for row in sample.rows if row.label == "MDR"), None)
    if mdr_row is None or mdr_row.actual is None or sample.amount == 0:
        observed_rate = ""
        difference_amount = ""
    else:
        observed_rate = str(mdr_row.actual / sample.amount)
        difference_amount = str(mdr_row.difference)
    effective = governance.effective_control("DOMESTIC_CARD_MDR", related[0].occurred_at.date())
    case = next(
        (
            item
            for item in store.list_cases()
            if any(violation_id in item.violation_ids for violation_id in {v.id for v in related})
        ),
        None,
    )
    evidence = (
        [
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
        if case
        else []
    )
    runtime = build_ai_runtime()
    async with agent_checkpointer() as checkpointer:
        controller = InvestigationController(
            provider=runtime.provider_client,
            max_attempts=get_settings().agent_max_attempts,
            checkpointer=checkpointer,
        )
        result = await controller.run(
            tenant_id=principal.tenant_id,
            run_id=DEMO_RUN_ID,
            root_cause_id=root.id,
            violation_ids=[item.id for item in related],
            evidence=evidence,
            razorpay_context={
                "source": "canonical Razorpay evidence",
                "observed_rate": observed_rate,
                "difference_amount": difference_amount,
                "observed_value": root.observed_value,
            },
            contract_controls=[
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
            ],
            case_id=case.id if case else None,
        )
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
            RunRepository(session).save_mutation_test(mutation_test, tenant_id=_principal.tenant_id)
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
    run_id = f"RUN_RAZORPAY_{sync_request.year}{sync_request.month:02d}{sync_request.day or 0:02d}"
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
