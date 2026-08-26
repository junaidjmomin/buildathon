from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

JSON_DOCUMENT = JSON().with_variant(JSONB, "postgresql")
MONEY = Numeric(20, 2, asdecimal=True)
RATE = Numeric(12, 8, asdecimal=True)
TENANT_LENGTH = 120


class Base(DeclarativeBase):
    pass


class RunRecord(Base):
    __tablename__ = "runs"

    tenant_id: Mapped[str] = mapped_column(String(TENANT_LENGTH), primary_key=True)
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(32), index=True)
    seed: Mapped[int | None] = mapped_column(Integer)
    manifest: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class EventRecord(Base):
    __tablename__ = "events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "run_id"],
            ["runs.tenant_id", "runs.id"],
            ondelete="CASCADE",
        ),
        Index("ix_events_tenant_run_type", "tenant_id", "run_id", "event_type"),
        Index("ix_events_tenant_external", "tenant_id", "external_id"),
    )

    tenant_id: Mapped[str] = mapped_column(String(TENANT_LENGTH), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    source: Mapped[str] = mapped_column(String(64))
    external_id: Mapped[str] = mapped_column(String(120))
    event_type: Mapped[str] = mapped_column(String(48))
    amount: Mapped[Decimal] = mapped_column(MONEY)
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str | None] = mapped_column(String(48))
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT)
    normalized_payload: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT)


class EventEdgeRecord(Base):
    __tablename__ = "event_edges"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "run_id"],
            ["runs.tenant_id", "runs.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "run_id", "from_event_id"],
            ["events.tenant_id", "events.run_id", "events.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "run_id", "to_event_id"],
            ["events.tenant_id", "events.run_id", "events.id"],
            ondelete="CASCADE",
        ),
        Index(
            "ix_edges_tenant_run_relationship",
            "tenant_id",
            "run_id",
            "relationship",
        ),
    )

    tenant_id: Mapped[str] = mapped_column(String(TENANT_LENGTH), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    id: Mapped[str] = mapped_column(String(140), primary_key=True)
    from_event_id: Mapped[str] = mapped_column(String(120), index=True)
    to_event_id: Mapped[str] = mapped_column(String(120), index=True)
    relationship: Mapped[str] = mapped_column(String(64))
    confidence: Mapped[Decimal] = mapped_column(RATE)
    method: Mapped[str] = mapped_column(String(32))
    evidence: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT)


class ControlRecord(Base):
    __tablename__ = "controls"
    __table_args__ = (
        Index(
            "ix_controls_tenant_logical_effective",
            "tenant_id",
            "logical_control_key",
            "effective_from",
        ),
    )

    tenant_id: Mapped[str] = mapped_column(String(TENANT_LENGTH), primary_key=True)
    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    logical_control_key: Mapped[str] = mapped_column(String(120))
    version: Mapped[int] = mapped_column(Integer)
    control_type: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    agreement_id: Mapped[str] = mapped_column(String(120))
    clause_id: Mapped[str | None] = mapped_column(String(120))
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT)
    definition: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT)


class ViolationRecord(Base):
    __tablename__ = "violations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "run_id"],
            ["runs.tenant_id", "runs.id"],
            ondelete="CASCADE",
        ),
        Index("ix_violations_tenant_run_category", "tenant_id", "run_id", "category"),
    )

    tenant_id: Mapped[str] = mapped_column(String(TENANT_LENGTH), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    payment_id: Mapped[str] = mapped_column(String(120), index=True)
    category: Mapped[str] = mapped_column(String(80))
    control_type: Mapped[str] = mapped_column(String(64))
    difference: Mapped[Decimal] = mapped_column(MONEY)
    financial_impact: Mapped[Decimal] = mapped_column(MONEY)
    confidence: Mapped[Decimal] = mapped_column(RATE)
    root_cause_id: Mapped[str | None] = mapped_column(String(120), index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    evidence: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT)


class RootCauseRecord(Base):
    __tablename__ = "root_causes"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "run_id"],
            ["runs.tenant_id", "runs.id"],
            ondelete="CASCADE",
        ),
    )

    tenant_id: Mapped[str] = mapped_column(String(TENANT_LENGTH), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(80))
    affected_count: Mapped[int] = mapped_column(Integer)
    verified_impact: Mapped[Decimal] = mapped_column(MONEY)
    verification_status: Mapped[str] = mapped_column(String(32))
    evidence: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT)


class MutationTestRecord(Base):
    __tablename__ = "mutation_tests"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "run_id"],
            ["runs.tenant_id", "runs.id"],
            ondelete="CASCADE",
        ),
    )

    tenant_id: Mapped[str] = mapped_column(String(TENANT_LENGTH), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    status: Mapped[str] = mapped_column(String(32))
    mutation_count: Mapped[int] = mapped_column(Integer)
    detected_count: Mapped[int] = mapped_column(Integer)
    missed_count: Mapped[int] = mapped_column(Integer)
    detection_rate: Mapped[Decimal] = mapped_column(RATE)
    false_positive_count: Mapped[int] = mapped_column(Integer)
    results: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ArtifactRecord(Base):
    __tablename__ = "artifacts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "run_id"],
            ["runs.tenant_id", "runs.id"],
            ondelete="CASCADE",
        ),
        Index("ix_artifacts_tenant_run_kind", "tenant_id", "run_id", "kind"),
    )

    tenant_id: Mapped[str] = mapped_column(String(TENANT_LENGTH), primary_key=True)
    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    run_id: Mapped[str | None] = mapped_column(String(80))
    case_id: Mapped[str | None] = mapped_column(String(120), index=True)
    kind: Mapped[str] = mapped_column(String(48))
    bucket: Mapped[str] = mapped_column(String(80))
    object_path: Mapped[str] = mapped_column(Text)
    content_type: Mapped[str] = mapped_column(String(120))
    byte_size: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AuditLogRecord(Base):
    __tablename__ = "audit_log"
    __table_args__ = (
        Index("ix_audit_tenant_created", "tenant_id", "created_at"),
        Index("ix_audit_tenant_resource", "tenant_id", "resource_type", "resource_id"),
    )

    tenant_id: Mapped[str] = mapped_column(String(TENANT_LENGTH), primary_key=True)
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    actor_id: Mapped[str] = mapped_column(String(160))
    action: Mapped[str] = mapped_column(String(80))
    resource_type: Mapped[str] = mapped_column(String(80))
    resource_id: Mapped[str] = mapped_column(String(160))
    outcome: Mapped[str] = mapped_column(String(32))
    details: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT)
    request_id: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SourceSnapshotRecord(Base):
    """Immutable payload captured from an upstream system.

    Snapshots deliberately retain their run identifier without a foreign key. Source
    evidence must survive run cleanup and may be captured before a run is created.
    """

    __tablename__ = "source_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "source_system",
            "resource_type",
            "external_id",
            "content_sha256",
            name="uq_source_snapshots_tenant_fingerprint",
        ),
        Index("ix_source_snapshots_tenant_run", "tenant_id", "run_id"),
        Index(
            "ix_source_snapshots_tenant_external",
            "tenant_id",
            "source_system",
            "resource_type",
            "external_id",
            "captured_at",
        ),
        Index("ix_source_snapshots_tenant_hash", "tenant_id", "content_sha256"),
    )

    tenant_id: Mapped[str] = mapped_column(String(TENANT_LENGTH), primary_key=True)
    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    run_id: Mapped[str | None] = mapped_column(String(80))
    job_id: Mapped[str | None] = mapped_column(String(120))
    source_system: Mapped[str] = mapped_column(String(64))
    resource_type: Mapped[str] = mapped_column(String(80))
    external_id: Mapped[str] = mapped_column(String(160))
    source_version: Mapped[str | None] = mapped_column(String(120))
    schema_version: Mapped[int] = mapped_column(Integer, default=1)
    content_sha256: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT)
    provenance: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT)
    source_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ControlEvaluationRecord(Base):
    """A durable, deterministic control decision and the evidence used to reach it."""

    __tablename__ = "control_evaluations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "run_id"],
            ["runs.tenant_id", "runs.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "control_id"],
            ["controls.tenant_id", "controls.id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "tenant_id",
            "run_id",
            "control_id",
            "target_type",
            "target_id",
            name="uq_control_evaluations_target",
        ),
        CheckConstraint(
            "outcome IN ('PASS', 'VIOLATION', 'WARNING', 'UNRESOLVED')",
            name="ck_control_evaluations_outcome",
        ),
        Index(
            "ix_control_evaluations_tenant_run_outcome",
            "tenant_id",
            "run_id",
            "outcome",
        ),
        Index(
            "ix_control_evaluations_tenant_control",
            "tenant_id",
            "control_id",
            "evaluated_at",
        ),
        Index(
            "ix_control_evaluations_tenant_target",
            "tenant_id",
            "target_type",
            "target_id",
        ),
    )

    tenant_id: Mapped[str] = mapped_column(String(TENANT_LENGTH), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    control_id: Mapped[str] = mapped_column(String(120))
    control_version: Mapped[int] = mapped_column(Integer)
    target_type: Mapped[str] = mapped_column(String(64))
    target_id: Mapped[str] = mapped_column(String(160))
    outcome: Mapped[str] = mapped_column(String(32))
    expected_amount: Mapped[Decimal | None] = mapped_column(MONEY)
    actual_amount: Mapped[Decimal | None] = mapped_column(MONEY)
    tolerance_amount: Mapped[Decimal | None] = mapped_column(MONEY)
    difference_amount: Mapped[Decimal | None] = mapped_column(MONEY)
    financial_impact: Mapped[Decimal | None] = mapped_column(MONEY)
    confidence: Mapped[Decimal] = mapped_column(RATE)
    input_fingerprint: Mapped[str] = mapped_column(String(64))
    engine_version: Mapped[str] = mapped_column(String(80))
    source_snapshot_ids: Mapped[list[str]] = mapped_column(JSON_DOCUMENT)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class BackgroundJobRecord(Base):
    """Durable job envelope used by workers with leases and bounded retries."""

    __tablename__ = "background_jobs"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "job_type",
            "idempotency_key",
            name="uq_background_jobs_tenant_idempotency",
        ),
        CheckConstraint("attempt_count >= 0", name="ck_background_jobs_attempt_count"),
        CheckConstraint("max_attempts >= 1", name="ck_background_jobs_max_attempts"),
        CheckConstraint(
            "status IN ('QUEUED', 'RUNNING', 'RETRYABLE', 'SUCCEEDED', 'FAILED', 'CANCELLED')",
            name="ck_background_jobs_status",
        ),
        Index(
            "ix_background_jobs_tenant_claim",
            "tenant_id",
            "status",
            "available_at",
            "lease_expires_at",
            "priority",
            "created_at",
        ),
        Index("ix_background_jobs_tenant_run", "tenant_id", "run_id", "created_at"),
        Index("ix_background_jobs_tenant_updated", "tenant_id", "updated_at"),
        Index(
            "ix_background_jobs_tenant_type_status_updated",
            "tenant_id",
            "job_type",
            "status",
            "updated_at",
        ),
    )

    tenant_id: Mapped[str] = mapped_column(String(TENANT_LENGTH), primary_key=True)
    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    run_id: Mapped[str | None] = mapped_column(String(80))
    job_type: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(32), default="QUEUED")
    idempotency_key: Mapped[str] = mapped_column(String(200))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON_DOCUMENT)
    error: Mapped[dict[str, Any] | None] = mapped_column(JSON_DOCUMENT)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    leased_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_owner: Mapped[str | None] = mapped_column(String(160))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AgentExecutionRecord(Base):
    """Durable final output and trace for one bounded agent workflow execution."""

    __tablename__ = "agent_executions"
    __table_args__ = (
        CheckConstraint(
            "workflow IN ('ROOT_CAUSE_INVESTIGATION', 'BLIND_SPOT_REMEDIATION', "
            "'AGREEMENT_CONTROL_COMPILER')",
            name="ck_agent_executions_workflow",
        ),
        Index(
            "ix_agent_executions_tenant_resource",
            "tenant_id",
            "resource_type",
            "resource_id",
            "completed_at",
        ),
        Index(
            "ix_agent_executions_tenant_updated",
            "tenant_id",
            "updated_at",
        ),
    )

    tenant_id: Mapped[str] = mapped_column(String(TENANT_LENGTH), primary_key=True)
    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    workflow: Mapped[str] = mapped_column(String(64))
    resource_type: Mapped[str] = mapped_column(String(64))
    resource_id: Mapped[str] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(48))
    result: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
