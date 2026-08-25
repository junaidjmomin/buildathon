from __future__ import annotations

from app.integrations.razorpay.client import RazorpayClient
from app.integrations.razorpay.schemas import ReconItem


async def fetch_reconciliation(
    client: RazorpayClient, *, year: int, month: int, day: int | None = None
) -> list[ReconItem]:
    items: list[ReconItem] = []
    skip = 0
    while True:
        params: dict[str, int] = {
            "year": year,
            "month": month,
            "count": 1000,
            "skip": skip,
        }
        if day is not None:
            params["day"] = day
        payload = await client.get("/settlements/recon/combined", params=params)
        page = [ReconItem.model_validate(item) for item in payload.get("items", [])]
        items.extend(page)
        if len(page) < 1000:
            break
        skip += len(page)
    return items
