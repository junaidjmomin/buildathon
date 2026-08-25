from __future__ import annotations

from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

PAISE = Decimal("0.01")


def money(value: Decimal | str | int) -> Decimal:
    """Convert and round a monetary value using commercial half-up rounding."""
    return Decimal(value).quantize(PAISE, rounding=ROUND_HALF_UP)


def expected_fee(amount: Decimal, rate: Decimal) -> Decimal:
    return money(amount * rate)


def expected_gst(fee: Decimal, rate: Decimal = Decimal("0.18")) -> Decimal:
    return money(fee * rate)


def add_business_days(captured_at: datetime, days: int) -> datetime:
    """Add Monday-Friday business days while preserving the input time and timezone."""
    current = captured_at
    added = 0
    while added < days:
        current += timedelta(days=1)
        if current.weekday() < 5:
            added += 1
    return current


def business_days_late(expected_at: datetime, actual_at: datetime) -> int:
    if actual_at <= expected_at:
        return 0
    cursor = expected_at
    days = 0
    while cursor.date() < actual_at.date():
        cursor += timedelta(days=1)
        if cursor.weekday() < 5:
            days += 1
    return days
