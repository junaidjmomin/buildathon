from __future__ import annotations

from datetime import datetime, time, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import delete
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
    ControlRecord,
    EventEdgeRecord,
    EventRecord,
    MutationTestRecord,
    RootCauseRecord,
    RunRecord,
    ViolationRecord,
)
from app.synthetic.generator import DEMO_SEED, SyntheticDataset


def _utc_start(value: Any) -> datetime:
    return datetime.combine(value, time.min, tzinfo=timezone.utc)


def _event(
    *,
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
    run_id: str, dataset: SyntheticDataset
) -> tuple[list[EventRecord], list[EventEdgeRecord]]:
    events: list[EventRecord] = []
    edges: list[EventEdgeRecord] = []
    seen_events: set[str] = set()

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
                event_id=settlement_event_id,
                run_id=run_id,
                source="RAZORPAY",
                external_id=payment.settlement_id,
                event_type="SETTLEMENT",
                amount=payment.actual_net,
                occurred_at=payment.settled_at,
                status="processed",
                payload={"settlement_id": payment.settlement_id},
            )
        )
        if bank_event_id is not None and payment.bank_credit is not None:
            append_event(
                _event(
                    event_id=bank_event_id,
                    run_id=run_id,
                    source="BANK",
                    external_id=payment.bank_txn_id or "",
                    event_type="BANK_CREDIT",
                    amount=payment.bank_credit,
                    occurred_at=payment.settled_at,
                    status="posted",
                    payload={"bank_txn_id": payment.bank_txn_id},
                )
            )
        if payment.refund_id is not None:
            append_event(
                _event(
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
    ) -> tuple[int, int]:
        self.session.execute(delete(RunRecord).where(RunRecord.id == run_id))
        self.session.flush()

        events, edges = canonical_records(run_id, dataset)
        self.session.add(
            RunRecord(
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

    def save_mutation_test(self, result: MutationTestSummary) -> None:
        self.session.merge(
            MutationTestRecord(
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
    ) -> None:
        if self.session.get(RunRecord, run_id) is None:
            self.session.add(
                RunRecord(
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
