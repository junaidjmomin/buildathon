from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from hashlib import sha256
from typing import Any
from uuid import uuid4

from sqlalchemy import and_, delete, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.controls.verification import verify_draft_control
from app.core.money import money
from app.domain.models import (
    Agreement,
    AgreementClause,
    AgreementClauseCreate,
    CanonicalEventEdge,
    CaseAuditEntry,
    CaseEvidence,
    ConfusionMatrix,
    Control,
    ControlProposal,
    ControlProposalVerification,
    ControlType,
    EvaluationStatus,
    ExceptionCase,
    ExceptionCaseStatus,
    FinancialEvent,
    MutationTestSummary,
    RootCause,
    RunListItem,
    RunSummary,
    StatusBreakdown,
    UnresolvedMatch,
    Violation,
)
from app.persistence.orm import (
    AgentExecutionRecord,
    AgreementClauseRecord,
    AgreementRecord,
    AuditLogRecord,
    BackgroundJobRecord,
    ControlEvaluationRecord,
    ControlProposalRecord,
    ControlRecord,
    EventEdgeRecord,
    EventRecord,
    ExceptionCaseRecord,
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
        # Persist the composite parent key before bulk event inserts. SQLAlchemy's
        # insert-many path does not infer object-level ordering without relationships.
        self.session.flush()
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
        values = {
            "tenant_id": tenant_id,
            "id": result.id,
            "run_id": result.source_run_id,
            "status": result.status,
            "mutation_count": result.mutation_count,
            "detected_count": result.detected_count,
            "missed_count": result.missed_count,
            "detection_rate": result.mutation_detection_rate,
            "false_positive_count": result.false_positive_count,
            "results": result.model_dump(mode="json"),
            "created_at": result.created_at,
        }
        if self.session.get_bind().dialect.name == "postgresql":
            statement = postgresql_insert(MutationTestRecord).values(**values)
            self.session.execute(
                statement.on_conflict_do_update(
                    index_elements=["tenant_id", "run_id", "id"],
                    set_={
                        "status": statement.excluded.status,
                        "mutation_count": statement.excluded.mutation_count,
                        "detected_count": statement.excluded.detected_count,
                        "missed_count": statement.excluded.missed_count,
                        "detection_rate": statement.excluded.detection_rate,
                        "false_positive_count": statement.excluded.false_positive_count,
                        "results": statement.excluded.results,
                        "created_at": statement.excluded.created_at,
                    },
                )
            )
            return
        self.session.merge(MutationTestRecord(**values))

    def list_runs(self, *, tenant_id: str, limit: int = 50) -> list[RunListItem]:
        records = self.session.scalars(
            select(RunRecord)
            .where(RunRecord.tenant_id == tenant_id)
            .order_by(
                RunRecord.completed_at.desc().nulls_last(),
                RunRecord.created_at.desc(),
            )
            .limit(limit)
        ).all()
        result: list[RunListItem] = []
        for record in records:
            manifest = record.manifest or {}
            counts = manifest.get("counts", {})
            if not isinstance(counts, dict):
                counts = {}
            result.append(
                RunListItem(
                    id=record.id,
                    name=record.name,
                    status=record.status,
                    source=(
                        "SEEDED"
                        if record.seed is not None
                        else str(manifest.get("source", "RAZORPAY"))
                    ),
                    transaction_count=int(
                        manifest.get("transaction_count", counts.get("payments", 0))
                    ),
                    event_count=int(manifest.get("event_count", 0)),
                    control_evaluation_count=int(manifest.get("control_evaluation_count", 0)),
                    completed_at=record.completed_at,
                )
            )
        return result

    def live_run_summary(self, *, tenant_id: str, run_id: str) -> RunSummary | None:
        run = self.session.get(RunRecord, (tenant_id, run_id))
        if run is None:
            return None
        event_count = int(
            self.session.scalar(
                select(func.count())
                .select_from(EventRecord)
                .where(
                    EventRecord.tenant_id == tenant_id,
                    EventRecord.run_id == run_id,
                )
            )
            or 0
        )
        transaction_count = int(
            self.session.scalar(
                select(func.count())
                .select_from(EventRecord)
                .where(
                    EventRecord.tenant_id == tenant_id,
                    EventRecord.run_id == run_id,
                    EventRecord.event_type == "PAYMENT",
                )
            )
            or 0
        )
        relationship_count = int(
            self.session.scalar(
                select(func.count())
                .select_from(EventEdgeRecord)
                .where(
                    EventEdgeRecord.tenant_id == tenant_id,
                    EventEdgeRecord.run_id == run_id,
                )
            )
            or 0
        )
        evaluations = self.session.scalars(
            select(ControlEvaluationRecord).where(
                ControlEvaluationRecord.tenant_id == tenant_id,
                ControlEvaluationRecord.run_id == run_id,
            )
        ).all()
        outcomes = {status: 0 for status in ("PASS", "VIOLATION", "WARNING", "UNRESOLVED")}
        for evaluation in evaluations:
            outcomes[evaluation.outcome] = outcomes.get(evaluation.outcome, 0) + 1
        leakage = sum(
            (
                item.financial_impact or Decimal("0")
                for item in evaluations
                if item.outcome == "VIOLATION"
            ),
            Decimal("0"),
        )
        evaluation_control_ids = {item.control_id for item in evaluations}
        control_types = dict(
            self.session.execute(
                select(ControlRecord.id, ControlRecord.control_type).where(
                    ControlRecord.tenant_id == tenant_id,
                    ControlRecord.id.in_(evaluation_control_ids),
                )
            ).all()
        )
        cash_delayed = sum(
            (
                item.actual_amount or Decimal("0")
                for item in evaluations
                if item.outcome == "VIOLATION"
                and control_types.get(item.control_id) == ControlType.SETTLEMENT_SLA.value
            ),
            Decimal("0"),
        )
        manifest = run.manifest or {}
        return RunSummary(
            id=run.id,
            name=run.name,
            status=run.status,
            transaction_count=transaction_count,
            event_count=event_count,
            relationship_count=relationship_count,
            control_evaluation_count=len(evaluations),
            breakdown=StatusBreakdown(
                passed=outcomes["PASS"],
                violation=outcomes["VIOLATION"],
                warning=outcomes["WARNING"],
                unresolved=outcomes["UNRESOLVED"],
            ),
            precision=Decimal("0"),
            recall=Decimal("0"),
            false_positive_rate=Decimal("0"),
            verified_leakage=leakage,
            cash_delayed=money(cash_delayed),
            unresolved_count=outcomes["UNRESOLVED"],
            processing_ms=int(manifest.get("processing_ms", 0)),
            evaluations_per_second=int(manifest.get("evaluations_per_second", 0)),
            confusion_matrix=ConfusionMatrix(
                true_positive=0,
                false_positive=0,
                true_negative=0,
                false_negative=0,
            ),
            completed_at=run.completed_at or run.created_at,
            ground_truth_available=False,
            metrics_scope="LIVE_CONTROL_OUTCOMES_NO_GROUND_TRUTH",
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
        run_name: str = "Razorpay read-only sync",
        source: str = "RAZORPAY",
        manifest_extra: dict[str, Any] | None = None,
    ) -> None:
        run = self.session.get(RunRecord, (tenant_id, run_id))
        if run is None:
            run = RunRecord(
                tenant_id=tenant_id,
                id=run_id,
                name=run_name,
                status="COMPLETE",
                seed=None,
                manifest={},
                completed_at=synced_at,
                created_at=synced_at,
            )
            self.session.add(run)
            self.session.flush()
        run.status = "COMPLETE"
        run.name = run_name
        run.manifest = {
            "sync_id": sync_id,
            "source": source,
            "transaction_count": sum(event.event_type == "PAYMENT" for event in events),
            "event_count": len(events),
            "relationship_count": len(edges),
            **(manifest_extra or {}),
        }
        run.completed_at = synced_at
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

    def finalize_live_run(
        self,
        *,
        tenant_id: str,
        run_id: str,
        control_evaluation_count: int,
        processing_ms: int,
    ) -> None:
        run = self.session.get(RunRecord, (tenant_id, run_id))
        if run is None:
            raise ValueError("Run must exist before it can be finalized")
        manifest = dict(run.manifest or {})
        manifest["control_evaluation_count"] = control_evaluation_count
        manifest["processing_ms"] = processing_ms
        manifest["evaluations_per_second"] = (
            int(control_evaluation_count / (processing_ms / 1000)) if processing_ms > 0 else 0
        )
        run.manifest = manifest

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

    def list_controls(
        self,
        *,
        tenant_id: str,
        approved_only: bool = False,
    ) -> list[Control]:
        statement = select(ControlRecord).where(ControlRecord.tenant_id == tenant_id)
        if approved_only:
            statement = statement.where(ControlRecord.status == "APPROVED")
        records = self.session.scalars(
            statement.order_by(
                ControlRecord.logical_control_key,
                ControlRecord.version,
                ControlRecord.id,
            )
        ).all()
        return [Control.model_validate(record.definition) for record in records]

    def control_versions(self, *, tenant_id: str, logical_control_key: str) -> list[Control]:
        records = self.session.scalars(
            select(ControlRecord)
            .where(
                ControlRecord.tenant_id == tenant_id,
                ControlRecord.logical_control_key == logical_control_key,
                ControlRecord.status == "APPROVED",
            )
            .order_by(ControlRecord.version, ControlRecord.effective_from, ControlRecord.id)
        ).all()
        return [Control.model_validate(record.definition) for record in records]

    def effective_control(
        self,
        *,
        tenant_id: str,
        logical_control_key: str,
        at: Any,
    ) -> Control | None:
        instant = _utc_start(at)
        records = self.session.scalars(
            select(ControlRecord).where(
                ControlRecord.tenant_id == tenant_id,
                ControlRecord.logical_control_key == logical_control_key,
                ControlRecord.status == "APPROVED",
                ControlRecord.effective_from <= instant,
                or_(ControlRecord.effective_to.is_(None), ControlRecord.effective_to >= instant),
            )
        ).all()
        if len(records) > 1:
            raise ValueError("Multiple approved controls overlap for this effective date")
        return Control.model_validate(records[0].definition) if records else None

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

    def save_root_cause(self, root_cause: RootCause, *, run_id: str, tenant_id: str) -> None:
        self.session.merge(
            RootCauseRecord(
                tenant_id=tenant_id,
                id=root_cause.id,
                run_id=run_id,
                title=root_cause.title,
                category=root_cause.category,
                affected_count=root_cause.affected_count,
                verified_impact=root_cause.verified_impact,
                verification_status=root_cause.verification_status,
                evidence={
                    "expected": root_cause.expected_value,
                    "observed": root_cause.observed_value,
                    "first_seen": root_cause.first_seen.isoformat(),
                    "last_seen": root_cause.last_seen.isoformat(),
                    "primary_violation_count": root_cause.primary_violation_count,
                    "downstream_effect_count": root_cause.downstream_effect_count,
                    "hypothesis": root_cause.hypothesis,
                    "verification_evidence": root_cause.verification_evidence,
                },
            )
        )

    def list_violations(self, *, tenant_id: str, run_id: str) -> list[Violation]:
        records = self.session.scalars(
            select(ViolationRecord)
            .where(
                ViolationRecord.tenant_id == tenant_id,
                ViolationRecord.run_id == run_id,
            )
            .order_by(ViolationRecord.occurred_at, ViolationRecord.id)
        ).all()
        return [self._violation(record) for record in records]

    def violations_for_root(self, *, tenant_id: str, root_cause_id: str) -> list[Violation]:
        records = self.session.scalars(
            select(ViolationRecord)
            .where(
                ViolationRecord.tenant_id == tenant_id,
                ViolationRecord.root_cause_id == root_cause_id,
            )
            .order_by(ViolationRecord.occurred_at, ViolationRecord.id)
        ).all()
        return [self._violation(record) for record in records]

    def list_root_causes(self, *, tenant_id: str, run_id: str) -> list[RootCause]:
        records = self.session.scalars(
            select(RootCauseRecord)
            .where(
                RootCauseRecord.tenant_id == tenant_id,
                RootCauseRecord.run_id == run_id,
            )
            .order_by(RootCauseRecord.verified_impact.desc())
        ).all()
        return [self._root_cause(record) for record in records]

    def list_unresolved_matches(self, *, tenant_id: str, run_id: str) -> list[UnresolvedMatch]:
        records = self.session.scalars(
            select(EventRecord)
            .where(
                EventRecord.tenant_id == tenant_id,
                EventRecord.run_id == run_id,
                EventRecord.event_type == "UNRESOLVED_MATCH",
            )
            .order_by(EventRecord.occurred_at, EventRecord.id)
        ).all()
        result = []
        for record in records:
            payload = record.normalized_payload or {}
            settlement_id = str(payload.get("settlement_id") or record.external_id)
            result.append(
                UnresolvedMatch(
                    id=record.external_id,
                    payment_id=settlement_id,
                    status=EvaluationStatus.UNRESOLVED,
                    amount=record.amount,
                    settlement_id=settlement_id,
                    missing_evidence=(
                        "No deterministic bank match met the confidence and ambiguity thresholds."
                    ),
                    candidate_bank_references=[
                        str(item) for item in payload.get("candidate_bank_references", [])
                    ],
                    safe_conclusion="No EventEdge was created.",
                )
            )
        return result

    def get_root_cause(self, *, tenant_id: str, root_cause_id: str) -> RootCause | None:
        record = self.session.scalar(
            select(RootCauseRecord).where(
                RootCauseRecord.tenant_id == tenant_id,
                RootCauseRecord.id == root_cause_id,
            )
        )
        return self._root_cause(record) if record is not None else None

    def run_id_for_root(self, *, tenant_id: str, root_cause_id: str) -> str | None:
        return self.session.scalar(
            select(RootCauseRecord.run_id).where(
                RootCauseRecord.tenant_id == tenant_id,
                RootCauseRecord.id == root_cause_id,
            )
        )

    def mdr_investigation_context(
        self, *, tenant_id: str, run_id: str, payment_id: str
    ) -> dict[str, Any] | None:
        event = self.session.scalar(
            select(EventRecord).where(
                EventRecord.tenant_id == tenant_id,
                EventRecord.run_id == run_id,
                EventRecord.event_type == "PAYMENT",
                EventRecord.external_id == payment_id,
            )
        )
        evaluation = self.session.scalar(
            select(ControlEvaluationRecord)
            .where(
                ControlEvaluationRecord.tenant_id == tenant_id,
                ControlEvaluationRecord.run_id == run_id,
                ControlEvaluationRecord.target_type == "PAYMENT",
                ControlEvaluationRecord.target_id == payment_id,
                ControlEvaluationRecord.outcome == "VIOLATION",
            )
            .order_by(ControlEvaluationRecord.evaluated_at.desc())
            .limit(1)
        )
        if event is None or evaluation is None:
            return None
        control = self.session.get(
            ControlRecord,
            (tenant_id, evaluation.control_id),
        )
        if control is None:
            return None
        snapshot_ids = list(evaluation.source_snapshot_ids or [])
        observed_rate = (
            evaluation.actual_amount / event.amount
            if evaluation.actual_amount is not None and event.amount != 0
            else None
        )
        definition = control.definition or {}
        return {
            "razorpay_context": {
                "source": "immutable Razorpay source snapshots",
                "observed_rate": str(observed_rate) if observed_rate is not None else "",
                "difference_amount": (
                    str(evaluation.difference_amount)
                    if evaluation.difference_amount is not None
                    else ""
                ),
                "observed_value": str(evaluation.actual_amount or ""),
            },
            "contract_controls": [
                {
                    "control_id": control.id,
                    "version": str(control.version),
                    "rate": str(control.parameters.get("rate", "")),
                    "tolerance": str(control.parameters.get("tolerance", "")),
                    "effective_from": control.effective_from.date().isoformat(),
                    "effective_to": (
                        control.effective_to.date().isoformat() if control.effective_to else ""
                    ),
                    "source_clause": str(definition.get("source_clause", "")),
                }
            ],
            "evidence": [
                {
                    "id": f"EVIDENCE_CONTROL_{control.id}",
                    "kind": "APPROVED_CONTROL",
                    "source": control.id,
                    "summary": "Approved effective control loaded from the tenant registry.",
                    "verified": control.status == "APPROVED",
                    "attributes": {"control_version": str(control.version)},
                },
                {
                    "id": f"EVIDENCE_EVENT_{event.id}",
                    "kind": "OBSERVED_EVENT",
                    "source": event.id,
                    "summary": "Observed fee is linked to immutable source snapshots.",
                    "verified": bool(snapshot_ids),
                    "attributes": {
                        "source_snapshot_count": str(len(snapshot_ids)),
                        "input_fingerprint": evaluation.input_fingerprint,
                    },
                },
                {
                    "id": f"EVIDENCE_EVALUATION_{evaluation.id}",
                    "kind": "DETERMINISTIC_CALCULATION",
                    "source": evaluation.id,
                    "summary": "Deterministic MDR evaluation exceeded its currency tolerance.",
                    "verified": bool(snapshot_ids),
                    "attributes": {"engine_version": evaluation.engine_version},
                },
            ],
        }

    @staticmethod
    def _violation(record: ViolationRecord) -> Violation:
        evidence = record.evidence or {}
        return Violation(
            id=record.id,
            payment_id=record.payment_id,
            category=record.category,
            control_type=ControlType(record.control_type),
            expected=str(evidence.get("expected", "")),
            actual=str(evidence.get("actual", "")),
            difference=record.difference,
            financial_impact=record.financial_impact,
            confidence=record.confidence,
            root_cause_id=record.root_cause_id,
            occurred_at=record.occurred_at,
        )

    def _root_cause(self, record: RootCauseRecord) -> RootCause:
        evidence = record.evidence or {}
        related = self.violations_for_root(
            tenant_id=record.tenant_id,
            root_cause_id=record.id,
        )
        fallback = datetime.now(timezone.utc)
        first_seen = min((item.occurred_at for item in related), default=fallback)
        last_seen = max((item.occurred_at for item in related), default=first_seen)
        return RootCause(
            id=record.id,
            title=record.title,
            category=record.category,
            affected_count=record.affected_count,
            verified_impact=record.verified_impact,
            expected_value=str(evidence.get("expected", "")),
            observed_value=str(evidence.get("observed", "")),
            first_seen=evidence.get("first_seen", first_seen),
            last_seen=evidence.get("last_seen", last_seen),
            hypothesis=evidence.get("hypothesis"),
            verification_status=record.verification_status,
            verification_evidence=evidence.get("verification_evidence"),
            primary_violation_count=int(
                evidence.get("primary_violation_count", record.affected_count)
            ),
            downstream_effect_count=int(evidence.get("downstream_effect_count", 0)),
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


class ProposalConcurrencyError(RuntimeError):
    pass


class AgreementRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, *, tenant_id: str, agreement_id: str) -> Agreement | None:
        record = self.session.get(AgreementRecord, (tenant_id, agreement_id))
        return self._agreement(record) if record is not None else None

    def get_by_hash(self, *, tenant_id: str, content_hash: str) -> Agreement | None:
        record = self.session.scalar(
            select(AgreementRecord).where(
                AgreementRecord.tenant_id == tenant_id,
                AgreementRecord.content_hash == content_hash,
            )
        )
        return self._agreement(record) if record is not None else None

    def list(self, *, tenant_id: str, limit: int = 100) -> list[Agreement]:
        records = self.session.scalars(
            select(AgreementRecord)
            .where(AgreementRecord.tenant_id == tenant_id)
            .order_by(AgreementRecord.created_at.desc(), AgreementRecord.id)
            .limit(limit)
        ).all()
        return [self._agreement(record) for record in records]

    def create(
        self,
        *,
        tenant_id: str,
        agreement: Agreement,
        artifact_id: str,
        actor_id: str,
    ) -> Agreement:
        existing = self.get_by_hash(tenant_id=tenant_id, content_hash=agreement.content_hash)
        if existing is not None:
            return existing
        now = datetime.now(timezone.utc)
        self.session.add(
            AgreementRecord(
                tenant_id=tenant_id,
                id=agreement.id,
                artifact_id=artifact_id,
                merchant=agreement.merchant,
                title=agreement.title,
                status=agreement.status,
                effective_from=agreement.effective_from,
                effective_to=agreement.effective_to,
                source_type=agreement.source_type,
                content_hash=agreement.content_hash,
                created_by=actor_id,
                created_at=now,
                updated_at=now,
            )
        )
        self.session.add_all(
            AgreementClauseRecord(
                tenant_id=tenant_id,
                agreement_id=agreement.id,
                id=clause.id,
                reference=clause.reference,
                page=clause.page,
                heading=clause.heading,
                text=clause.text,
                effective_from=clause.effective_from,
                effective_to=clause.effective_to,
                source_type=clause.source_type,
                created_by=clause.created_by or actor_id,
                content_hash=sha256(clause.text.encode("utf-8")).hexdigest(),
                created_at=now,
            )
            for clause in agreement.clauses
        )
        self.session.flush()
        return agreement

    def add_clause(
        self,
        *,
        tenant_id: str,
        agreement_id: str,
        clause: AgreementClauseCreate,
        actor_id: str,
    ) -> AgreementClause:
        statement = select(AgreementRecord).where(
            AgreementRecord.tenant_id == tenant_id,
            AgreementRecord.id == agreement_id,
        )
        if self.session.bind is not None and self.session.bind.dialect.name == "postgresql":
            statement = statement.with_for_update()
        agreement = self.session.scalar(statement)
        if agreement is None:
            raise KeyError(agreement_id)

        effective_from = clause.effective_from or agreement.effective_from
        effective_to = (
            clause.effective_to if clause.effective_to is not None else agreement.effective_to
        )
        if effective_to is not None and effective_to < effective_from:
            raise ValueError("effective_to must not precede effective_from")
        if effective_from < agreement.effective_from:
            raise ValueError("Clause effective_from cannot precede the agreement")
        if agreement.effective_to is not None and (
            effective_to is None or effective_to > agreement.effective_to
        ):
            raise ValueError("Clause effective period must remain inside the agreement period")

        canonical = json.dumps(
            {
                "reference": clause.reference.strip(),
                "heading": clause.heading.strip(),
                "text": clause.text.strip(),
                "effective_from": effective_from.isoformat(),
                "effective_to": effective_to.isoformat() if effective_to else None,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        content_hash = sha256(canonical.encode("utf-8")).hexdigest()
        existing = self.session.scalar(
            select(AgreementClauseRecord).where(
                AgreementClauseRecord.tenant_id == tenant_id,
                AgreementClauseRecord.agreement_id == agreement_id,
                AgreementClauseRecord.content_hash == content_hash,
            )
        )
        if existing is not None:
            return self._clause(existing)

        created = AgreementClauseRecord(
            tenant_id=tenant_id,
            agreement_id=agreement_id,
            id=f"CLAUSE_MANUAL_{content_hash[:20].upper()}",
            reference=clause.reference.strip(),
            page=0,
            heading=clause.heading.strip(),
            text=clause.text.strip(),
            effective_from=effective_from,
            effective_to=effective_to,
            source_type="MANUAL_ENTRY",
            created_by=actor_id,
            content_hash=content_hash,
            created_at=datetime.now(timezone.utc),
        )
        self.session.add(created)
        agreement.status = "EXTRACTED"
        agreement.updated_at = datetime.now(timezone.utc)
        self.session.flush()
        return self._clause(created)

    def list_proposals(self, *, tenant_id: str, agreement_id: str) -> list[ControlProposal]:
        records = self.session.scalars(
            select(ControlProposalRecord)
            .where(
                ControlProposalRecord.tenant_id == tenant_id,
                ControlProposalRecord.agreement_id == agreement_id,
            )
            .order_by(ControlProposalRecord.created_at, ControlProposalRecord.id)
        ).all()
        return [self._proposal(record) for record in records]

    def get_proposal(self, *, tenant_id: str, proposal_id: str) -> ControlProposal | None:
        record = self.session.get(ControlProposalRecord, (tenant_id, proposal_id))
        return self._proposal(record) if record is not None else None

    def add_proposal(
        self,
        *,
        tenant_id: str,
        proposal: ControlProposal,
        execution_id: str | None,
        actor_id: str,
    ) -> ControlProposal:
        if self.get(tenant_id=tenant_id, agreement_id=proposal.agreement_id) is None:
            raise KeyError(proposal.agreement_id)
        existing = self.get_proposal(tenant_id=tenant_id, proposal_id=proposal.id)
        if existing is not None:
            return existing
        now = datetime.now(timezone.utc)
        self.session.add(
            ControlProposalRecord(
                tenant_id=tenant_id,
                id=proposal.id,
                agreement_id=proposal.agreement_id,
                clause_id=proposal.clause_id,
                control_id=proposal.control_id,
                status=proposal.status,
                confidence=proposal.confidence,
                rationale=proposal.rationale,
                source_excerpt=proposal.source_excerpt,
                extraction_method=proposal.extraction_method,
                proposed_control=proposal.proposed_control.model_dump(mode="json"),
                execution_id=execution_id,
                version=1,
                verification_status="NOT_RUN",
                verification_result=None,
                verified_by=None,
                verified_at=None,
                approved_by=None,
                approved_at=None,
                created_by=actor_id,
                created_at=now,
                updated_at=now,
            )
        )
        self.session.flush()
        return proposal

    def replace_proposals(
        self,
        *,
        tenant_id: str,
        agreement_id: str,
        proposals: list[ControlProposal],
        execution_id: str,
        actor_id: str,
    ) -> list[ControlProposal]:
        agreement_statement = select(AgreementRecord).where(
            AgreementRecord.tenant_id == tenant_id,
            AgreementRecord.id == agreement_id,
        )
        if self.session.bind is not None and self.session.bind.dialect.name == "postgresql":
            agreement_statement = agreement_statement.with_for_update()
        agreement = self.session.scalar(agreement_statement)
        if agreement is None:
            raise KeyError(agreement_id)
        immutable_control_ids = set(
            self.session.scalars(
                select(ControlProposalRecord.control_id).where(
                    ControlProposalRecord.tenant_id == tenant_id,
                    ControlProposalRecord.agreement_id == agreement_id,
                    ControlProposalRecord.status.in_(["APPROVED", "REJECTED"]),
                )
            ).all()
        )
        self.session.execute(
            delete(ControlProposalRecord).where(
                ControlProposalRecord.tenant_id == tenant_id,
                ControlProposalRecord.agreement_id == agreement_id,
                ControlProposalRecord.status.in_(["DRAFT", "REVIEW_REQUIRED"]),
            )
        )
        now = datetime.now(timezone.utc)
        for proposal in proposals:
            if proposal.control_id in immutable_control_ids:
                continue
            self.session.add(
                ControlProposalRecord(
                    tenant_id=tenant_id,
                    id=proposal.id,
                    agreement_id=agreement_id,
                    clause_id=proposal.clause_id,
                    control_id=proposal.control_id,
                    status=proposal.status,
                    confidence=proposal.confidence,
                    rationale=proposal.rationale,
                    source_excerpt=proposal.source_excerpt,
                    extraction_method=proposal.extraction_method,
                    proposed_control=proposal.proposed_control.model_dump(mode="json"),
                    execution_id=execution_id,
                    version=1,
                    verification_status="NOT_RUN",
                    verification_result=None,
                    verified_by=None,
                    verified_at=None,
                    approved_by=None,
                    approved_at=None,
                    created_by=actor_id,
                    created_at=now,
                    updated_at=now,
                )
            )
        agreement.status = "EXTRACTED"
        agreement.updated_at = now
        self.session.flush()
        return proposals

    def verify_proposal(
        self,
        *,
        tenant_id: str,
        proposal_id: str,
        actor_id: str,
    ) -> ControlProposalVerification:
        record = self._locked_proposal(tenant_id=tenant_id, proposal_id=proposal_id)
        if record.status not in {"DRAFT", "REVIEW_REQUIRED"}:
            raise ValueError("Only draft proposals can be verified")
        control = Control.model_validate(record.proposed_control)
        verification = verify_draft_control(control)
        clause_exists = self.session.scalar(
            select(func.count())
            .select_from(AgreementClauseRecord)
            .where(
                AgreementClauseRecord.tenant_id == tenant_id,
                AgreementClauseRecord.agreement_id == record.agreement_id,
                AgreementClauseRecord.id == record.clause_id,
            )
        )
        checks = [
            *verification.checks,
            {
                "name": "agreement_clause_provenance",
                "status": "PASSED" if clause_exists else "FAILED",
                "detail": "The proposal cites an extracted clause in the same tenant agreement.",
            },
        ]
        status = "PASSED" if verification.status == "PASSED" and bool(clause_exists) else "FAILED"
        now = datetime.now(timezone.utc)
        result = {
            "status": status,
            "checks": checks,
            "mutation_probe_count": verification.mutation_probe_count,
            "detected_mutation_count": verification.detected_mutation_count,
            "input_fingerprint": verification.input_fingerprint,
        }
        record.verification_status = status
        record.verification_result = result
        record.verified_by = actor_id
        record.verified_at = now
        record.version += 1
        record.updated_at = now
        self.session.flush()
        return ControlProposalVerification(
            proposal_id=record.id,
            control_id=record.control_id,
            status=status,
            version=record.version,
            checks=checks,
            mutation_probe_count=verification.mutation_probe_count,
            detected_mutation_count=verification.detected_mutation_count,
            input_fingerprint=verification.input_fingerprint,
            verified_by=actor_id,
            verified_at=now,
        )

    def approve_proposal(
        self,
        *,
        tenant_id: str,
        proposal_id: str,
        expected_version: int,
        actor_id: str,
    ) -> Control:
        record = self._locked_proposal(tenant_id=tenant_id, proposal_id=proposal_id)
        if record.version != expected_version:
            raise ProposalConcurrencyError(
                "Proposal was updated by another reviewer; refresh before retrying"
            )
        if record.status not in {"DRAFT", "REVIEW_REQUIRED"}:
            raise ValueError("Only draft proposals can be approved")
        if record.verification_status != "PASSED" or not record.verification_result:
            raise ValueError("Deterministic control verification must pass before approval")
        if record.verified_by == actor_id:
            raise ValueError("Maker-checker requires a different verifier and approver")
        draft = Control.model_validate(record.proposed_control)
        overlaps = self.session.scalars(
            select(ControlRecord).where(
                ControlRecord.tenant_id == tenant_id,
                ControlRecord.logical_control_key == draft.logical_control_key,
                ControlRecord.status == "APPROVED",
                ControlRecord.effective_from <= _utc_start(draft.effective_to or date.max),
                or_(
                    ControlRecord.effective_to.is_(None),
                    ControlRecord.effective_to >= _utc_start(draft.effective_from),
                ),
            )
        ).all()
        if overlaps:
            raise ValueError("The proposed effective period overlaps an approved control version")
        now = datetime.now(timezone.utc)
        approved = draft.model_copy(update={"status": "APPROVED", "approved_at": now})
        RunRepository(self.session).save_controls([approved], tenant_id=tenant_id)
        record.status = "APPROVED"
        record.proposed_control = approved.model_dump(mode="json")
        record.approved_by = actor_id
        record.approved_at = now
        record.version += 1
        record.updated_at = now
        self.session.flush()
        return approved

    def _locked_proposal(
        self,
        *,
        tenant_id: str,
        proposal_id: str,
    ) -> ControlProposalRecord:
        statement = select(ControlProposalRecord).where(
            ControlProposalRecord.tenant_id == tenant_id,
            ControlProposalRecord.id == proposal_id,
        )
        if self.session.bind is not None and self.session.bind.dialect.name == "postgresql":
            statement = statement.with_for_update()
        record = self.session.scalar(statement)
        if record is None:
            raise KeyError(proposal_id)
        return record

    def _agreement(self, record: AgreementRecord) -> Agreement:
        clauses = self.session.scalars(
            select(AgreementClauseRecord)
            .where(
                AgreementClauseRecord.tenant_id == record.tenant_id,
                AgreementClauseRecord.agreement_id == record.id,
            )
            .order_by(AgreementClauseRecord.page, AgreementClauseRecord.id)
        ).all()
        return Agreement(
            id=record.id,
            merchant=record.merchant,
            title=record.title,
            status=record.status,
            effective_from=record.effective_from,
            effective_to=record.effective_to,
            source_type=record.source_type,
            content_hash=record.content_hash,
            clauses=[self._clause(clause) for clause in clauses],
        )

    @staticmethod
    def _clause(clause: AgreementClauseRecord) -> AgreementClause:
        return AgreementClause(
            id=clause.id,
            reference=clause.reference,
            page=clause.page,
            heading=clause.heading,
            text=clause.text,
            effective_from=clause.effective_from,
            effective_to=clause.effective_to,
            source_type=clause.source_type,
            created_by=clause.created_by,
        )

    @staticmethod
    def _proposal(record: ControlProposalRecord) -> ControlProposal:
        return ControlProposal(
            id=record.id,
            agreement_id=record.agreement_id,
            clause_id=record.clause_id,
            control_id=record.control_id,
            status=record.status,
            confidence=record.confidence,
            rationale=record.rationale,
            source_excerpt=record.source_excerpt,
            extraction_method=record.extraction_method,
            proposed_control=Control.model_validate(record.proposed_control),
            version=record.version,
            verification_status=record.verification_status,
            verification_result=record.verification_result,
            verified_by=record.verified_by,
            verified_at=record.verified_at,
            approved_by=record.approved_by,
            approved_at=record.approved_at,
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

    def capture_many(
        self,
        *,
        tenant_id: str,
        items: list[dict[str, Any]],
    ) -> list[SourceSnapshotRecord]:
        """Idempotently capture a batch with one lookup and one write round trip."""

        if not items:
            return []
        prepared: list[tuple[tuple[str, str, str], dict[str, Any]]] = []
        for item in items:
            payload = item["payload"]
            canonical = json.dumps(
                payload,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
                allow_nan=False,
            ).encode("utf-8")
            fingerprint = sha256(canonical).hexdigest()
            key = (item["resource_type"], item["external_id"], fingerprint)
            prepared.append(
                (
                    key,
                    {
                        "tenant_id": tenant_id,
                        "id": f"SRC_{uuid4().hex.upper()}",
                        "run_id": item.get("run_id"),
                        "job_id": item.get("job_id"),
                        "source_system": item["source_system"],
                        "resource_type": item["resource_type"],
                        "external_id": item["external_id"],
                        "source_version": item.get("source_version"),
                        "schema_version": item.get("schema_version", 1),
                        "content_sha256": fingerprint,
                        "payload": payload,
                        "provenance": item["provenance"],
                        "source_created_at": item.get("source_created_at"),
                        "captured_at": item["captured_at"],
                        "created_at": datetime.now(timezone.utc),
                    },
                )
            )
        fingerprints = {key[2] for key, _ in prepared}
        existing = self.session.scalars(
            select(SourceSnapshotRecord).where(
                SourceSnapshotRecord.tenant_id == tenant_id,
                SourceSnapshotRecord.source_system == items[0]["source_system"],
                SourceSnapshotRecord.content_sha256.in_(fingerprints),
            )
        ).all()
        record_by_key = {
            (record.resource_type, record.external_id, record.content_sha256): record
            for record in existing
        }
        missing_by_key = {key: values for key, values in prepared if key not in record_by_key}
        if missing_by_key:
            if self.session.bind is not None and self.session.bind.dialect.name == "postgresql":
                statement = postgresql_insert(SourceSnapshotRecord).values(
                    list(missing_by_key.values())
                )
                self.session.execute(
                    statement.on_conflict_do_nothing(
                        constraint="uq_source_snapshots_tenant_fingerprint"
                    )
                )
            else:
                self.session.add_all(
                    SourceSnapshotRecord(**values) for values in missing_by_key.values()
                )
            self.session.flush()
            records = self.session.scalars(
                select(SourceSnapshotRecord).where(
                    SourceSnapshotRecord.tenant_id == tenant_id,
                    SourceSnapshotRecord.source_system == items[0]["source_system"],
                    SourceSnapshotRecord.content_sha256.in_(fingerprints),
                )
            ).all()
            record_by_key = {
                (record.resource_type, record.external_id, record.content_sha256): record
                for record in records
            }
        return [record_by_key[key] for key, _ in prepared]


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
        self.session.execute(
            update(BackgroundJobRecord)
            .where(
                BackgroundJobRecord.tenant_id == tenant_id,
                BackgroundJobRecord.status == "RUNNING",
                BackgroundJobRecord.lease_expires_at < now,
                BackgroundJobRecord.attempt_count >= BackgroundJobRecord.max_attempts,
            )
            .values(
                status="FAILED",
                error={
                    "code": "LEASE_EXHAUSTED",
                    "message": "The job exhausted its attempts after worker lease expiry",
                },
                lease_owner=None,
                lease_expires_at=None,
                finished_at=now,
                updated_at=now,
            )
        )
        conditions = [
            BackgroundJobRecord.tenant_id == tenant_id,
            or_(
                and_(
                    BackgroundJobRecord.status.in_(["QUEUED", "RETRYABLE"]),
                    BackgroundJobRecord.available_at <= now,
                    or_(
                        BackgroundJobRecord.lease_expires_at.is_(None),
                        BackgroundJobRecord.lease_expires_at < now,
                    ),
                ),
                and_(
                    BackgroundJobRecord.status == "RUNNING",
                    BackgroundJobRecord.lease_expires_at < now,
                    BackgroundJobRecord.attempt_count < BackgroundJobRecord.max_attempts,
                ),
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

    def renew_lease(
        self,
        *,
        tenant_id: str,
        job_id: str,
        worker_id: str,
        lease_seconds: int,
    ) -> bool:
        now = datetime.now(timezone.utc)
        record = self.get(tenant_id=tenant_id, job_id=job_id)
        if record is None or record.status != "RUNNING" or record.lease_owner != worker_id:
            return False
        record.leased_at = now
        record.lease_expires_at = now + timedelta(seconds=lease_seconds)
        record.updated_at = now
        return True

    @staticmethod
    def _require_lease(record: BackgroundJobRecord, worker_id: str) -> None:
        if record.status != "RUNNING" or record.lease_owner != worker_id:
            raise LeaseOwnershipError("Worker no longer owns the job lease")

    def succeed(
        self,
        record: BackgroundJobRecord,
        result: dict[str, Any],
        *,
        worker_id: str,
    ) -> None:
        self._require_lease(record, worker_id)
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
        worker_id: str,
        retry_delay_seconds: int = 30,
        retryable: bool = True,
    ) -> None:
        self._require_lease(record, worker_id)
        now = datetime.now(timezone.utc)
        will_retry = retryable and record.attempt_count < record.max_attempts
        record.status = "RETRYABLE" if will_retry else "FAILED"
        record.error = {"code": error_code, "message": safe_message}
        record.lease_owner = None
        record.lease_expires_at = None
        record.available_at = now + timedelta(seconds=retry_delay_seconds)
        record.finished_at = None if will_retry else now
        record.updated_at = now


class LeaseOwnershipError(RuntimeError):
    pass


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


class CaseConcurrencyError(RuntimeError):
    pass


class CaseRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_from_investigation(
        self,
        *,
        tenant_id: str,
        case_id: str,
        root_cause: RootCause,
        violations: list[Violation],
        evidence: list[CaseEvidence],
        actor_id: str,
    ) -> ExceptionCase:
        existing = self.get(tenant_id=tenant_id, case_id=case_id)
        if existing is not None:
            return existing
        if not violations:
            raise ValueError("A case requires at least one deterministic violation")
        primary = violations[0]
        now = datetime.now(timezone.utc)
        opened = CaseAuditEntry(
            from_status=None,
            to_status=ExceptionCaseStatus.OPEN,
            actor=actor_id,
            note="Case opened from a deterministically proven root-cause investigation.",
            occurred_at=now,
        )
        record = ExceptionCaseRecord(
            tenant_id=tenant_id,
            id=case_id,
            run_id=self._run_id_for_root(tenant_id, root_cause.id),
            root_cause_id=root_cause.id,
            title=root_cause.title,
            payment_id=primary.payment_id,
            primary_violation_id=primary.id,
            violation_ids=[item.id for item in violations],
            status=ExceptionCaseStatus.OPEN.value,
            verified_impact=root_cause.verified_impact,
            evidence=[item.model_dump(mode="json") for item in evidence],
            audit_trail=[opened.model_dump(mode="json")],
            resolution_note=None,
            version=1,
            created_at=now,
            updated_at=now,
        )
        self.session.add(record)
        self.session.flush()
        return self._case(record)

    def _run_id_for_root(self, tenant_id: str, root_cause_id: str) -> str:
        run_id = self.session.scalar(
            select(RootCauseRecord.run_id).where(
                RootCauseRecord.tenant_id == tenant_id,
                RootCauseRecord.id == root_cause_id,
            )
        )
        if run_id is None:
            raise ValueError("Root cause is not persisted for this tenant")
        return run_id

    def list_for_run(self, *, tenant_id: str, run_id: str) -> list[ExceptionCase]:
        records = self.session.scalars(
            select(ExceptionCaseRecord)
            .where(
                ExceptionCaseRecord.tenant_id == tenant_id,
                ExceptionCaseRecord.run_id == run_id,
            )
            .order_by(ExceptionCaseRecord.updated_at.desc())
        ).all()
        return [self._case(record) for record in records]

    def get(self, *, tenant_id: str, case_id: str) -> ExceptionCase | None:
        record = self.session.get(ExceptionCaseRecord, (tenant_id, case_id))
        return self._case(record) if record is not None else None

    def get_for_root(self, *, tenant_id: str, root_cause_id: str) -> ExceptionCase | None:
        record = self.session.scalar(
            select(ExceptionCaseRecord)
            .where(
                ExceptionCaseRecord.tenant_id == tenant_id,
                ExceptionCaseRecord.root_cause_id == root_cause_id,
            )
            .order_by(ExceptionCaseRecord.created_at.desc())
            .limit(1)
        )
        return self._case(record) if record is not None else None

    def transition(
        self,
        *,
        tenant_id: str,
        case_id: str,
        target: ExceptionCaseStatus,
        actor_id: str,
        note: str,
        expected_version: int,
    ) -> ExceptionCase:
        statement = select(ExceptionCaseRecord).where(
            ExceptionCaseRecord.tenant_id == tenant_id,
            ExceptionCaseRecord.id == case_id,
        )
        if self.session.bind is not None and self.session.bind.dialect.name == "postgresql":
            statement = statement.with_for_update()
        record = self.session.scalar(statement)
        if record is None:
            raise KeyError(case_id)
        if record.version != expected_version:
            raise CaseConcurrencyError(
                "Case was updated by another reviewer; refresh before retrying"
            )
        current = ExceptionCaseStatus(record.status)
        allowed = {
            ExceptionCaseStatus.OPEN: {ExceptionCaseStatus.VERIFIED},
            ExceptionCaseStatus.VERIFIED: {
                ExceptionCaseStatus.ESCALATED,
                ExceptionCaseStatus.RESOLVED,
            },
            ExceptionCaseStatus.ESCALATED: {ExceptionCaseStatus.RESOLVED},
            ExceptionCaseStatus.RESOLVED: set(),
        }
        if target not in allowed[current]:
            raise ValueError(f"Cannot transition {current.value} to {target.value}")
        if target == ExceptionCaseStatus.VERIFIED:
            if not record.evidence or not all(
                bool(item.get("verified")) for item in record.evidence
            ):
                raise ValueError("Every evidence item must be deterministically verified")
            note = note or "Every evidence item was independently verified."
        elif not note.strip():
            raise ValueError("A note is required for escalation or resolution")
        now = datetime.now(timezone.utc)
        entry = CaseAuditEntry(
            from_status=current,
            to_status=target,
            actor=actor_id,
            note=note,
            occurred_at=now,
        )
        record.status = target.value
        record.audit_trail = [*record.audit_trail, entry.model_dump(mode="json")]
        record.resolution_note = note if target == ExceptionCaseStatus.RESOLVED else None
        record.version += 1
        record.updated_at = now
        self.session.flush()
        return self._case(record)

    @staticmethod
    def _case(record: ExceptionCaseRecord) -> ExceptionCase:
        return ExceptionCase(
            id=record.id,
            run_id=record.run_id,
            root_cause_id=record.root_cause_id,
            title=record.title,
            payment_id=record.payment_id,
            primary_violation_id=record.primary_violation_id,
            violation_ids=list(record.violation_ids),
            status=ExceptionCaseStatus(record.status),
            verified_impact=record.verified_impact,
            evidence=[CaseEvidence.model_validate(item) for item in record.evidence],
            audit_trail=[CaseAuditEntry.model_validate(item) for item in record.audit_trail],
            resolution_note=record.resolution_note,
            version=record.version,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )
