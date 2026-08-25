from datetime import datetime, timezone
from decimal import Decimal

from app.core.money import add_business_days, expected_fee, expected_gst


def test_mdr_and_gst_use_commercial_rounding() -> None:
    fee = expected_fee(Decimal("10000"), Decimal("0.0155"))
    assert fee == Decimal("155.00")
    assert expected_gst(fee) == Decimal("27.90")


def test_t_plus_two_skips_weekend() -> None:
    friday = datetime(2026, 8, 21, 10, tzinfo=timezone.utc)
    expected = add_business_days(friday, 2)
    assert expected.date().isoformat() == "2026-08-25"
