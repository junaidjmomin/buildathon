"""One-off throughput benchmark for execute_source_run against the configured DB.

Generates a synthetic three-file CSV bundle of ``PAYMENTS`` payments, executes
the deterministic pipeline, prints engine/persistence timing, then removes every
row written for the benchmark tenant so the real run list stays clean.
"""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv

load_dotenv()

from sqlalchemy import delete, text  # noqa: E402

from app.core.money import expected_fee, expected_gst  # noqa: E402
from app.ingestion.csv import read_source_csv  # noqa: E402
from app.ingestion.pipeline import execute_source_run  # noqa: E402
from app.persistence.database import get_engine, get_session_factory  # noqa: E402
from app.persistence.orm import (  # noqa: E402
    ArtifactRecord,
    AuditLogRecord,
    Base,
    ControlEvaluationRecord,
    ControlRecord,
    EventEdgeRecord,
    EventRecord,
    ExceptionCaseRecord,
    RootCauseRecord,
    RunRecord,
    RunStageRecord,
    SourceSnapshotRecord,
    ViolationRecord,
)

BENCH_TENANT = "bench-throughput"
PAYMENTS = int(sys.argv[1]) if len(sys.argv) > 1 else 250

# Rows are removed tenant-wide after the benchmark, newest tables first so
# foreign keys on run_id cascade cleanly.
CLEANUP_MODELS = (
    ExceptionCaseRecord,
    ViolationRecord,
    RootCauseRecord,
    RunStageRecord,
    ControlEvaluationRecord,
    EventEdgeRecord,
    EventRecord,
    SourceSnapshotRecord,
    AuditLogRecord,
    ArtifactRecord,
    ControlRecord,
    RunRecord,
)


def build_bundle(payment_count: int) -> tuple[bytes, bytes, bytes]:
    mdr_rate = Decimal("0.0155")
    gst_rate = Decimal("0.18")
    rows = ["payment_id,amount,captured_at,payment_method,card_scope,fee,tax,status"]
    for index in range(payment_count):
        amount = 1000 + (index % 900)
        gross = Decimal(amount)
        fee = expected_fee(gross, mdr_rate)
        tax = expected_gst(fee, gst_rate)
        captured = f"2026-08-{(index % 27) + 1:02d}T10:00:00"
        rows.append(f"PAY_{index:05d},{amount}.00,{captured},card,domestic,{fee},{tax},captured")
    payments = ("\n".join(rows) + "\n").encode()

    settlement_rows = ["settlement_id,payment_id,net_amount,settled_at"]
    bank_rows = ["bank_txn_id,credit,debit,posted_at,reference,description"]
    for index in range(payment_count):
        amount = 1000 + (index % 900)
        gross = Decimal(amount)
        net = gross - expected_fee(gross, mdr_rate)
        net -= expected_gst(expected_fee(gross, mdr_rate), gst_rate)
        settled = f"2026-08-{(index % 27) + 1:02d}T18:00:00"
        settlement_rows.append(f"SET_{index:05d},PAY_{index:05d},{net:.2f},{settled}")
        posted = f"2026-08-{(index % 27) + 1:02d}T20:00:00"
        bank_rows.append(
            f"BANK_{index:05d},{net:.2f},0.00,{posted},SET_{index:05d},merchant payout"
        )
    settlements = ("\n".join(settlement_rows) + "\n").encode()
    bank = ("\n".join(bank_rows) + "\n").encode()

    return payments, settlements, bank


def main() -> None:
    get_engine.cache_clear()
    get_session_factory.cache_clear()
    engine = get_engine()
    assert engine is not None, "DATABASE_URL required"
    Base.metadata.create_all(engine)

    payments_csv, settlements_csv, bank_csv = build_bundle(PAYMENTS)
    documents = [
        (
            f"BENCH_PAY_{PAYMENTS}",
            "payments.csv",
            read_source_csv(payments_csv, filename="payments.csv"),
        ),
        (
            f"BENCH_SET_{PAYMENTS}",
            "settlements.csv",
            read_source_csv(settlements_csv, filename="settlements.csv"),
        ),
        (f"BENCH_BANK_{PAYMENTS}", "bank.csv", read_source_csv(bank_csv, filename="bank.csv")),
    ]

    result = execute_source_run(
        documents,
        tenant_id=BENCH_TENANT,
        actor_id="benchmark",
        request_id="benchmark",
        run_name=f"Benchmark {PAYMENTS} payments",
    )
    print(
        f"run={result.run_id} events={result.events_created} edges={result.edges_created} "
        f"evaluations={result.control_evaluations_created} violations={result.violations_created}"
    )

    with get_session_factory()() as session:
        session.execute(
            text("SELECT set_config('app.tenant_id', :tenant, true)"),
            {"tenant": BENCH_TENANT},
        )
        manifest = session.get(RunRecord, (BENCH_TENANT, result.run_id))
        if manifest is not None:
            metrics = manifest.manifest or {}
            print(
                "timing: engine_ms={engine_processing_ms} "
                "persistence_ms={persistence_ms} total_ms={total_processing_ms} "
                "evals_per_second={evaluations_per_second}".format(**metrics)
            )

        for model in CLEANUP_MODELS:
            deleted = session.execute(delete(model).where(model.tenant_id == BENCH_TENANT))
            print(f"cleanup {model.__name__}: {deleted.rowcount}")
        session.commit()
    print("benchmark complete")


if __name__ == "__main__":
    main()
