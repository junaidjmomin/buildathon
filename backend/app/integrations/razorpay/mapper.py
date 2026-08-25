from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from app.domain.models import CanonicalEventEdge, FinancialEvent
from app.integrations.razorpay.schemas import ReconItem, SettlementItem


def _money_from_subunits(value: int) -> Decimal:
    return (Decimal(value) / Decimal("100")).quantize(Decimal("0.01"))


def _event_id(kind: str, external_id: str) -> str:
    return f"rzp:{kind.lower()}:{external_id}"


def map_recon_item(
    item: ReconItem, *, run_id: str, sync_id: str
) -> tuple[list[FinancialEvent], list[CanonicalEventEdge]]:
    raw = item.model_dump(mode="json")
    kind = item.type.upper()
    event_id = _event_id(kind, item.entity_id)
    primary = FinancialEvent(
        id=event_id,
        run_id=run_id,
        source="RAZORPAY",
        external_id=item.entity_id,
        event_type=kind,
        amount=_money_from_subunits(item.amount),
        currency=item.currency.upper(),
        timestamp=datetime.fromtimestamp(item.created_at, timezone.utc),
        status="settled" if item.settled else "unsettled",
        raw_payload=raw,
        normalized_payload={
            "sync_id": sync_id,
            "payment_id": item.payment_id,
            "order_id": item.order_id,
            "settlement_id": item.settlement_id,
            "settlement_utr": item.settlement_utr,
            "debit": str(_money_from_subunits(item.debit)),
            "credit": str(_money_from_subunits(item.credit)),
            "payment_method": item.method,
            "card_network": item.card_network,
            "card_type": item.card_type,
        },
    )
    events = [primary]
    edges: list[CanonicalEventEdge] = []

    if item.fee:
        fee_id = _event_id("FEE", item.entity_id)
        events.append(
            FinancialEvent(
                id=fee_id,
                run_id=run_id,
                source="RAZORPAY",
                external_id=f"{item.entity_id}:fee",
                event_type="FEE",
                amount=_money_from_subunits(item.fee),
                currency=item.currency.upper(),
                timestamp=primary.timestamp,
                raw_payload=raw,
                normalized_payload={"sync_id": sync_id, "base_event_id": event_id},
            )
        )
        edges.append(_edge(run_id, event_id, fee_id, "CHARGED_FEE", sync_id))
    if item.tax:
        tax_id = _event_id("TAX", item.entity_id)
        events.append(
            FinancialEvent(
                id=tax_id,
                run_id=run_id,
                source="RAZORPAY",
                external_id=f"{item.entity_id}:tax",
                event_type="TAX",
                amount=_money_from_subunits(item.tax),
                currency=item.currency.upper(),
                timestamp=primary.timestamp,
                raw_payload=raw,
                normalized_payload={"sync_id": sync_id, "base_event_id": event_id},
            )
        )
        edges.append(_edge(run_id, event_id, tax_id, "CHARGED_TAX", sync_id))
    if item.payment_id and kind == "REFUND":
        edges.append(
            _edge(run_id, _event_id("PAYMENT", item.payment_id), event_id, "REFUNDED_BY", sync_id)
        )
    if item.settlement_id:
        edges.append(
            _edge(
                run_id,
                event_id,
                _event_id("SETTLEMENT", item.settlement_id),
                "INCLUDED_IN",
                sync_id,
            )
        )
    return events, edges


def map_settlement(item: SettlementItem, *, run_id: str, sync_id: str) -> FinancialEvent:
    raw = item.model_dump(mode="json")
    return FinancialEvent(
        id=_event_id("SETTLEMENT", item.id),
        run_id=run_id,
        source="RAZORPAY",
        external_id=item.id,
        event_type="SETTLEMENT",
        amount=_money_from_subunits(item.amount),
        currency="INR",
        timestamp=datetime.fromtimestamp(item.created_at, timezone.utc),
        status=item.status,
        raw_payload=raw,
        normalized_payload={
            "sync_id": sync_id,
            "utr": item.utr,
            "fees": str(_money_from_subunits(item.fees)),
            "tax": str(_money_from_subunits(item.tax)),
        },
    )


def _edge(
    run_id: str, source: str, target: str, relationship: str, sync_id: str
) -> CanonicalEventEdge:
    return CanonicalEventEdge(
        id=f"edge:{relationship.lower()}:{source}:{target}",
        run_id=run_id,
        from_event_id=source,
        to_event_id=target,
        relationship=relationship,
        confidence=Decimal("1"),
        method="EXACT",
        evidence={"source": "razorpay", "sync_id": sync_id},
    )
