from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
from typing import Any

from app.controls.dsl import MdrRateParameters
from app.core.config import get_settings
from app.core.money import expected_fee, money
from app.domain.models import (
    Control,
    ControlType,
    EvaluationStatus,
    FinancialEvent,
    RazorpayConnectionStatus,
    RazorpaySyncRequest,
    RazorpaySyncSummary,
    Violation,
)
from app.integrations.razorpay.client import RazorpayClient
from app.integrations.razorpay.mapper import (
    map_payment,
    map_recon_item,
    map_refund,
    map_settlement,
)
from app.integrations.razorpay.payments import fetch_payments
from app.integrations.razorpay.recon import fetch_reconciliation
from app.integrations.razorpay.refunds import fetch_refunds
from app.integrations.razorpay.settlements import fetch_settlements
from app.persistence.database import session_scope
from app.persistence.repository import (
    ControlEvaluationRepository,
    JobRepository,
    RunRepository,
    SourceSnapshotRepository,
)
from app.services.governance import CONTROLS, governance

last_sync: RazorpaySyncSummary | None = None


@dataclass(frozen=True)
class LiveMdrEvaluation:
    evaluation_id: str
    event: FinancialEvent
    control: Control
    outcome: EvaluationStatus
    expected_amount: Decimal
    actual_amount: Decimal | None
    tolerance_amount: Decimal
    difference_amount: Decimal | None
    financial_impact: Decimal
    input_fingerprint: str
    violation: Violation | None


def connection_status(
    *, tenant_id: str, client: RazorpayClient | None = None
) -> RazorpayConnectionStatus:
    active = client or RazorpayClient()
    settings = get_settings()
    latest_status = last_sync.status if last_sync else "NEVER_SYNCED"
    latest_synced_at = last_sync.synced_at if last_sync else None
    verified_success = bool(last_sync and last_sync.status == "COMPLETE")
    if settings.database_url:
        with session_scope(tenant_id=tenant_id) as session:
            repository = JobRepository(session)
            latest = repository.latest(tenant_id=tenant_id, job_type="RAZORPAY_SYNC")
            latest_success = repository.latest(
                tenant_id=tenant_id,
                job_type="RAZORPAY_SYNC",
                status="SUCCEEDED",
            )
            if latest is not None:
                latest_status = latest.status
            if latest_success is not None:
                verified_success = True
                result = latest_success.result or {}
                latest_status = (
                    str(result.get("status", latest_status))
                    if latest is latest_success
                    else latest_status
                )
                latest_synced_at = _result_datetime(result.get("synced_at"))
                latest_synced_at = latest_synced_at or latest_success.finished_at
    return RazorpayConnectionStatus(
        configured=active.configured,
        mode=settings.razorpay_mode,
        connected=active.configured and verified_success,
        last_sync_status=latest_status,
        last_synced_at=latest_synced_at,
    )


def _result_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


async def sync_razorpay(
    request: RazorpaySyncRequest,
    *,
    run_id: str,
    tenant_id: str = "novacart_demo",
    job_id: str | None = None,
    client: RazorpayClient | None = None,
) -> RazorpaySyncSummary:
    global last_sync
    active = client or RazorpayClient()
    start_day = request.day or 1
    end_day = request.day or monthrange(request.year, request.month)[1]
    start = datetime(request.year, request.month, start_day, tzinfo=timezone.utc)
    end = datetime(request.year, request.month, end_day, 23, 59, 59, tzinfo=timezone.utc)
    sync_id = f"RZP_SYNC_{request.year}{request.month:02d}{request.day or 0:02d}"

    recon = await fetch_reconciliation(
        active, year=request.year, month=request.month, day=request.day
    )
    payments = await fetch_payments(
        active, from_timestamp=int(start.timestamp()), to_timestamp=int(end.timestamp())
    )
    refunds = await fetch_refunds(
        active, from_timestamp=int(start.timestamp()), to_timestamp=int(end.timestamp())
    )
    settlements = await fetch_settlements(
        active, from_timestamp=int(start.timestamp()), to_timestamp=int(end.timestamp())
    )

    event_index: dict[str, FinancialEvent] = {}
    for item in payments:
        event = map_payment(item, run_id=run_id, sync_id=sync_id)
        event_index[event.id] = event
    edge_index = {}
    for item in refunds:
        event, edge = map_refund(item, run_id=run_id, sync_id=sync_id)
        event_index[event.id] = event
        edge_index[edge.id] = edge
    for item in recon:
        mapped_events, mapped_edges = map_recon_item(item, run_id=run_id, sync_id=sync_id)
        for event in mapped_events:
            event_index[event.id] = _merge_event(event_index.get(event.id), event)
        edge_index.update((edge.id, edge) for edge in mapped_edges)
    for item in settlements:
        event = map_settlement(item, run_id=run_id, sync_id=sync_id)
        event_index[event.id] = event
    synced_at = datetime.now(timezone.utc)
    unresolved_references = 0
    for edge_id, edge in list(edge_index.items()):
        missing_ids = [
            endpoint
            for endpoint in (edge.from_event_id, edge.to_event_id)
            if endpoint not in event_index
        ]
        if not missing_ids:
            continue
        unresolved_references += len(missing_ids)
        del edge_index[edge_id]
        digest = sha256(f"{sync_id}:{edge.id}".encode()).hexdigest()[:20]
        unresolved_id = f"rzp:unresolved:{digest}"
        event_index[unresolved_id] = FinancialEvent(
            id=unresolved_id,
            run_id=run_id,
            source="RAZORPAY",
            external_id=digest,
            event_type="UNRESOLVED_MATCH",
            amount=Decimal("0.00"),
            currency="INR",
            timestamp=synced_at,
            status="unresolved",
            raw_payload={},
            normalized_payload={
                "sync_id": sync_id,
                "reason": "Referenced entity was outside the requested sync window",
                "missing_event_ids": missing_ids,
                "rejected_edge_id": edge.id,
                "relationship": edge.relationship,
                "decision": "UNRESOLVED",
            },
        )
    persistence_status = "IN_MEMORY"
    persisted_events = list(event_index.values())
    evaluations = _build_mdr_evaluations(persisted_events)
    if get_settings().database_url:
        with session_scope(tenant_id=tenant_id) as session:
            snapshot_repository = SourceSnapshotRepository(session)
            snapshot_ids: dict[str, list[str]] = {}
            provenance = {
                "sync_id": sync_id,
                "job_id": job_id,
                "read_only": True,
                "window_start": start.isoformat(),
                "window_end": end.isoformat(),
            }
            sources: list[tuple[str, str, Any]] = [
                *(("payment", "/payments", item) for item in payments),
                *(("refund", "/refunds", item) for item in refunds),
                *(("settlement", "/settlements", item) for item in settlements),
                *(("reconciliation", "/settlements/recon/combined", item) for item in recon),
            ]
            for resource_type, endpoint, item in sources:
                external_id = getattr(item, "id", None) or item.entity_id
                created_epoch = getattr(item, "created_at", None)
                snapshot = snapshot_repository.capture(
                    tenant_id=tenant_id,
                    source_system="RAZORPAY",
                    resource_type=resource_type,
                    external_id=external_id,
                    payload=item.model_dump(mode="json"),
                    provenance={**provenance, "endpoint": endpoint},
                    captured_at=synced_at,
                    run_id=run_id,
                    job_id=job_id,
                    source_created_at=(
                        datetime.fromtimestamp(created_epoch, timezone.utc)
                        if created_epoch is not None
                        else None
                    ),
                )
                snapshot_ids.setdefault(external_id, []).append(snapshot.id)
            persisted_events = []
            for event in event_index.values():
                base_external_id = event.external_id.split(":", 1)[0]
                persisted_events.append(
                    event.model_copy(
                        update={
                            "normalized_payload": {
                                **event.normalized_payload,
                                "source_snapshot_ids": snapshot_ids.get(base_external_id, []),
                            }
                        }
                    )
                )
            RunRepository(session).save_canonical_sync(
                run_id=run_id,
                sync_id=sync_id,
                synced_at=synced_at,
                events=persisted_events,
                edges=list(edge_index.values()),
                tenant_id=tenant_id,
            )
            run_repository = RunRepository(session)
            run_repository.save_controls(CONTROLS, tenant_id=tenant_id)
            session.flush()
            evaluations = _build_mdr_evaluations(persisted_events)
            evaluation_repository = ControlEvaluationRepository(session)
            for evaluation in evaluations:
                snapshot_ids = evaluation.event.normalized_payload.get("source_snapshot_ids", [])
                evaluation_repository.save(
                    tenant_id=tenant_id,
                    run_id=run_id,
                    evaluation_id=evaluation.evaluation_id,
                    control_id=evaluation.control.id,
                    control_version=evaluation.control.version,
                    target_type="PAYMENT",
                    target_id=evaluation.event.external_id,
                    outcome=evaluation.outcome.value,
                    expected_amount=evaluation.expected_amount,
                    actual_amount=evaluation.actual_amount,
                    tolerance_amount=evaluation.tolerance_amount,
                    difference_amount=evaluation.difference_amount,
                    financial_impact=evaluation.financial_impact,
                    confidence=Decimal("1"),
                    input_fingerprint=evaluation.input_fingerprint,
                    engine_version="sl3dge-deterministic-v1",
                    source_snapshot_ids=(
                        list(snapshot_ids) if isinstance(snapshot_ids, list) else []
                    ),
                    evidence={
                        "event_id": evaluation.event.id,
                        "calculation": (
                            f"{evaluation.event.amount} * {evaluation.control.parameters['rate']}"
                        ),
                        "authority": "DETERMINISTIC",
                    },
                    evaluated_at=synced_at,
                )
                if evaluation.violation is not None:
                    run_repository.save_violation(
                        evaluation.violation,
                        run_id=run_id,
                        tenant_id=tenant_id,
                    )
        persistence_status = "POSTGRES"
    last_sync = RazorpaySyncSummary(
        sync_id=sync_id,
        status="COMPLETE",
        payments_imported=len(payments),
        refunds_imported=len(refunds),
        settlements_imported=len(settlements),
        reconciliation_records_imported=len(recon),
        events_created=len(event_index),
        edges_created=len(edge_index),
        unresolved_references=unresolved_references,
        control_evaluations_created=len(evaluations),
        violations_created=sum(item.violation is not None for item in evaluations),
        synced_at=synced_at,
        persistence_status=persistence_status,
    )
    return last_sync


def _merge_event(existing: FinancialEvent | None, incoming: FinancialEvent) -> FinancialEvent:
    if existing is None:
        return incoming
    conflicts: list[str] = []
    if existing.amount != incoming.amount:
        conflicts.append("amount")
    if existing.currency != incoming.currency:
        conflicts.append("currency")
    return existing.model_copy(
        update={
            "status": "unresolved" if conflicts else (existing.status or incoming.status),
            "raw_payload": {
                "direct_view": existing.raw_payload,
                "reconciliation_view": incoming.raw_payload,
            },
            "normalized_payload": {
                **existing.normalized_payload,
                **incoming.normalized_payload,
                "source_views": ["direct_api", "reconciliation"],
                "source_conflicts": conflicts,
            },
        }
    )


def _build_mdr_evaluations(events: list[FinancialEvent]) -> list[LiveMdrEvaluation]:
    evaluations: list[LiveMdrEvaluation] = []
    for event in events:
        if event.event_type != "PAYMENT":
            continue
        normalized = event.normalized_payload
        method = normalized.get("method") or normalized.get("payment_method")
        if method != "card":
            continue
        international = normalized.get("international")
        if international is True:
            continue
        try:
            control = governance.effective_control("DOMESTIC_CARD_MDR", event.timestamp.date())
        except KeyError:
            continue
        parameters = MdrRateParameters.model_validate(control.parameters)
        expected = expected_fee(event.amount, parameters.rate)
        raw_actual = normalized.get("fee")
        try:
            actual = Decimal(str(raw_actual)) if raw_actual is not None else None
        except Exception:
            actual = None
        difference = money(actual - expected) if actual is not None else None
        unresolved = international is None or actual is None or event.status == "unresolved"
        if unresolved:
            outcome = EvaluationStatus.UNRESOLVED
        elif abs(difference or Decimal("0")) > parameters.tolerance:
            outcome = EvaluationStatus.VIOLATION
        else:
            outcome = EvaluationStatus.PASS
        impact = (
            max(difference or Decimal("0"), Decimal("0"))
            if outcome == EvaluationStatus.VIOLATION
            else Decimal("0")
        )
        fingerprint_source = "|".join(
            [
                event.id,
                str(event.amount),
                str(actual),
                control.id,
                str(control.version),
                str(parameters.rate),
                str(parameters.tolerance),
            ]
        )
        fingerprint = sha256(fingerprint_source.encode()).hexdigest()
        evaluation_id = f"EVAL_MDR_{fingerprint[:24].upper()}"
        violation = None
        if outcome == EvaluationStatus.VIOLATION:
            violation = Violation(
                id=f"V_MDR_{fingerprint[:24].upper()}",
                payment_id=event.external_id,
                category="MDR rate deviation",
                control_type=ControlType.MDR_RATE,
                expected=str(expected),
                actual=str(actual),
                difference=difference or Decimal("0"),
                financial_impact=impact,
                confidence=Decimal("1"),
                status=EvaluationStatus.VIOLATION,
                occurred_at=event.timestamp,
            )
        evaluations.append(
            LiveMdrEvaluation(
                evaluation_id=evaluation_id,
                event=event,
                control=control,
                outcome=outcome,
                expected_amount=expected,
                actual_amount=actual,
                tolerance_amount=parameters.tolerance,
                difference_amount=difference,
                financial_impact=impact,
                input_fingerprint=fingerprint,
                violation=violation,
            )
        )
    return evaluations
