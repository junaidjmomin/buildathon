from __future__ import annotations

from app.integrations.razorpay.client import RazorpayClient
from app.integrations.razorpay.schemas import PaymentItem


async def fetch_payments(
    client: RazorpayClient, *, from_timestamp: int, to_timestamp: int
) -> list[PaymentItem]:
    return await _fetch_pages(client, "/payments", from_timestamp, to_timestamp)


async def _fetch_pages(
    client: RazorpayClient, path: str, from_timestamp: int, to_timestamp: int
) -> list[PaymentItem]:
    items: list[PaymentItem] = []
    skip = 0
    while True:
        payload = await client.get(
            path,
            params={
                "from": from_timestamp,
                "to": to_timestamp,
                "count": 100,
                "skip": skip,
            },
        )
        page = [PaymentItem.model_validate(item) for item in payload.get("items", [])]
        items.extend(page)
        if len(page) < 100:
            break
        skip += len(page)
    return items
