from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from hashlib import sha256
from typing import Any
from uuid import uuid4

from sqlalchemy import delete, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domain.models import (
    CanonicalEventEdge,
    Control,
    FinancialEvent,
    MutationTestSummary,
    RootCause,
    RunSummary,
    Violation,
)
from app.persistence.orm import (
    AgentExecutionRecord,
    AuditLogRecord,
    BackgroundJobRecord,
    ControlEvaluationRecord,
    ControlRecord,
    EventEdgeRecord,
    EventRecord,
    MutationTestRecord,
    RootCauseRecord,
    RunRecord,
    SourceSnapshotRecord,
    ViolationRecord,
)
from app.synthetic.generator import DEMO_SEED, SyntheticDataset


def _utc_start(value: Any) -> datetime:
    return datetime.combine(value, time.min, tzinfo=timezone.utc)


def _event(
    *,
    tenant_id: str,
    event_id: str,
    run_id: str,
    source: str,
    external_id: str,
    event_type: str,
    amount: Decimal,
    occurred_at: datetime,
    status: str,
    payload: dict[str, Any],
) -> EventRecord:
    return EventRecord(
        tenant_id=tenant_id,
        id=event_id,
        run_id=run_id,
        source=source,
        external_id=external_id,
        event_type=event_type,
        amount=amount,
        currency="INR",
        occurred_at=occurred_at,
        status=status,
        raw_payload=payload,
        normalized_payload=payload,
    )


def canonical_records(
    run_id: str,
    dataset: SyntheticDataset,
    *,
    tenant_id: str = "novacart_demo",
) -> tuple[list[EventRecord], list[EventEdgeRecord]]:
    events: list[EventRecord] = []
    edges: list[EventEdgeRecord] = []
    seen_events: set[str] = set()
    settlement_totals: dict[str, Decimal] = defaultdict(lambda: Decimal("0.00"))
    bank_totals: dict[str, Decimal] = defaultdict(lambda: Decimal("0.00"))
    settlement_times: dict[str, datetime] = {}
    for payment in dataset.payments:
        settlement_totals[payment.settlement_id] += payment.actual_net
        settlement_times[payment.settlement_id] = max(
            settlement_times.get(payment.settlement_id, payment.settled_at),
            payment.settled_at,
        )
        if payment.bank_txn_id is not None and payment.bank_credit is not None:
            bank_totals[payment.bank_txn_id] += payment.bank_credit

    def append_event(record: EventRecord) -> None:
        if record.id not in seen_events:
            events.append(record)
            seen_events.add(record.id)

    for payment in dataset.payments:
        order_event_id = f"EVT_ORDER_{payment.order_id}"
        payment_event_id = f"EVT_PAYMENT_{payment.payment_id}"
        settlement_event_id = f"EVT_SETTLEMENT_{payment.settlement_id}"
        bank_event_id = (
            f"EVT_BANK_{payment.bank_txn_id}" if payment.bank_txn_id is not None else None
        )

        append_event(
            _event(
                tenant_id=tenant_id,
                event_id=order_event_id,
                run_id=run_id,
                source="NOVACART",
                external_id=payment.order_id,
                event_type="ORDER",
                amount=payment.amount,
                occurred_at=payment.captured_at,
                status="created",
                payload={"order_id": payment.order_id, "amount": str(payment.amount)},
            )
        )
        append_event(
            _event(
                tenant_id=tenant_id,
                event_id=payment_event_id,
                run_id=run_id,
                source="RAZORPAY",
                external_id=payment.payment_id,
                event_type="PAYMENT",
                amount=payment.amount,
                occurred_at=payment.captured_at,
                status=payment.status,
                payload={
                    "payment_id": payment.payment_id,
                    "fee": str(payment.actual_fee),
                    "tax": str(payment.actual_tax),
                },
            )
        )
        append_event(
            _event(
                tenant_id=tenant_id,
                event_id=settlement_event_id,
                run_id=run_id,
                source="RAZORPAY",
                external_id=payment.settlement_id,
                event_type="SETTLEMENT",
                amount=settlement_totals[payment.settlement_id],
                occurred_at=settlement_times[payment.settlement_id],
                status="processed",
                payload={"settlement_id": payment.settlement_id},
            )
        )
        if bank_event_id is not None and payment.bank_credit is not None:
            append_event(
                _event(
                    tenant_id=tenant_id,
                    event_id=bank_event_id,
                    run_id=run_id,
                    source="BANK",
                    external_id=payment.bank_txn_id or "",
                    event_type="BANK_CREDIT",
                    amount=bank_totals[payment.bank_txn_id],
                    occurred_at=settlement_times[payment.settlement_id],
                    status="posted",
                    payload={"bank_txn_id": payment.bank_txn_id},
                )
            )
        if payment.refund_id is not None:
            append_event(
                _event(
                    tenant_id=tenant_id,
                    event_id=f"EVT_REFUND_{payment.refund_id}",
                    run_id=run_id,
                    source="RAZORPAY",
                    external_id=payment.refund_id,
                    event_type="REFUND",
                    amount=payment.refund_amount,
                    occurred_at=payment.captured_at,
                    status="processed",
                    payload={"refund_id": payment.refund_id},
                )
            )

        edge_evidence = {"payment_id": payment.payment_id, "score": "1.0000"}
        edges.extend(
            [
                EventEdgeRecord(
                    tenant_id=tenant_id,
                    id=f"EDGE_ORDER_PAYMENT_{payment.payment_id}",
                    run_id=run_id,
                    from_event_id=order_event_id,
                    to_event_id=payment_event_id,
                    relationship="ORDER_TO_PAYMENT",
                    confidence=Decimal("1.0000"),
                    method="EXACT",
                    evidence=edge_evidence,
                ),
                EventEdgeRecord(
                    tenant_id=tenant_id,
                    id=f"EDGE_PAYMENT_SETTLEMENT_{payment.payment_id}",
                    run_id=run_id,
                    from_event_id=payment_event_id,
                    to_event_id=settlement_event_id,
                    relationship="PAYMENT_TO_SETTLEMENT",
                    confidence=Decimal("1.0000"),
                    method="EXACT",
                    evidence=edge_evidence,
                ),
            ]
        )
        if bank_event_id is not None:
            edges.append(
                EventEdgeRecord(
                    tenant_id=tenant_id,
                    id=f"EDGE_SETTLEMENT_BANK_{payment.payment_id}",
                    run_id=run_id,
                    from_event_id=settlement_event_id,
                    to_event_id=bank_event_id,
                    relationship="SETTLEMENT_TO_BANK",
                    confidence=Decimal("1.0000"),
                    method="EXACT",
                    evidence=edge_evidence,
                )
            )

    for index in range(6):
        chargeback_id = f"CB_{index + 1:03d}"
        payment = dataset.payments[100 + index]
        append_event(
            _event(
                tenant_id=tenant_id,
                event_id=f"EVT_CHARGEBACK_{chargeback_id}",
                run_id=run_id,
                source="RAZORPAY",
                external_id=chargeback_id,
                event_type="CHARGEBACK",
                amount=payment.amount,
                occurred_at=payment.settled_at,
                status="closed",
                payload={"chargeback_id": chargeback_id},
            )
        )

    return events, edges


class RunRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def replace_demo_run(
        self,
        *,
        run_id: str,
        dataset: SyntheticDataset,
        summary: RunSummary,
        violations: list[Violation],
        root_causes: list[RootCause],
        controls: list[Control],
        tenant_id: str = "novacart_demo",
    ) -> tuple[int, int]:
        self.session.execute(
            delete(RunRecord).where(
                RunRecord.tenant_id == tenant_id,
                RunRecord.id == run_id,
            )
        )
        self.session.flush()

        events, edges = canonical_records(run_id, dataset, tenant_id=tenant_id)
        self.session.add(
            RunRecord(
                tenant_id=tenant_id,
                id=run_id,
                name=summary.name,
                status=summary.status,
                seed=DEMO_SEED,
                manifest={
                    "counts": dataset.counts,
                    "event_count": summary.event_count,
                    "relationship_count": summary.relationship_count,
                    "control_evaluation_count": summary.control_evaluation_count,
                },
                completed_at=summary.completed_at,
                created_at=datetime.now(timezone.utc),
            )
        )
        self.session.add_all(events)
        self.session.flush()
        self.session.add_all(edges)

        for control in controls:
            self.session.merge(
                ControlRecord(
                    tenant_id=tenant_id,
                    id=control.id,
                    logical_control_key=control.logical_control_key,
                    version=control.version,
                    control_type=control.control_type.value,
                    status=control.status,
                    agreement_id=control.agreement_id,
                    clause_id=control.clause_id,
                    effective_from=_utc_start(control.effective_from),
                    effective_to=(
                        _utc_start(control.effective_to) if control.effective_to else None
                    ),
                    parameters=control.model_dump(mode="json")["parameters"],
                    definition=control.model_dump(mode="json"),
                )
            )

        self.session.add_all(
            ViolationRecord(
                tenant_id=tenant_id,
                id=violation.id,
                run_id=run_id,
                payment_id=violation.payment_id,
                category=violation.category,
                control_type=violation.control_type.value,
                difference=violation.difference,
                financial_impact=violation.financial_impact,
                confidence=violation.confidence,
                root_cause_id=violation.root_cause_id,
                occurred_at=violation.occurred_at,
                evidence={"expected": violation.expected, "actual": violation.actual},
            )
            for violation in violations
        )
        self.session.add_all(
            RootCauseRecord(
                tenant_id=tenant_id,
                id=root.id,
                run_id=run_id,
                title=root.title,
                category=root.category,
                affected_count=root.affected_count,
                verified_impact=root.verified_impact,
                verification_status=root.verification_status,
                evidence={
                    "expected": root.expected_value,
                    "observed": root.observed_value,
                },
            )
            for root in root_causes
        )
        return len(events), len(edges)

    def save_mutation_test(
        self, result: MutationTestSummary, *, tenant_id: str = "novacart_demo"
    ) -> None:
        self.session.merge(
            MutationTestRecord(
                tenant_id=tenant_id,
                id=result.id,
                run_id=result.source_run_id,
                status=result.status,
                mutation_count=result.mutation_count,
                detected_count=result.detected_count,
                missed_count=result.missed_count,
                detection_rate=result.mutation_detection_rate,
                false_positive_count=result.false_positive_count,
                results=result.model_dump(mode="json"),
                created_at=result.created_at,
            )
        )

    def save_canonical_sync(
        self,
        *,
        run_id: str,
        sync_id: str,
        synced_at: datetime,
        events: list[FinancialEvent],
        edges: list[CanonicalEventEdge],
        tenant_id: str,
    ) -> None:
        if self.session.get(RunRecord, (tenant_id, run_id)) is None:
            self.session.add(
                RunRecord(
                    tenant_id=tenant_id,
                    id=run_id,
                    name="Razorpay read-only sync",
                    status="COMPLETE",
                    seed=None,
                    manifest={
                        "sync_id": sync_id,
                        "event_count": len(events),
                        "relationship_count": len(edges),
                    },
                    completed_at=synced_at,
                    created_at=synced_at,
                )
            )
            self.session.flush()
        for event in events:
            self.session.merge(
                EventRecord(
                    tenant_id=tenant_id,
                    id=event.id,
                    run_id=event.run_id,
                    source=event.source,
                    external_id=event.external_id,
                    event_type=event.event_type,
                    amount=event.amount,
                    currency=event.currency,
                    occurred_at=event.timestamp,
                    status=event.status,
                    raw_payload=event.raw_payload,
                    normalized_payload=event.normalized_payload,
                )
            )
        self.session.flush()
        for edge in edges:
            self.session.merge(
                EventEdgeRecord(
                    tenant_id=tenant_id,
                    id=edge.id,
                    run_id=edge.run_id,
                    from_event_id=edge.from_event_id,
                    to_event_id=edge.to_event_id,
                    relationship=edge.relationship,
                    confidence=edge.confidence,
                    method=edge.method,
                    evidence=edge.evidence,
                )
            )

    def save_controls(self, controls: list[Control], *, tenant_id: str) -> None:
        for control in controls:
            self.session.merge(
                ControlRecord(
                    tenant_id=tenant_id,
                    id=control.id,
                    logical_control_key=control.logical_control_key,
                    version=control.version,
                    control_type=control.control_type.value,
                    status=control.status,
                    agreement_id=control.agreement_id,
                    clause_id=control.clause_id,
                    effective_from=_utc_start(control.effective_from),
                    effective_to=(
                        _utc_start(control.effective_to) if control.effective_to else None
                    ),
                    parameters=control.model_dump(mode="json")["parameters"],
                    definition=control.model_dump(mode="json"),
                )
            )

    def save_violation(self, violation: Violation, *, run_id: str, tenant_id: str) -> None:
        self.session.merge(
            ViolationRecord(
                tenant_id=tenant_id,
                id=violation.id,
                run_id=run_id,
                payment_id=violation.payment_id,
                category=violation.category,
                control_type=violation.control_type.value,
                difference=violation.difference,
                financial_impact=violation.financial_impact,
                confidence=violation.confidence,
                root_cause_id=violation.root_cause_id,
                occurred_at=violation.occurred_at,
                evidence={"expected": violation.expected, "actual": violation.actual},
            )
        )

    def write_audit(
        self,
        *,
        tenant_id: str,
        actor_id: str,
        action: str,
        resource_type: str,
        resource_id: str,
        outcome: str,
        details: dict[str, Any] | None = None,
        request_id: str | None = None,
    ) -> None:
        self.session.add(
            AuditLogRecord(
                tenant_id=tenant_id,
                id=f"AUD_{uuid4().hex.upper()}",
                actor_id=actor_id,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                outcome=outcome,
                details=details or {},
                request_id=request_id,
                created_at=datetime.now(timezone.utc),
            )
        )


class SourceSnapshotRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def capture(
        self,
        *,
        tenant_id: str,
        source_system: str,
        resource_type: str,
        external_id: str,
        payload: dict[str, Any],
        provenance: dict[str, Any],
        captured_at: datetime,
        run_id: str | None = None,
        job_id: str | None = None,
        source_version: str | None = None,
        source_created_at: datetime | None = None,
        schema_version: int = 1,
    ) -> SourceSnapshotRecord:
        canonical = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
        fingerprint = sha256(canonical).hexdigest()
        existing = self.session.scalar(
            select(SourceSnapshotRecord).where(
                SourceSnapshotRecord.tenant_id == tenant_id,
                SourceSnapshotRecord.source_system == source_system,
                SourceSnapshotRecord.resource_type == resource_type,
                SourceSnapshotRecord.external_id == external_id,
                SourceSnapshotRecord.content_sha256 == fingerprint,
            )
        )
        if existing is not None:
            return existing
        record = SourceSnapshotRecord(
            tenant_id=tenant_id,
            id=f"SRC_{uuid4().hex.upper()}",
            run_id=run_id,
            job_id=job_id,
            source_system=source_system,
            resource_type=resource_type,
            external_id=external_id,
            source_version=source_version,
            schema_version=schema_version,
            content_sha256=fingerprint,
            payload=payload,
            provenance=provenance,
            source_created_at=source_created_at,
            captured_at=captured_at,
            created_at=datetime.now(timezone.utc),
        )
        self.session.add(record)
        self.session.flush()
        return record


class ControlEvaluationRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def save(
        self,
        *,
        tenant_id: str,
        run_id: str,
        evaluation_id: str,
        control_id: str,
        control_version: int,
        target_type: str,
        target_id: str,
        outcome: str,
        expected_amount: Decimal | None,
        actual_amount: Decimal | None,
        tolerance_amount: Decimal | None,
        difference_amount: Decimal | None,
        financial_impact: Decimal | None,
        confidence: Decimal,
        input_fingerprint: str,
        engine_version: str,
        source_snapshot_ids: list[str],
        evidence: dict[str, Any],
        evaluated_at: datetime,
    ) -> ControlEvaluationRecord:
        record = ControlEvaluationRecord(
            tenant_id=tenant_id,
            run_id=run_id,
            id=evaluation_id,
            control_id=control_id,
            control_version=control_version,
            target_type=target_type,
            target_id=target_id,
            outcome=outcome,
            expected_amount=expected_amount,
            actual_amount=actual_amount,
            tolerance_amount=tolerance_amount,
            difference_amount=difference_amount,
            financial_impact=financial_impact,
            confidence=confidence,
            input_fingerprint=input_fingerprint,
            engine_version=engine_version,
            source_snapshot_ids=source_snapshot_ids,
            evidence=evidence,
            evaluated_at=evaluated_at,
            created_at=datetime.now(timezone.utc),
        )
        return self.session.merge(record)


class JobRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def enqueue(
        self,
        *,
        tenant_id: str,
        job_type: str,
        idempotency_key: str,
        payload: dict[str, Any],
        run_id: str | None = None,
        priority: int = 0,
        max_attempts: int = 3,
    ) -> tuple[BackgroundJobRecord, bool]:
        existing = self._by_idempotency(tenant_id, job_type, idempotency_key)
        if existing is not None:
            return existing, False
        now = datetime.now(timezone.utc)
        record = BackgroundJobRecord(
            tenant_id=tenant_id,
            id=f"JOB_{uuid4().hex.upper()}",
            run_id=run_id,
            job_type=job_type,
            status="QUEUED",
            idempotency_key=idempotency_key,
            payload=payload,
            result=None,
            error=None,
            priority=priority,
            attempt_count=0,
            max_attempts=max_attempts,
            available_at=now,
            leased_at=None,
            lease_expires_at=None,
            lease_owner=None,
            started_at=None,
            finished_at=None,
            created_at=now,
            updated_at=now,
        )
        savepoint = self.session.begin_nested()
        try:
            self.session.add(record)
            self.session.flush()
            savepoint.commit()
            return record, True
        except IntegrityError:
            savepoint.rollback()
            existing = self._by_idempotency(tenant_id, job_type, idempotency_key)
            if existing is None:
                raise
            return existing, False

    def get(self, *, tenant_id: str, job_id: str) -> BackgroundJobRecord | None:
        return self.session.get(BackgroundJobRecord, (tenant_id, job_id))

    def latest(
        self, *, tenant_id: str, job_type: str, status: str | None = None
    ) -> BackgroundJobRecord | None:
        statement = select(BackgroundJobRecord).where(
            BackgroundJobRecord.tenant_id == tenant_id,
            BackgroundJobRecord.job_type == job_type,
        )
        if status is not None:
            statement = statement.where(BackgroundJobRecord.status == status)
        return self.session.scalar(
            statement.order_by(BackgroundJobRecord.updated_at.desc()).limit(1)
        )

    def _by_idempotency(
        self, tenant_id: str, job_type: str, idempotency_key: str
    ) -> BackgroundJobRecord | None:
        return self.session.scalar(
            select(BackgroundJobRecord).where(
                BackgroundJobRecord.tenant_id == tenant_id,
                BackgroundJobRecord.job_type == job_type,
                BackgroundJobRecord.idempotency_key == idempotency_key,
            )
        )

    def claim_next(
        self,
        *,
        tenant_id: str,
        worker_id: str,
        lease_seconds: int = 120,
        job_types: list[str] | None = None,
    ) -> BackgroundJobRecord | None:
        now = datetime.now(timezone.utc)
        conditions = [
            BackgroundJobRecord.tenant_id == tenant_id,
            BackgroundJobRecord.status.in_(["QUEUED", "RETRYABLE"]),
            BackgroundJobRecord.available_at <= now,
            or_(
                BackgroundJobRecord.lease_expires_at.is_(None),
                BackgroundJobRecord.lease_expires_at < now,
            ),
        ]
        if job_types:
            conditions.append(BackgroundJobRecord.job_type.in_(job_types))
        statement = (
            select(BackgroundJobRecord)
            .where(*conditions)
            .order_by(
                BackgroundJobRecord.priority.desc(),
                BackgroundJobRecord.created_at.asc(),
            )
            .limit(1)
        )
        if self.session.bind is not None and self.session.bind.dialect.name == "postgresql":
            statement = statement.with_for_update(skip_locked=True)
        record = self.session.scalar(statement)
        if record is None:
            return None
        record.status = "RUNNING"
        record.attempt_count += 1
        record.leased_at = now
        record.lease_expires_at = now + timedelta(seconds=lease_seconds)
        record.lease_owner = worker_id
        record.started_at = record.started_at or now
        record.updated_at = now
        self.session.flush()
        return record

    def succeed(self, record: BackgroundJobRecord, result: dict[str, Any]) -> None:
        now = datetime.now(timezone.utc)
        record.status = "SUCCEEDED"
        record.result = result
        record.error = None
        record.lease_owner = None
        record.lease_expires_at = None
        record.finished_at = now
        record.updated_at = now

    def fail(
        self,
        record: BackgroundJobRecord,
        *,
        error_code: str,
        safe_message: str,
        retry_delay_seconds: int = 30,
        retryable: bool = True,
    ) -> None:
        now = datetime.now(timezone.utc)
        will_retry = retryable and record.attempt_count < record.max_attempts
        record.status = "RETRYABLE" if will_retry else "FAILED"
        record.error = {"code": error_code, "message": safe_message}
        record.lease_owner = None
        record.lease_expires_at = None
        record.available_at = now + timedelta(seconds=retry_delay_seconds)
        record.finished_at = None if will_retry else now
        record.updated_at = now


class AgentExecutionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def save(
        self,
        *,
        tenant_id: str,
        execution_id: str,
        workflow: str,
        resource_type: str,
        resource_id: str,
        status: str,
        result: dict[str, Any],
        started_at: datetime,
        completed_at: datetime,
    ) -> AgentExecutionRecord:
        now = datetime.now(timezone.utc)
        record = AgentExecutionRecord(
            tenant_id=tenant_id,
            id=execution_id,
            workflow=workflow,
            resource_type=resource_type,
            resource_id=resource_id,
            status=status,
            result=result,
            started_at=started_at,
            completed_at=completed_at,
            created_at=now,
            updated_at=now,
        )
        return self.session.merge(record)

    def get(self, *, tenant_id: str, execution_id: str) -> AgentExecutionRecord | None:
        return self.session.get(AgentExecutionRecord, (tenant_id, execution_id))
