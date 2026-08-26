from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.persistence.orm import ArtifactRecord
from app.storage.supabase import StoredObject, SupabaseStorage


class ArtifactService:
    def __init__(self, storage: SupabaseStorage, session: Session) -> None:
        self.storage = storage
        self.session = session

    async def store(
        self,
        *,
        artifact_id: str,
        kind: str,
        object_path: str,
        content: bytes,
        content_type: str,
        tenant_id: str,
        run_id: str | None = None,
        case_id: str | None = None,
        overwrite: bool = False,
    ) -> StoredObject:
        stored = await self.storage.upload(
            object_path,
            content,
            content_type=content_type,
            overwrite=overwrite,
        )
        self.session.merge(
            ArtifactRecord(
                tenant_id=tenant_id,
                id=artifact_id,
                run_id=run_id,
                case_id=case_id,
                kind=kind,
                bucket=stored.bucket,
                object_path=stored.object_path,
                content_type=stored.content_type,
                byte_size=stored.byte_size,
                sha256=stored.sha256,
                created_at=datetime.now(timezone.utc),
            )
        )
        return stored
