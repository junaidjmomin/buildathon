from __future__ import annotations

import os
from typing import Any

import httpx


class RazorpayNotConfiguredError(RuntimeError):
    pass


class RazorpayClient:
    """Backend-only, GET-only Razorpay API client."""

    def __init__(
        self,
        *,
        key_id: str | None = None,
        key_secret: str | None = None,
        base_url: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.key_id = key_id or os.getenv("RAZORPAY_KEY_ID", "")
        self.key_secret = key_secret or os.getenv("RAZORPAY_KEY_SECRET", "")
        self.base_url = base_url or os.getenv(
            "RAZORPAY_API_BASE_URL", "https://api.razorpay.com/v1"
        )
        self.transport = transport

    @property
    def configured(self) -> bool:
        return bool(self.key_id and self.key_secret)

    async def get(self, path: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.configured:
            raise RazorpayNotConfiguredError(
                "Configure RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET on the backend"
            )
        async with httpx.AsyncClient(
            base_url=self.base_url,
            auth=httpx.BasicAuth(self.key_id, self.key_secret),
            timeout=httpx.Timeout(30),
            transport=self.transport,
        ) as client:
            response = await client.get(path, params=params)
            response.raise_for_status()
            return response.json()
