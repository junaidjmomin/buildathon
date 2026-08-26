from __future__ import annotations

import asyncio
from typing import Any
from urllib.parse import urlsplit

import httpx

from app.core.config import Settings, get_settings


class RazorpayNotConfiguredError(RuntimeError):
    pass


class RazorpayUpstreamError(RuntimeError):
    def __init__(self, code: str, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class RazorpayClient:
    """Backend-only, GET-only Razorpay client with bounded retries and payloads."""

    _ALLOWED_PATH_PREFIXES = (
        "/payments",
        "/refunds",
        "/settlements",
    )
    _RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

    def __init__(
        self,
        *,
        key_id: str | None = None,
        key_secret: str | None = None,
        base_url: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        settings: Settings | None = None,
    ) -> None:
        config = settings or get_settings()
        self.key_id = key_id or config.razorpay_key_id.get_secret_value()
        self.key_secret = key_secret or config.razorpay_key_secret.get_secret_value()
        self.base_url = (base_url or config.razorpay_api_base_url).rstrip("/")
        self.transport = transport
        self.timeout_seconds = config.razorpay_timeout_seconds
        self.max_retries = config.razorpay_max_retries
        self.max_pages = config.razorpay_max_pages
        self.max_records = config.razorpay_max_records
        self.max_response_bytes = config.razorpay_max_response_bytes
        parsed = urlsplit(self.base_url)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("Razorpay API base URL must be an absolute HTTPS URL")

    @property
    def configured(self) -> bool:
        return bool(self.key_id and self.key_secret)

    def _validate_path(self, path: str) -> None:
        if (
            not path.startswith("/")
            or ".." in path
            or "?" in path
            or "#" in path
            or not any(
                path == prefix or path.startswith(f"{prefix}/")
                for prefix in self._ALLOWED_PATH_PREFIXES
            )
        ):
            raise ValueError("Razorpay request path is outside the read-only allowlist")

    async def get(self, path: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.configured:
            raise RazorpayNotConfiguredError(
                "Configure RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET on the backend"
            )
        self._validate_path(path)
        timeout = httpx.Timeout(self.timeout_seconds, connect=min(self.timeout_seconds, 10))
        async with httpx.AsyncClient(
            base_url=self.base_url,
            auth=httpx.BasicAuth(self.key_id, self.key_secret),
            timeout=timeout,
            transport=self.transport,
            follow_redirects=False,
        ) as client:
            for attempt in range(self.max_retries + 1):
                try:
                    response = await client.get(path, params=params)
                except httpx.RequestError as exc:
                    if attempt >= self.max_retries:
                        raise RazorpayUpstreamError(
                            "RAZORPAY_NETWORK_ERROR",
                            "Razorpay could not be reached after bounded retries",
                            retryable=True,
                        ) from exc
                    await asyncio.sleep(0.5 * (2**attempt))
                    continue
                if response.status_code in self._RETRYABLE_STATUS_CODES:
                    if attempt >= self.max_retries:
                        raise RazorpayUpstreamError(
                            "RAZORPAY_RETRY_EXHAUSTED",
                            f"Razorpay returned HTTP {response.status_code} after bounded retries",
                            retryable=True,
                        )
                    retry_after = response.headers.get("retry-after", "")
                    delay = min(float(retry_after), 5.0) if retry_after.isdigit() else 0.5 * (
                        2**attempt
                    )
                    await asyncio.sleep(delay)
                    continue
                if response.is_redirect:
                    raise RazorpayUpstreamError(
                        "RAZORPAY_REDIRECT_REJECTED",
                        "Razorpay returned an unexpected redirect",
                        retryable=False,
                    )
                try:
                    response.raise_for_status()
                except httpx.HTTPStatusError as exc:
                    raise RazorpayUpstreamError(
                        "RAZORPAY_HTTP_ERROR",
                        f"Razorpay returned HTTP {response.status_code}",
                        retryable=False,
                    ) from exc
                content_length = response.headers.get("content-length")
                if content_length and int(content_length) > self.max_response_bytes:
                    raise RazorpayUpstreamError(
                        "RAZORPAY_RESPONSE_TOO_LARGE",
                        "Razorpay response exceeds the configured byte limit",
                        retryable=False,
                    )
                if len(response.content) > self.max_response_bytes:
                    raise RazorpayUpstreamError(
                        "RAZORPAY_RESPONSE_TOO_LARGE",
                        "Razorpay response exceeds the configured byte limit",
                        retryable=False,
                    )
                payload = response.json()
                if not isinstance(payload, dict):
                    raise RazorpayUpstreamError(
                        "RAZORPAY_INVALID_RESPONSE",
                        "Razorpay response root must be a JSON object",
                        retryable=False,
                    )
                return payload
        raise AssertionError("Unreachable Razorpay retry state")
