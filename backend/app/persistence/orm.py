from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

JSON_DOCUMENT = JSON().with_variant(JSONB, "postgresql")
MONEY = Numeric(20, 2, asdecimal=True)
RATE = Numeric(12, 8, asdecimal=True)


class Base(DeclarativeBase):
    pass


class RunRecord(Base):
    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(32), index=True)
    seed: Mapped[int | None] = mapped_column(Integer)
    manifest: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class EventRecord(Base):
    __tablename__ = "events"
    __table_args__ = (Index("ix_events_run_type", "run_id", "event_type"),)

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("runs.id", ondelete="CASCADE"), index=True
    )
    source: Mapped[str] = mapped_column(String(64))
    external_id: Mapped[str] = mapped_column(String(120), index=True)
    event_type: Mapped[str] = mapped_column(String(48), index=True)
    amount: Mapped[Decimal] = mapped_column(MONEY)
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str | None] = mapped_column(String(48))
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT)
    normalized_payload: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT)


class EventEdgeRecord(Base):
    __tablename__ = "event_edges"
    __table_args__ = (Index("ix_edges_run_relationship", "run_id", "relationship"),)

    id: Mapped[str] = mapped_column(String(140), primary_key=True)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("runs.id", ondelete="CASCADE"), index=True
    )
    from_event_id: Mapped[str] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), index=True
    )
    to_event_id: Mapped[str] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), index=True
    )
    relationship: Mapped[str] = mapped_column(String(64))
    confidence: Mapped[Decimal] = mapped_column(RATE)
    method: Mapped[str] = mapped_column(String(32))
    evidence: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT)


class ControlRecord(Base):
    __tablename__ = "controls"
    __table_args__ = (
        Index("ix_controls_logical_effective", "logical_control_key", "effective_from"),
    )

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    logical_control_key: Mapped[str] = mapped_column(String(120), index=True)
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
    __table_args__ = (Index("ix_violations_run_category", "run_id", "category"),)

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("runs.id", ondelete="CASCADE"), index=True
    )
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

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("runs.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(80))
    affected_count: Mapped[int] = mapped_column(Integer)
    verified_impact: Mapped[Decimal] = mapped_column(MONEY)
    verification_status: Mapped[str] = mapped_column(String(32))
    evidence: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT)


class MutationTestRecord(Base):
    __tablename__ = "mutation_tests"

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("runs.id", ondelete="CASCADE"), index=True
    )
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
    __table_args__ = (Index("ix_artifacts_run_kind", "run_id", "kind"),)

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    run_id: Mapped[str | None] = mapped_column(
        ForeignKey("runs.id", ondelete="CASCADE"), index=True
    )
    case_id: Mapped[str | None] = mapped_column(String(120), index=True)
    kind: Mapped[str] = mapped_column(String(48))
    bucket: Mapped[str] = mapped_column(String(80))
    object_path: Mapped[str] = mapped_column(Text)
    content_type: Mapped[str] = mapped_column(String(120))
    byte_size: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
