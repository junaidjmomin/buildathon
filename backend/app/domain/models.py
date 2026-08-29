from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ApiModel(BaseModel):
    pass


class EvaluationStatus(str, Enum):
    PASS = "PASS"
    VIOLATION = "VIOLATION"
    WARNING = "WARNING"
    UNRESOLVED = "UNRESOLVED"


class RunSourceType(str, Enum):
    DEMO = "DEMO"
    CSV_UPLOAD = "CSV_UPLOAD"
    RAZORPAY = "RAZORPAY"


class LineageType(str, Enum):
    PRIMARY = "PRIMARY"
    DOWNSTREAM = "DOWNSTREAM"


class ControlType(str, Enum):
    MDR_RATE = "MDR_RATE"
    GST_ON_FEE = "GST_ON_FEE"
    SETTLEMENT_SLA = "SETTLEMENT_SLA"
    REFUND_INTEGRITY = "REFUND_INTEGRITY"
    SETTLEMENT_ARITHMETIC = "SETTLEMENT_ARITHMETIC"
    LIFECYCLE_VALIDITY = "LIFECYCLE_VALIDITY"
    UNSUPPORTED_FEE = "UNSUPPORTED_FEE"


class Control(ApiModel):
    id: str
    name: str
    control_type: ControlType
    expected: str
    scope: str
    source: str
    source_clause: str
    status: str = "APPROVED"
    agreement_id: str = "AGR_NOVACART_2026"
    clause_id: str | None = None
    logical_control_key: str = ""
    version: int = 1
    effective_from: date = date(2026, 1, 1)
    effective_to: date | None = None
    supersedes_control_id: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    conditions: list[str] = Field(default_factory=list)
    extraction_method: str = "HUMAN_APPROVED"
    approved_at: datetime | None = None


class AgreementClause(ApiModel):
    id: str
    reference: str
    page: int
    heading: str
    text: str
    effective_from: date
    effective_to: date | None = None
    source_type: str = "PDF_TEXT_EXTRACTION"
    created_by: str | None = None


class AgreementClauseCreate(ApiModel):
    reference: str = Field(min_length=1, max_length=120)
    heading: str = Field(min_length=1, max_length=240)
    text: str = Field(min_length=1, max_length=50_000)
    effective_from: date | None = None
    effective_to: date | None = None


class Agreement(ApiModel):
    id: str
    merchant: str
    title: str
    status: str
    effective_from: date
    effective_to: date | None = None
    source_type: str
    content_hash: str
    clauses: list[AgreementClause]


class ControlProposal(ApiModel):
    id: str
    agreement_id: str
    clause_id: str
    control_id: str
    status: str
    confidence: Decimal
    rationale: str
    source_excerpt: str
    extraction_method: str
    proposed_control: Control
    version: int = 1
    verification_status: str = "NOT_RUN"
    verification_result: dict[str, Any] | None = None
    verified_by: str | None = None
    verified_at: datetime | None = None
    approved_by: str | None = None
    approved_at: datetime | None = None


class ControlProposalApprovalRequest(ApiModel):
    expected_version: int = Field(ge=1)


class ControlProposalVerification(ApiModel):
    proposal_id: str
    control_id: str
    status: str
    version: int
    checks: list[dict[str, Any]]
    mutation_probe_count: int
    detected_mutation_count: int
    input_fingerprint: str
    verified_by: str
    verified_at: datetime


class CoverageStatus(str, Enum):
    GOVERNED = "GOVERNED"
    PARTIALLY_GOVERNED = "PARTIALLY_GOVERNED"
    UNGOVERNED = "UNGOVERNED"


class ControlCoverageItem(ApiModel):
    """One runtime relationship type with its actual material event edges.

    Only relationship types with at least one actual material edge in the run
    belong here; detectability gaps proven by mutation testing are exposed as
    ``MutationBlindSpot`` entries instead and never counted as ungoverned
    runtime edges.
    """

    id: str
    relationship: str
    description: str
    material_edge_count: int
    governed_edge_count: int
    status: CoverageStatus
    control_ids: list[str]
    blind_spot: str | None = None


class MutationBlindSpot(ApiModel):
    """A failure mode the approved control suite cannot detect.

    Derived from mutation testing (or from the absence of an approved control
    for a known failure mode), never from runtime edge counts: a relationship
    type with zero actual edges is a blind spot statement about the control
    suite, not an ungoverned runtime edge.
    """

    id: str
    relationship: str
    failure_mode: str
    description: str
    reason: str


class ControlCoverageSummary(ApiModel):
    run_id: str
    total_material_edges: int
    governed_edges: int
    partially_governed_edges: int
    ungoverned_edges: int
    coverage_percentage: Decimal
    items: list[ControlCoverageItem]
    mutation_derived_blind_spots: list[MutationBlindSpot] = Field(default_factory=list)


class ExceptionCaseStatus(str, Enum):
    OPEN = "OPEN"
    VERIFIED = "VERIFIED"
    ESCALATED = "ESCALATED"
    RESOLVED = "RESOLVED"


class CaseAuditEntry(ApiModel):
    from_status: ExceptionCaseStatus | None
    to_status: ExceptionCaseStatus
    actor: str
    note: str
    occurred_at: datetime


class CaseEvidence(ApiModel):
    id: str
    kind: str
    title: str
    summary: str
    source_id: str
    verified: bool


class ExceptionCase(ApiModel):
    id: str
    run_id: str
    root_cause_id: str | None = None
    title: str
    payment_id: str
    primary_violation_id: str
    violation_ids: list[str]
    status: ExceptionCaseStatus
    verified_impact: Decimal
    evidence: list[CaseEvidence]
    audit_trail: list[CaseAuditEntry]
    created_at: datetime
    updated_at: datetime
    resolution_note: str | None = None
    version: int = 1


class CaseTransitionRequest(ApiModel):
    note: str = ""
    expected_version: int | None = Field(default=None, ge=1)


class UnresolvedMatch(ApiModel):
    id: str
    payment_id: str
    status: EvaluationStatus = EvaluationStatus.UNRESOLVED
    amount: Decimal
    settlement_id: str
    missing_evidence: str
    candidate_bank_references: list[str]
    safe_conclusion: str


class McpEvidenceCapability(ApiModel):
    enabled: bool
    authoritative: bool = False
    provider: str
    allowed_tools: list[str]
    prohibited_tool_classes: list[str]
    result_policy: str


class PaymentLifecycle(ApiModel):
    payment_id: str
    order_id: str
    settlement_id: str
    bank_txn_id: str | None
    amount: Decimal
    payment_method: str
    card_network: str
    card_scope: str
    captured_at: datetime
    actual_fee: Decimal
    actual_tax: Decimal
    refund_id: str | None = None
    refund_amount: Decimal = Decimal("0")
    refund_deduction: Decimal = Decimal("0")
    unsupported_fee: Decimal = Decimal("0")
    settled_at: datetime
    actual_net: Decimal
    bank_credit: Decimal | None
    unresolved_case_id: str | None = None
    status: str = "captured"
    chargeback_fee: Decimal = Decimal("0")
    chargeback_fee_deductions: int = 0


class ExpectedActualRow(ApiModel):
    label: str
    expected: Decimal
    actual: Decimal | None
    status: EvaluationStatus
    difference: Decimal


class Evidence(ApiModel):
    title: str
    control: str
    calculation: str
    expected: Decimal | None = None
    actual: Decimal | None = None
    difference: Decimal | None = None
    source: str
    source_clause: str
    evaluation_id: str | None = None
    control_version: int | None = None
    source_snapshot_ids: list[str] = Field(default_factory=list)


class ExpectedActualResponse(ApiModel):
    payment_id: str
    descriptor: str
    amount: Decimal
    status: EvaluationStatus
    rows: list[ExpectedActualRow]
    verified_leakage: Decimal
    gateway_net: Decimal
    bank_credit: Decimal | None
    expected_net: Decimal
    evidence: list[Evidence]
    applied_control_id: str
    applied_control_version: int
    applied_control_effective_period: str


class Violation(ApiModel):
    id: str
    payment_id: str
    category: str
    control_type: ControlType
    expected: str
    actual: str
    difference: Decimal
    financial_impact: Decimal
    confidence: Decimal = Decimal("1")
    status: EvaluationStatus = EvaluationStatus.VIOLATION
    root_cause_id: str | None = None
    lineage_type: LineageType = LineageType.PRIMARY
    root_violation_id: str | None = None
    parent_violation_id: str | None = None
    causal_evidence: dict[str, Any] = Field(default_factory=dict)
    occurred_at: datetime
    #: Canonical violation taxonomy, derived from control semantics (never from
    #: identifiers or dataset-specific values). Empty for legacy records.
    violation_type: str = ""
    #: Native entity of the finding: PAYMENT, SETTLEMENT, RELATIONSHIP, ...
    target_type: str = "PAYMENT"


class RootCause(ApiModel):
    id: str
    title: str
    category: str
    affected_count: int
    verified_impact: Decimal
    expected_value: str
    observed_value: str
    first_seen: datetime
    last_seen: datetime
    hypothesis: str | None = None
    verification_status: str = "NOT_TESTED"
    verification_evidence: dict[str, Any] | None = None
    primary_violation_count: int = 0
    downstream_effect_count: int = 0
    direct_impact: Decimal = Decimal("0")
    downstream_impact: Decimal = Decimal("0")
    total_attributable_impact: Decimal = Decimal("0")


class StatusBreakdown(ApiModel):
    passed: int
    violation: int
    warning: int
    unresolved: int


class ConfusionMatrix(ApiModel):
    true_positive: int
    false_positive: int
    true_negative: int
    false_negative: int


class MetricsAvailability(ApiModel):
    ground_truth: bool = False
    precision: bool = False
    recall: bool = False
    false_positive_rate: bool = False
    control_coverage: bool = False


class RunSummary(ApiModel):
    id: str
    name: str
    status: str
    source_type: RunSourceType = RunSourceType.DEMO
    transaction_count: int
    event_count: int
    relationship_count: int
    control_evaluation_count: int
    breakdown: StatusBreakdown
    pass_count: int = 0
    violation_count: int = 0
    warning_count: int = 0
    # Control-evaluation outcomes and event-relationship outcomes are distinct
    # quantities and are never folded into one number:
    #   pass + violation + warning + unresolved_control == control_evaluation_count
    #   unresolved_relationship counts UNRESOLVED_MATCH event relationships.
    unresolved_control_count: int = 0
    unresolved_relationship_count: int = 0
    precision: Decimal
    recall: Decimal
    false_positive_rate: Decimal
    verified_leakage: Decimal
    cash_delayed: Decimal
    # Legacy alias of unresolved_control_count, kept for existing consumers.
    unresolved_count: int
    unresolved_match_count: int = 0
    processing_ms: int
    deterministic_processing_ms: int = 0
    ai_processing_ms: int | None = None
    evaluations_per_second: int
    persistence_ms: int = 0
    total_processing_ms: int = 0
    primary_violation_count: int = 0
    downstream_violation_count: int = 0
    control_coverage: Decimal | None = None
    provider_used: str | None = None
    model_used: str | None = None
    mcp_used: bool = False
    confusion_matrix: ConfusionMatrix
    completed_at: datetime
    ground_truth_available: bool = True
    metrics_scope: str = "SEEDED_GROUND_TRUTH"
    # Source-neutral, user-facing explanation of why precision and recall are
    # or are not scored for this run.
    metrics_note: str = ""
    metrics_available: MetricsAvailability = Field(default_factory=MetricsAvailability)


class RunListItem(ApiModel):
    id: str
    name: str
    status: str
    source_type: RunSourceType
    transaction_count: int
    event_count: int
    control_evaluation_count: int
    completed_at: datetime | None = None


class RunStage(ApiModel):
    """One persisted pipeline stage of a control run, upload through finalize."""

    stage: str
    status: str
    stage_index: int
    started_at: datetime
    finished_at: datetime | None = None
    duration_ms: int | None = None
    detail: dict[str, Any] = Field(default_factory=dict)


class RunOperationalMetrics(ApiModel):
    run_id: str
    stage_count: int
    completed_stage_count: int
    failed_stage_count: int
    stage_durations_ms: dict[str, int]
    total_processing_ms: int
    events_created: int
    evaluations_created: int


class GraphNode(ApiModel):
    id: str
    kind: str
    label: str
    amount: Decimal
    status: EvaluationStatus = EvaluationStatus.PASS
    detail: str | None = None


class GraphEdge(ApiModel):
    id: str
    source: str
    target: str
    relationship: str
    confidence: Decimal
    method: str


class PaymentGraph(ApiModel):
    payment_id: str
    nodes: list[GraphNode]
    edges: list[GraphEdge]


class DemoLoadResponse(ApiModel):
    run_id: str
    name: str
    counts: dict[str, int]
    known_demo_ids: dict[str, str]
    persistence_status: str = "IN_MEMORY"


class InfrastructureCapability(ApiModel):
    database_configured: bool
    database_mode: str
    storage_configured: bool
    storage_bucket: str
    storage_policy: str


class SourceRowError(ApiModel):
    """A single invalid row reported without rejecting the whole file."""

    row_number: int
    column: str
    message: str


class SourceUploadResponse(ApiModel):
    upload_id: str | None = None
    filename: str
    source_type: str = "UNRESOLVED"
    classification_confidence: Decimal = Decimal("0")
    classification_evidence: list[str] = Field(default_factory=list)
    status: str = "ACCEPTED"
    error: str | None = None
    row_count: int = 0
    columns: list[str] = Field(default_factory=list)
    decimal_values_checked: int = 0
    row_errors: list[SourceRowError] = Field(default_factory=list)
    row_error_count: int = 0
    schema_drift: bool = False
    drift_columns: list[str] = Field(default_factory=list)
    storage_status: str = "NOT_STORED"
    object_path: str | None = None


class SourceUploadBatchResponse(ApiModel):
    file_count: int
    accepted_count: int
    rejected_count: int
    files: list[SourceUploadResponse]


class SourceRunResponse(ApiModel):
    run_id: str
    name: str
    status: str
    source_types: list[str]
    files_ingested: int
    events_created: int
    edges_created: int
    unresolved_matches: int
    control_evaluations_created: int
    violations_created: int
    persistence_status: str
    stages: list[RunStage] = Field(default_factory=list)


class AiCapability(ApiModel):
    provider: str
    model: str
    configured: bool
    deterministic_pipeline_available: bool = True
    fallback_policy: str


class HypothesisResponse(ApiModel):
    root_cause_id: str
    hypothesis: str
    status: str


class HypothesisVerification(ApiModel):
    root_cause_id: str
    status: str
    classification: str
    checks: list[dict[str, str]]
    conclusion: str


class MutationType(str, Enum):
    MDR_RATE_INCREASE = "MDR_RATE_INCREASE"
    GST_BASE_CORRUPTION = "GST_BASE_CORRUPTION"
    DUPLICATE_REFUND_DEDUCTION = "DUPLICATE_REFUND_DEDUCTION"
    SETTLEMENT_DELAY = "SETTLEMENT_DELAY"
    UNSUPPORTED_FEE = "UNSUPPORTED_FEE"
    FAILED_PAYMENT_SETTLED = "FAILED_PAYMENT_SETTLED"
    REFUND_EXCEEDS_PAYMENT = "REFUND_EXCEEDS_PAYMENT"
    DUPLICATE_CHARGEBACK_FEE = "DUPLICATE_CHARGEBACK_FEE"
    PAYMENT_METHOD_RECLASSIFICATION = "PAYMENT_METHOD_RECLASSIFICATION"


class BlindSpotReason(str, Enum):
    NO_APPLICABLE_CONTROL = "NO_APPLICABLE_CONTROL"
    CONTROL_LOGIC_FAILED = "CONTROL_LOGIC_FAILED"
    UNGOVERNED_LIFECYCLE_EDGE = "UNGOVERNED_LIFECYCLE_EDGE"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class MutationResult(ApiModel):
    id: str
    mutation_type: MutationType
    target_event_id: str
    description: str
    detected: bool
    expected_control_type: ControlType
    detected_by_control_types: list[ControlType]
    blind_spot_reason: BlindSpotReason | None = None


class MutationCoverage(ApiModel):
    mutation_type: MutationType
    injected: int
    detected: int
    detection_rate: Decimal


class MutationTestSummary(ApiModel):
    id: str
    source_run_id: str
    status: str
    mutation_count: int
    detected_count: int
    missed_count: int
    mutation_detection_rate: Decimal
    false_positive_count: int
    blind_spot_count: int
    canonical_data_unchanged: bool
    coverage: list[MutationCoverage]
    results: list[MutationResult]
    created_at: datetime


class BacktestMetrics(ApiModel):
    detected_count: int
    mutation_count: int
    mutation_detection_rate: Decimal
    false_positive_count: int


class ControlBacktest(ApiModel):
    control_id: str
    status: str
    candidate_status: str
    historical_false_positives: int
    before: BacktestMetrics
    after: BacktestMetrics
    detection_rate_delta: Decimal
    false_positive_delta: int
    newly_detected_mutation_ids: list[str]
    canonical_data_unchanged: bool


class TemporalReplayRequest(ApiModel):
    control_id: str = Field(min_length=1, max_length=160)


class TemporalReplayResponse(ApiModel):
    run_id: str
    control_id: str
    control_version: int
    logical_control_key: str
    transaction_count: int
    baseline_expected_amount: Decimal
    replay_expected_amount: Decimal
    difference_amount: Decimal
    baseline_violation_count: int
    replay_violation_count: int
    evidence: list[dict[str, Any]]
    monthly_series: list[dict[str, Any]]


class EvidenceExportResponse(ApiModel):
    artifact_id: str
    run_id: str
    bucket: str
    object_path: str
    content_type: str
    byte_size: int
    sha256: str
    created_at: datetime


class ViolationLineageNode(ApiModel):
    id: str
    category: str
    lineage_type: LineageType
    parent_violation_id: str | None
    root_violation_id: str
    expected: Decimal
    actual: Decimal
    difference: Decimal
    financial_impact: Decimal
    causal_evidence: dict[str, Any] | str


class ViolationLineageResponse(ApiModel):
    payment_id: str
    primary_violation_count: int
    downstream_effect_count: int
    nodes: list[ViolationLineageNode]


class CashFlow(ApiModel):
    gross: Decimal
    mdr: Decimal
    gst: Decimal
    refunds: Decimal
    other_fees: Decimal
    net: Decimal


class CounterfactualDriver(ApiModel):
    type: str
    amount: Decimal


class CounterfactualSettlement(ApiModel):
    payment_id: str
    actual: CashFlow
    expected: CashFlow
    difference: Decimal
    drivers: list[CounterfactualDriver]


class FinancialEvent(ApiModel):
    id: str
    run_id: str
    source: str
    external_id: str
    event_type: str
    amount: Decimal
    currency: str
    timestamp: datetime
    status: str | None = None
    raw_payload: dict[str, Any]
    normalized_payload: dict[str, Any]


class CanonicalEventEdge(ApiModel):
    id: str
    run_id: str
    from_event_id: str
    to_event_id: str
    relationship: str
    confidence: Decimal
    method: str
    evidence: dict[str, Any]


class RazorpayConnectionStatus(ApiModel):
    configured: bool
    mode: str
    connected: bool
    last_sync_status: str
    last_synced_at: datetime | None = None


class RazorpaySyncRequest(ApiModel):
    year: int
    month: int
    day: int | None = None


class RazorpaySyncSummary(ApiModel):
    sync_id: str
    status: str
    payments_imported: int
    refunds_imported: int
    settlements_imported: int
    reconciliation_records_imported: int
    events_created: int
    edges_created: int
    unresolved_references: int = 0
    control_evaluations_created: int = 0
    violations_created: int = 0
    synced_at: datetime
    persistence_status: str = "IN_MEMORY"


class BackgroundJob(ApiModel):
    id: str
    run_id: str | None = None
    job_type: str
    status: str
    attempt_count: int
    max_attempts: int
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None


class JobSubmission(ApiModel):
    created: bool
    job: BackgroundJob
