from __future__ import annotations

import argparse
import asyncio
import logging
import socket
from uuid import uuid4

from pydantic import ValidationError

from app.core.config import get_settings
from app.domain.models import RazorpaySyncRequest
from app.integrations.razorpay.client import (
    RazorpayNotConfiguredError,
    RazorpayUpstreamError,
)
from app.integrations.razorpay.sync import sync_razorpay
from app.persistence.database import session_scope
from app.persistence.repository import JobRepository, RunRepository

logger = logging.getLogger("sl3dge.worker")


async def process_one(*, tenant_id: str, worker_id: str) -> bool:
    settings = get_settings()
    with session_scope(tenant_id=tenant_id) as session:
        record = JobRepository(session).claim_next(
            tenant_id=tenant_id,
            worker_id=worker_id,
            lease_seconds=settings.worker_lease_seconds,
            job_types=["RAZORPAY_SYNC"],
        )
        if record is None:
            return False
        job_id = record.id
        payload = dict(record.payload)

    try:
        sync_request = RazorpaySyncRequest.model_validate(payload)
        summary = await sync_razorpay(
            sync_request,
            run_id=str(payload["run_id"]),
            tenant_id=tenant_id,
            job_id=job_id,
        )
    except RazorpayNotConfiguredError as exc:
        await _record_failure(
            tenant_id=tenant_id,
            job_id=job_id,
            code="RAZORPAY_NOT_CONFIGURED",
            message=str(exc),
            retryable=False,
        )
    except RazorpayUpstreamError as exc:
        await _record_failure(
            tenant_id=tenant_id,
            job_id=job_id,
            code=exc.code,
            message=str(exc),
            retryable=exc.retryable,
        )
    except (KeyError, ValidationError, ValueError) as exc:
        await _record_failure(
            tenant_id=tenant_id,
            job_id=job_id,
            code="INVALID_JOB_PAYLOAD",
            message="The queued Razorpay sync request is invalid",
            retryable=False,
        )
        logger.warning("Invalid job %s: %s", job_id, type(exc).__name__)
    except Exception:
        await _record_failure(
            tenant_id=tenant_id,
            job_id=job_id,
            code="WORKER_INTERNAL_ERROR",
            message="The worker encountered an unexpected error",
            retryable=True,
        )
        logger.exception("Unexpected failure while processing job %s", job_id)
    else:
        with session_scope(tenant_id=tenant_id) as session:
            repository = JobRepository(session)
            record = repository.get(tenant_id=tenant_id, job_id=job_id)
            if record is None:
                raise RuntimeError("Claimed job disappeared before completion")
            repository.succeed(record, summary.model_dump(mode="json"))
            RunRepository(session).write_audit(
                tenant_id=tenant_id,
                actor_id=worker_id,
                action="RAZORPAY_SYNC_JOB_COMPLETED",
                resource_type="background_job",
                resource_id=job_id,
                outcome="SUCCEEDED",
                details={"sync_id": summary.sync_id, "run_id": record.run_id},
            )
    return True


async def _record_failure(
    *,
    tenant_id: str,
    job_id: str,
    code: str,
    message: str,
    retryable: bool,
) -> None:
    with session_scope(tenant_id=tenant_id) as session:
        repository = JobRepository(session)
        record = repository.get(tenant_id=tenant_id, job_id=job_id)
        if record is None:
            raise RuntimeError("Claimed job disappeared before failure handling")
        repository.fail(
            record,
            error_code=code,
            safe_message=message,
            retryable=retryable,
        )
        RunRepository(session).write_audit(
            tenant_id=tenant_id,
            actor_id=record.lease_owner or "sl3dge-worker",
            action="RAZORPAY_SYNC_JOB_FAILED",
            resource_type="background_job",
            resource_id=job_id,
            outcome=record.status,
            details={"error_code": code, "retryable": retryable},
        )


async def run_worker(*, once: bool) -> None:
    settings = get_settings()
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL is required for the durable worker")
    worker_id = f"{socket.gethostname()}:{uuid4().hex[:12]}"
    while True:
        processed = False
        for tenant_id in settings.parsed_worker_tenant_ids:
            processed = await process_one(tenant_id=tenant_id, worker_id=worker_id) or processed
        if once:
            return
        if not processed:
            await asyncio.sleep(settings.worker_poll_seconds)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the durable sl3dge background worker")
    parser.add_argument("--once", action="store_true", help="Process at most one job per tenant")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    asyncio.run(run_worker(once=args.once))


if __name__ == "__main__":
    main()
