from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256

import httpx

from app.core.config import Settings, get_settings


class StorageNotConfiguredError(RuntimeError):
    pass


@dataclass(frozen=True)
class StoredObject:
    bucket: str
    object_path: str
    content_type: str
    byte_size: int
    sha256: str


class SupabaseStorage:
    """Backend-only adapter for a private Supabase Storage bucket."""

    def __init__(
        self,
        settings: Settings | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.transport = transport

    @property
    def configured(self) -> bool:
        return bool(
            self.settings.supabase_url and self.settings.supabase_service_role_key
        )

    async def upload(
        self,
        object_path: str,
        content: bytes,
        *,
        content_type: str,
        overwrite: bool = False,
    ) -> StoredObject:
        if not self.configured:
            raise StorageNotConfiguredError(
                "Configure SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY on the backend"
            )
        clean_path = object_path.strip("/")
        if not clean_path or ".." in clean_path.split("/"):
            raise ValueError("Storage object path must be a safe relative path")
        url = (
            f"{self.settings.supabase_url.rstrip('/')}/storage/v1/object/"
            f"{self.settings.supabase_storage_bucket}/{clean_path}"
        )
        headers = {
            "Authorization": f"Bearer {self.settings.supabase_service_role_key}",
            "apikey": self.settings.supabase_service_role_key,
            "Content-Type": content_type,
            "x-upsert": "true" if overwrite else "false",
        }
        async with httpx.AsyncClient(transport=self.transport, timeout=30) as client:
            response = await client.post(url, content=content, headers=headers)
            response.raise_for_status()
        return StoredObject(
            bucket=self.settings.supabase_storage_bucket,
            object_path=clean_path,
            content_type=content_type,
            byte_size=len(content),
            sha256=sha256(content).hexdigest(),
        )
