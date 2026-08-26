from __future__ import annotations

from app.integrations.razorpay.client import RazorpayClient, RazorpayUpstreamError
from app.integrations.razorpay.schemas import ReconItem


async def fetch_reconciliation(
    client: RazorpayClient, *, year: int, month: int, day: int | None = None
) -> list[ReconItem]:
    items: list[ReconItem] = []
    skip = 0
    for _page_number in range(client.max_pages):
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
        if len(items) + len(page) > client.max_records:
            raise RazorpayUpstreamError(
                "RAZORPAY_RECORD_LIMIT",
                "Razorpay reconciliation exceeds the configured record limit",
                retryable=False,
            )
        items.extend(page)
        if len(page) < 1000:
            break
        skip += len(page)
    else:
        raise RazorpayUpstreamError(
            "RAZORPAY_PAGE_LIMIT",
            "Razorpay reconciliation exceeds the configured page limit",
            retryable=False,
        )
    return items
