from __future__ import annotations

import os
from calendar import monthrange
from datetime import datetime, timezone
from decimal import Decimal

from app.core.config import get_settings
from app.domain.models import (
    FinancialEvent,
    RazorpayConnectionStatus,
    RazorpaySyncRequest,
    RazorpaySyncSummary,
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
from app.persistence.repository import RunRepository

last_sync: RazorpaySyncSummary | None = None


def connection_status(client: RazorpayClient | None = None) -> RazorpayConnectionStatus:
    active = client or RazorpayClient()
    return RazorpayConnectionStatus(
        configured=active.configured,
        mode=os.getenv("RAZORPAY_MODE", "test"),
        connected=active.configured,
        last_sync_status=last_sync.status if last_sync else "NEVER_SYNCED",
        last_synced_at=last_sync.synced_at if last_sync else None,
    )


async def sync_razorpay(
    request: RazorpaySyncRequest, *, run_id: str, client: RazorpayClient | None = None
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

    event_index = {
        event.id: event
        for event in (
            map_payment(item, run_id=run_id, sync_id=sync_id) for item in payments
        )
    }
    edge_index = {}
    for item in refunds:
        event, edge = map_refund(item, run_id=run_id, sync_id=sync_id)
        event_index[event.id] = event
        edge_index[edge.id] = edge
    for item in recon:
        mapped_events, mapped_edges = map_recon_item(item, run_id=run_id, sync_id=sync_id)
        event_index.update((event.id, event) for event in mapped_events)
        edge_index.update((edge.id, edge) for edge in mapped_edges)
    for item in settlements:
        event = map_settlement(item, run_id=run_id, sync_id=sync_id)
        event_index[event.id] = event
    synced_at = datetime.now(timezone.utc)
    referenced_ids = {
        endpoint
        for edge in edge_index.values()
        for endpoint in (edge.from_event_id, edge.to_event_id)
    }
    for missing_id in referenced_ids - event_index.keys():
        event_index[missing_id] = FinancialEvent(
            id=missing_id,
            run_id=run_id,
            source="RAZORPAY",
            external_id=missing_id.rsplit(":", 1)[-1],
            event_type="UNRESOLVED_REFERENCE",
            amount=Decimal("0.00"),
            currency="INR",
            timestamp=synced_at,
            status="unresolved",
            raw_payload={},
            normalized_payload={
                "sync_id": sync_id,
                "reason": "Referenced entity was outside the requested sync window.",
            },
        )
    persistence_status = "IN_MEMORY"
    if get_settings().database_url:
        with session_scope() as session:
            RunRepository(session).save_canonical_sync(
                run_id=run_id,
                sync_id=sync_id,
                synced_at=synced_at,
                events=list(event_index.values()),
                edges=list(edge_index.values()),
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
        synced_at=synced_at,
        persistence_status=persistence_status,
    )
    return last_sync
