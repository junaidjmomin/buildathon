from __future__ import annotations

import os
from calendar import monthrange
from datetime import datetime, timezone

from app.domain.models import RazorpayConnectionStatus, RazorpaySyncRequest, RazorpaySyncSummary
from app.integrations.razorpay.client import RazorpayClient
from app.integrations.razorpay.mapper import map_recon_item, map_settlement
from app.integrations.razorpay.payments import fetch_payments
from app.integrations.razorpay.recon import fetch_reconciliation
from app.integrations.razorpay.refunds import fetch_refunds
from app.integrations.razorpay.settlements import fetch_settlements

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

    events = []
    edges = []
    for item in recon:
        mapped_events, mapped_edges = map_recon_item(item, run_id=run_id, sync_id=sync_id)
        events.extend(mapped_events)
        edges.extend(mapped_edges)
    events.extend(map_settlement(item, run_id=run_id, sync_id=sync_id) for item in settlements)
    last_sync = RazorpaySyncSummary(
        sync_id=sync_id,
        status="COMPLETE",
        payments_imported=len(payments),
        refunds_imported=len(refunds),
        settlements_imported=len(settlements),
        reconciliation_records_imported=len(recon),
        events_created=len(events),
        edges_created=len(edges),
        synced_at=datetime.now(timezone.utc),
    )
    return last_sync
