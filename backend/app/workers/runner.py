from __future__ import annotations

import argparse
import asyncio
import logging
import socket
from contextlib import suppress
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
from app.persistence.repository import JobRepository, LeaseOwnershipError, RunRepository

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
        summary = await _run_with_lease_heartbeat(
            sync_razorpay(
                sync_request,
                run_id=str(payload["run_id"]),
                tenant_id=tenant_id,
                job_id=job_id,
            ),
            tenant_id=tenant_id,
            job_id=job_id,
            worker_id=worker_id,
        )
    except RazorpayNotConfiguredError as exc:
        await _record_failure(
            tenant_id=tenant_id,
            job_id=job_id,
            code="RAZORPAY_NOT_CONFIGURED",
            message=str(exc),
            retryable=False,
            worker_id=worker_id,
        )
    except RazorpayUpstreamError as exc:
        await _record_failure(
            tenant_id=tenant_id,
            job_id=job_id,
            code=exc.code,
            message=str(exc),
            retryable=exc.retryable,
            worker_id=worker_id,
        )
    except (KeyError, ValidationError, ValueError) as exc:
        await _record_failure(
            tenant_id=tenant_id,
            job_id=job_id,
            code="INVALID_JOB_PAYLOAD",
            message="The queued Razorpay sync request is invalid",
            retryable=False,
            worker_id=worker_id,
        )
        logger.warning("Invalid job %s: %s", job_id, type(exc).__name__)
    except Exception:
        await _record_failure(
            tenant_id=tenant_id,
            job_id=job_id,
            code="WORKER_INTERNAL_ERROR",
            message="The worker encountered an unexpected error",
            retryable=True,
            worker_id=worker_id,
        )
        logger.exception("Unexpected failure while processing job %s", job_id)
    else:
        with session_scope(tenant_id=tenant_id) as session:
            repository = JobRepository(session)
            record = repository.get(tenant_id=tenant_id, job_id=job_id)
            if record is None:
                raise RuntimeError("Claimed job disappeared before completion")
            repository.succeed(
                record,
                summary.model_dump(mode="json"),
                worker_id=worker_id,
            )
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
    worker_id: str,
) -> None:
    with session_scope(tenant_id=tenant_id) as session:
        repository = JobRepository(session)
        record = repository.get(tenant_id=tenant_id, job_id=job_id)
        if record is None:
            raise RuntimeError("Claimed job disappeared before failure handling")
        try:
            repository.fail(
                record,
                error_code=code,
                safe_message=message,
                retryable=retryable,
                worker_id=worker_id,
            )
        except LeaseOwnershipError:
            logger.warning("Skipped stale failure update for job %s", job_id)
            return
        RunRepository(session).write_audit(
            tenant_id=tenant_id,
            actor_id=worker_id,
            action="RAZORPAY_SYNC_JOB_FAILED",
            resource_type="background_job",
            resource_id=job_id,
            outcome=record.status,
            details={"error_code": code, "retryable": retryable},
        )


async def _run_with_lease_heartbeat(
    operation,
    *,
    tenant_id: str,
    job_id: str,
    worker_id: str,
):
    settings = get_settings()
    stop = asyncio.Event()
    operation_task = asyncio.create_task(operation)
    heartbeat_task = asyncio.create_task(
        _maintain_lease(
            tenant_id=tenant_id,
            job_id=job_id,
            worker_id=worker_id,
            lease_seconds=settings.worker_lease_seconds,
            stop=stop,
        )
    )
    done, _ = await asyncio.wait(
        {operation_task, heartbeat_task},
        return_when=asyncio.FIRST_COMPLETED,
    )
    if heartbeat_task in done:
        operation_task.cancel()
        with suppress(asyncio.CancelledError):
            await operation_task
        return await heartbeat_task
    stop.set()
    await heartbeat_task
    return await operation_task


async def _maintain_lease(
    *,
    tenant_id: str,
    job_id: str,
    worker_id: str,
    lease_seconds: int,
    stop: asyncio.Event,
) -> None:
    interval = max(10, lease_seconds // 3)
    while True:
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
            return
        except asyncio.TimeoutError:
            pass
        with session_scope(tenant_id=tenant_id) as session:
            renewed = JobRepository(session).renew_lease(
                tenant_id=tenant_id,
                job_id=job_id,
                worker_id=worker_id,
                lease_seconds=lease_seconds,
            )
        if not renewed:
            raise LeaseOwnershipError("Worker lost the job lease during processing")


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
