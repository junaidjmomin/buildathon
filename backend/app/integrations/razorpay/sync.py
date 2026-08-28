from __future__ import annotations

from calendar import monthrange
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
from time import perf_counter
from typing import Any

from app.controls.live import LiveControlEvaluation, build_live_control_evaluations
from app.core.config import get_settings
from app.core.money import money
from app.domain.models import (
    Control,
    ControlType,
    FinancialEvent,
    RazorpayConnectionStatus,
    RazorpaySyncRequest,
    RazorpaySyncSummary,
    RootCause,
    Violation,
)
from app.integrations.razorpay.client import RazorpayClient
from app.integrations.razorpay.mapper import (
    RAZORPAY_MAPPING_VERSION,
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
from app.services.governance import CONTROLS

last_sync: RazorpaySyncSummary | None = None
REQUIRED_LIVE_CONTROL_KEYS = frozenset(
    {
        "DOMESTIC_CARD_MDR",
        "GST_ON_VALID_FEE",
        "CAPTURE_TO_SETTLEMENT_SLA",
        "SETTLEMENT_BANK_ARITHMETIC",
        "REFUND_PRINCIPAL_INTEGRITY",
    }
)


class IncompleteControlRegistryError(RuntimeError):
    pass


def _validate_live_control_registry(controls: list[Control]) -> None:
    available = {
        control.logical_control_key for control in controls if control.status == "APPROVED"
    }
    missing = sorted(REQUIRED_LIVE_CONTROL_KEYS - available)
    if missing:
        raise IncompleteControlRegistryError(
            "Tenant control registry is incomplete; missing approved controls: "
            + ", ".join(missing)
        )


def live_controls_for_tenant(tenant_id: str) -> list[Control]:
    settings = get_settings()
    if not settings.database_url:
        return list(CONTROLS)
    with session_scope(tenant_id=tenant_id) as session:
        persisted = RunRepository(session).list_controls(
            tenant_id=tenant_id,
            approved_only=True,
        )
    if persisted:
        if settings.environment in {"staging", "production"}:
            _validate_live_control_registry(persisted)
        return persisted
    if settings.environment in {"staging", "production"}:
        _validate_live_control_registry([])
    return list(CONTROLS)


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
    started = perf_counter()
    active = client or RazorpayClient()
    live_controls = live_controls_for_tenant(tenant_id)
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
                "mapping_version": RAZORPAY_MAPPING_VERSION,
                "reason": "Referenced entity was outside the requested sync window",
                "missing_event_ids": missing_ids,
                "rejected_edge_id": edge.id,
                "relationship": edge.relationship,
                "decision": "UNRESOLVED",
            },
        )
    persistence_status = "IN_MEMORY"
    persisted_events = list(event_index.values())
    evaluations = build_live_control_evaluations(
        persisted_events,
        list(edge_index.values()),
        live_controls,
    )
    if get_settings().database_url:
        with session_scope(tenant_id=tenant_id) as session:
            snapshot_repository = SourceSnapshotRepository(session)
            snapshot_ids: dict[str, list[str]] = {}
            snapshot_checksums: dict[str, list[str]] = {}
            provenance = {
                "sync_id": sync_id,
                "job_id": job_id,
                "mapping_version": RAZORPAY_MAPPING_VERSION,
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
                snapshot_checksums.setdefault(external_id, []).append(snapshot.content_sha256)
            persisted_events = []
            for event in event_index.values():
                base_external_id = event.external_id.split(":", 1)[0]
                persisted_events.append(
                    event.model_copy(
                        update={
                            "normalized_payload": {
                                **event.normalized_payload,
                                "source_snapshot_ids": snapshot_ids.get(base_external_id, []),
                                "source_snapshot_sha256": snapshot_checksums.get(
                                    base_external_id, []
                                ),
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
            run_repository.save_controls(live_controls, tenant_id=tenant_id)
            session.flush()
            evaluations = build_live_control_evaluations(
                persisted_events,
                list(edge_index.values()),
                live_controls,
            )
            evaluation_repository = ControlEvaluationRepository(session)
            mdr_evaluations = [
                item for item in evaluations if item.control.control_type == ControlType.MDR_RATE
            ]
            mdr_violations = [
                item.violation for item in mdr_evaluations if item.violation is not None
            ]
            root_cause = _mdr_root_cause(
                run_id=run_id,
                evaluations=mdr_evaluations,
                violations=mdr_violations,
            )
            for evaluation in evaluations:
                evaluation_repository.save(
                    tenant_id=tenant_id,
                    run_id=run_id,
                    evaluation_id=evaluation.evaluation_id,
                    control_id=evaluation.control.id,
                    control_version=evaluation.control.version,
                    target_type=evaluation.target_type,
                    target_id=evaluation.target_id,
                    outcome=evaluation.outcome.value,
                    expected_amount=evaluation.expected_amount,
                    actual_amount=evaluation.actual_amount,
                    tolerance_amount=evaluation.tolerance_amount,
                    difference_amount=evaluation.difference_amount,
                    financial_impact=evaluation.financial_impact,
                    confidence=Decimal("1"),
                    input_fingerprint=evaluation.input_fingerprint,
                    engine_version="sl3dge-deterministic-v1",
                    source_snapshot_ids=evaluation.source_snapshot_ids,
                    evidence=evaluation.evidence,
                    evaluated_at=synced_at,
                )
                if evaluation.violation is not None:
                    violation = evaluation.violation.model_copy(
                        update={
                            "root_cause_id": (
                                root_cause.id
                                if root_cause is not None
                                and evaluation.control.control_type == ControlType.MDR_RATE
                                else None
                            )
                        }
                    )
                    run_repository.save_violation(
                        violation,
                        run_id=run_id,
                        tenant_id=tenant_id,
                    )
            if root_cause is not None:
                run_repository.save_root_cause(
                    root_cause,
                    run_id=run_id,
                    tenant_id=tenant_id,
                )
            processing_ms = max(1, int((perf_counter() - started) * 1000))
            run_repository.finalize_live_run(
                tenant_id=tenant_id,
                run_id=run_id,
                control_evaluation_count=len(evaluations),
                processing_ms=processing_ms,
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


def _build_mdr_evaluations(events: list[FinancialEvent]) -> list[LiveControlEvaluation]:
    """Compatibility wrapper used by focused unit tests and investigation code."""

    return [
        evaluation
        for evaluation in build_live_control_evaluations(events, [], CONTROLS)
        if evaluation.control.control_type == ControlType.MDR_RATE
    ]


def _mdr_root_cause(
    *,
    run_id: str,
    evaluations: list[LiveControlEvaluation],
    violations: list[Violation],
) -> RootCause | None:
    if not violations:
        return None
    violating = [item for item in evaluations if item.violation is not None]
    observed_rates = sorted(
        {
            str(item.actual_amount / item.event.amount)
            for item in violating
            if item.actual_amount is not None and item.event.amount != 0
        }
    )
    expected_rates = sorted({str(item.control.parameters["rate"]) for item in violating})
    root_id = f"RC_RZP_MDR_{sha256(run_id.encode()).hexdigest()[:12].upper()}"
    return RootCause(
        id=root_id,
        title="Systemic Razorpay MDR rate deviation",
        category="MDR rate deviation",
        affected_count=len(violations),
        verified_impact=money(sum((item.financial_impact for item in violations), Decimal("0"))),
        expected_value=", ".join(expected_rates),
        observed_value=", ".join(observed_rates),
        first_seen=min(item.occurred_at for item in violations),
        last_seen=max(item.occurred_at for item in violations),
        verification_status="DETERMINISTICALLY_CLUSTERED",
        primary_violation_count=len(violations),
        downstream_effect_count=0,
    )
