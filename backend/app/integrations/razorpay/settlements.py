from __future__ import annotations

from app.integrations.razorpay.client import RazorpayClient
from app.integrations.razorpay.schemas import SettlementItem


async def fetch_settlements(
    client: RazorpayClient, *, from_timestamp: int, to_timestamp: int
) -> list[SettlementItem]:
    items: list[SettlementItem] = []
    skip = 0
    while True:
        payload = await client.get(
            "/settlements",
            params={
                "from": from_timestamp,
                "to": to_timestamp,
                "count": 100,
                "skip": skip,
            },
        )
        page = [SettlementItem.model_validate(item) for item in payload.get("items", [])]
        items.extend(page)
        if len(page) < 100:
            break
        skip += len(page)
    return items


async def fetch_settlement(client: RazorpayClient, settlement_id: str) -> SettlementItem:
    return SettlementItem.model_validate(await client.get(f"/settlements/{settlement_id}"))
