from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from urllib.parse import quote

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
            self.settings.supabase_url
            and self.settings.supabase_service_role_key.get_secret_value()
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
        segments = clean_path.split("/")
        if (
            not clean_path
            or ".." in segments
            or any(not segment for segment in segments)
            or "\\" in clean_path
            or any(ord(character) < 32 for character in clean_path)
        ):
            raise ValueError("Storage object path must be a safe relative path")
        encoded_path = quote(clean_path, safe="/-_.")
        url = (
            f"{self.settings.supabase_url.rstrip('/')}/storage/v1/object/"
            f"{self.settings.supabase_storage_bucket}/{encoded_path}"
        )
        service_key = self.settings.supabase_service_role_key.get_secret_value()
        headers = {
            "Authorization": f"Bearer {service_key}",
            "apikey": service_key,
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
