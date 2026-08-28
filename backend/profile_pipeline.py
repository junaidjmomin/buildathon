"""Profile execute_source_run phase timings against the configured DB."""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv

load_dotenv()

from sqlalchemy import event  # noqa: E402

from app.ingestion.csv import read_source_csv  # noqa: E402
from app.ingestion.pipeline import execute_source_run  # noqa: E402
from app.persistence.database import get_engine  # noqa: E402
from bench_throughput import BENCH_TENANT, build_bundle  # noqa: E402


class QueryTimer:
    def __init__(self) -> None:
        self.queries: list[tuple[float, str]] = []
        self._start = 0.0

    def before_cursor_execute(self, conn, cursor, statement, parameters, context, executemany):
        self._start = time.perf_counter()

    def after_cursor_execute(self, conn, cursor, statement, parameters, context, executemany):
        elapsed = time.perf_counter() - self._start
        label = " ".join(statement.split())[:110]
        self.queries.append((elapsed, label))


def main() -> None:
    payment_count = int(sys.argv[1]) if len(sys.argv) > 1 else 60
    payments_csv, settlements_csv, bank_csv = build_bundle(payment_count)
    documents = [
        (
            f"BENCH_PAY_{payment_count}",
            "payments.csv",
            read_source_csv(payments_csv, filename="payments.csv"),
        ),
        (
            f"BENCH_SET_{payment_count}",
            "settlements.csv",
            read_source_csv(settlements_csv, filename="settlements.csv"),
        ),
        (
            f"BENCH_BANK_{payment_count}",
            "bank.csv",
            read_source_csv(bank_csv, filename="bank.csv"),
        ),
    ]

    timer = QueryTimer()
    engine = get_engine()
    assert engine is not None
    event.listen(engine, "before_cursor_execute", timer.before_cursor_execute)
    event.listen(engine, "after_cursor_execute", timer.after_cursor_execute)

    started = time.perf_counter()
    result = execute_source_run(
        documents,
        tenant_id=BENCH_TENANT,
        actor_id="benchmark",
        request_id="benchmark",
        run_name="profile run",
    )
    total = time.perf_counter() - started
    event.remove(engine, "before_cursor_execute", timer.before_cursor_execute)
    event.remove(engine, "after_cursor_execute", timer.after_cursor_execute)
    print(
        f"total={total:.2f}s events={result.events_created} "
        f"evals={result.control_evaluations_created}"
    )
    print(f"query count={len(timer.queries)} query time={sum(q[0] for q in timer.queries):.2f}s")
    timer.queries.sort(reverse=True)
    for elapsed, label in timer.queries[:15]:
        print(f"  {elapsed:7.3f}s  {label}")


if __name__ == "__main__":
    main()
