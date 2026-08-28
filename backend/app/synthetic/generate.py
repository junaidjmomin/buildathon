from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from collections.abc import Iterable
from decimal import Decimal
from pathlib import Path

from app.services.governance import AGREEMENT
from app.synthetic.generator import DEMO_SEED, SyntheticDataset, generate_dataset


def export_dataset(
    output: Path,
    *,
    seed: int = DEMO_SEED,
    payment_count: int = 500,
) -> dict[str, int]:
    """Export the authoritative seeded dataset without binary-float conversion."""

    dataset = generate_dataset(seed=seed, payment_count=payment_count)
    output.mkdir(parents=True, exist_ok=True)
    _write_csv(
        output / "orders.csv",
        ["order_id", "customer_id", "amount", "created_at", "expected_status", "payment_id"],
        (
            {
                "order_id": payment.order_id,
                "customer_id": f"CUST_{index % 125:04d}",
                "amount": str(payment.amount),
                "created_at": payment.captured_at.isoformat(),
                "expected_status": "paid",
                "payment_id": payment.payment_id,
            }
            for index, payment in enumerate(dataset.payments)
        ),
    )
    _write_csv(
        output / "payments.csv",
        [
            "payment_id",
            "order_id",
            "amount",
            "currency",
            "payment_method",
            "card_network",
            "card_scope",
            "captured_at",
            "fee",
            "tax",
            "status",
        ],
        (
            {
                "payment_id": payment.payment_id,
                "order_id": payment.order_id,
                "amount": str(payment.amount),
                "currency": "INR",
                "payment_method": payment.payment_method,
                "card_network": payment.card_network,
                "card_scope": payment.card_scope,
                "captured_at": payment.captured_at.isoformat(),
                "fee": str(payment.actual_fee),
                "tax": str(payment.actual_tax),
                "status": payment.status,
            }
            for payment in dataset.payments
        ),
    )
    _write_csv(
        output / "refunds.csv",
        ["refund_id", "payment_id", "amount", "created_at", "status"],
        (
            {
                "refund_id": payment.refund_id,
                "payment_id": payment.payment_id,
                "amount": str(payment.refund_amount),
                "created_at": payment.captured_at.isoformat(),
                "status": "processed",
            }
            for payment in dataset.payments
            if payment.refund_id is not None
        ),
    )
    _write_csv(
        output / "settlements.csv",
        [
            "settlement_id",
            "payment_id",
            "gross_amount",
            "fee",
            "tax",
            "refund_adjustment",
            "other_adjustment",
            "net_amount",
            "settled_at",
        ],
        (
            {
                "settlement_id": payment.settlement_id,
                "payment_id": payment.payment_id,
                "gross_amount": str(payment.amount),
                "fee": str(payment.actual_fee),
                "tax": str(payment.actual_tax),
                "refund_adjustment": str(payment.refund_deduction),
                "other_adjustment": str(payment.unsupported_fee),
                "net_amount": str(payment.actual_net),
                "settled_at": payment.settled_at.isoformat(),
            }
            for payment in dataset.payments
        ),
    )
    _write_bank_csv(output / "bank.csv", dataset)
    _write_csv(
        output / "chargebacks.csv",
        ["chargeback_id", "payment_id", "amount", "fee", "created_at", "status"],
        (
            {
                "chargeback_id": f"CB_{index + 1:03d}",
                "payment_id": payment.payment_id,
                "amount": str(min(payment.amount, Decimal("1000.00"))),
                "fee": "0.00",
                "created_at": payment.settled_at.isoformat(),
                "status": "open",
            }
            for index, payment in enumerate(dataset.payments[61:67])
        ),
    )
    (output / "ground_truth.json").write_text(
        json.dumps(dataset.ground_truth, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output / "agreement.json").write_text(
        AGREEMENT.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )
    return dataset.counts


def _write_bank_csv(path: Path, dataset: SyntheticDataset) -> None:
    totals: dict[str, Decimal] = defaultdict(lambda: Decimal("0.00"))
    timestamps = {}
    references = {}
    for payment in dataset.payments:
        if payment.bank_txn_id is None or payment.bank_credit is None:
            continue
        totals[payment.bank_txn_id] += payment.bank_credit
        timestamps[payment.bank_txn_id] = max(
            timestamps.get(payment.bank_txn_id, payment.settled_at),
            payment.settled_at,
        )
        references[payment.bank_txn_id] = payment.settlement_id
    _write_csv(
        path,
        ["bank_txn_id", "posted_at", "description", "credit", "debit", "currency", "reference"],
        (
            {
                "bank_txn_id": bank_id,
                "posted_at": timestamps[bank_id].isoformat(),
                "description": f"RAZORPAY SETTLEMENT {references[bank_id]}",
                "credit": str(total),
                "debit": "0.00",
                "currency": "INR",
                "reference": references[bank_id],
            }
            for bank_id, total in sorted(totals.items())
        ),
    )


def _write_csv(path: Path, fields: list[str], rows: Iterable[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Export the authoritative NovaCart demo fixtures")
    parser.add_argument("--seed", type=int, default=DEMO_SEED)
    parser.add_argument("--payments", type=int, default=500)
    parser.add_argument("--output", type=Path, default=Path("data/demo"))
    args = parser.parse_args()
    counts = export_dataset(args.output, seed=args.seed, payment_count=args.payments)
    print(json.dumps({"output": str(args.output), "counts": counts}, indent=2))


if __name__ == "__main__":
    main()
