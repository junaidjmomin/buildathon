from __future__ import annotations

from app.integrations.razorpay.client import RazorpayClient
from app.integrations.razorpay.schemas import RefundItem


async def fetch_refunds(
    client: RazorpayClient, *, from_timestamp: int, to_timestamp: int
) -> list[RefundItem]:
    items: list[RefundItem] = []
    skip = 0
    while True:
        payload = await client.get(
            "/refunds",
            params={
                "from": from_timestamp,
                "to": to_timestamp,
                "count": 100,
                "skip": skip,
            },
        )
        page = [RefundItem.model_validate(item) for item in payload.get("items", [])]
        items.extend(page)
        if len(page) < 100:
            break
        skip += len(page)
    return items
