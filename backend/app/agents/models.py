from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AgentModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class HypothesisKind(str, Enum):
    CONTRACT_CHANGE = "CONTRACT_CHANGE"
    GATEWAY_RATE_DEVIATION = "GATEWAY_RATE_DEVIATION"
    TAX_BASE_DEVIATION = "TAX_BASE_DEVIATION"
    DUPLICATE_DEDUCTION = "DUPLICATE_DEDUCTION"
    SETTLEMENT_PROCESSING_DELAY = "SETTLEMENT_PROCESSING_DELAY"
    UNSUPPORTED_FEE = "UNSUPPORTED_FEE"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class StructuredHypothesis(AgentModel):
    """LLM output. It can propose an explanation, never a financial decision."""

    hypothesis_id: str = Field(min_length=1, max_length=120)
    kind: HypothesisKind
    statement: str = Field(min_length=1, max_length=1200)
    rationale: str = Field(min_length=1, max_length=2000)
    claimed_rate: str | None = Field(
        default=None,
        description="Optional financial rate encoded as a base-10 decimal string.",
    )
    evidence_ids: list[str] = Field(default_factory=list, max_length=50)
    confidence: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))

    @field_validator("claimed_rate")
    @classmethod
    def validate_claimed_rate(cls, value: str | None) -> str | None:
        if value is None:
            return None
        parsed = Decimal(value)
        if not parsed.is_finite() or parsed < 0:
            raise ValueError("claimed_rate must be a non-negative finite decimal string")
        return value


class AgentEvidence(AgentModel):
    id: str
    kind: str
    source: str
    summary: str
    verified: bool
    attributes: dict[str, str] = Field(default_factory=dict)


class VerificationCheck(AgentModel):
    label: str
    result: str
    expected: str | None = None
    observed: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)


class DeterministicVerification(AgentModel):
    status: str
    classification: str
    checks: list[VerificationCheck]
    conclusion: str
    verifier: str = "sl3dge-deterministic-verifier"


class AgentTraceStep(AgentModel):
    sequence: int
    node: str
    status: str
    message: str
    occurred_at: datetime
    details: dict[str, Any] = Field(default_factory=dict)


class InvestigationExecution(AgentModel):
    execution_id: str
    workflow: str = "ROOT_CAUSE_INVESTIGATION"
    tenant_id: str
    run_id: str
    root_cause_id: str
    violation_ids: list[str]
    status: str
    attempt_count: int
    ai_configured: bool
    hypotheses: list[StructuredHypothesis]
    verification: DeterministicVerification | None = None
    case_id: str | None = None
    trace: list[AgentTraceStep]
    started_at: datetime
    completed_at: datetime


class TypedControlCandidate(AgentModel):
    candidate_id: str
    logical_control_key: str
    control_type: str
    name: str
    clause_id: str
    version: int = Field(ge=1)
    effective_from: date
    effective_to: date | None = None
    supersedes_candidate_id: str | None = None
    parameters: dict[str, Any]
    conditions: list[str]
    rationale: str
    confidence: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))

    @field_validator("parameters")
    @classmethod
    def reject_binary_financial_values(cls, value: dict[str, Any]) -> dict[str, Any]:
        def walk(item: Any, path: str) -> None:
            if isinstance(item, float):
                raise ValueError(f"Binary floating-point value is forbidden at {path}")
            if isinstance(item, dict):
                for key, child in item.items():
                    walk(child, f"{path}.{key}")
            elif isinstance(item, list):
                for index, child in enumerate(item):
                    walk(child, f"{path}[{index}]")

        walk(value, "parameters")
        for key in ("rate", "tolerance", "amount", "fee", "refund_fee", "max_fee"):
            if key in value and not isinstance(value[key], str):
                raise ValueError(f"{key} must be a decimal string")
        return value


class ControlCandidateBatch(AgentModel):
    candidates: list[TypedControlCandidate] = Field(max_length=25)


class BlindSpotRemediationExecution(AgentModel):
    execution_id: str
    workflow: str = "BLIND_SPOT_REMEDIATION"
    tenant_id: str
    run_id: str
    mutation_ids: list[str]
    status: str
    proposed_control: TypedControlCandidate
    schema_valid: bool
    historical_backtest: dict[str, Any]
    mutation_backtest: dict[str, Any]
    comparison: dict[str, Any]
    human_approval_required: bool = True
    trace: list[AgentTraceStep]
    started_at: datetime
    completed_at: datetime


class AgreementCompilationExecution(AgentModel):
    execution_id: str
    workflow: str = "AGREEMENT_CONTROL_COMPILER"
    tenant_id: str
    agreement_id: str
    status: str
    proposals: list[TypedControlCandidate]
    schema_valid: bool
    conflict_count: int
    human_approval_required: bool = True
    trace: list[AgentTraceStep]
    started_at: datetime
    completed_at: datetime
