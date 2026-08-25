from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ApiModel(BaseModel):
    model_config = ConfigDict(json_encoders={Decimal: lambda value: f"{value:.2f}"})


class EvaluationStatus(str, Enum):
    PASS = "PASS"
    VIOLATION = "VIOLATION"
    WARNING = "WARNING"
    UNRESOLVED = "UNRESOLVED"


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
    refund_amount: Decimal = Decimal("0")
    refund_deduction: Decimal = Decimal("0")
    unsupported_fee: Decimal = Decimal("0")
    settled_at: datetime
    actual_net: Decimal
    bank_credit: Decimal | None
    status: str = "captured"


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
    occurred_at: datetime


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


class RunSummary(ApiModel):
    id: str
    name: str
    status: str
    transaction_count: int
    event_count: int
    relationship_count: int
    control_evaluation_count: int
    breakdown: StatusBreakdown
    precision: Decimal
    recall: Decimal
    false_positive_rate: Decimal
    verified_leakage: Decimal
    cash_delayed: Decimal
    unresolved_count: int
    processing_ms: int
    evaluations_per_second: int
    confusion_matrix: ConfusionMatrix
    completed_at: datetime


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

