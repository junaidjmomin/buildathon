from datetime import datetime, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.controls.dsl import MdrRateParameters
from app.core.money import add_business_days, expected_fee, expected_gst


def test_mdr_and_gst_use_commercial_rounding() -> None:
    fee = expected_fee(Decimal("10000"), Decimal("0.0155"))
    assert fee == Decimal("155.00")
    assert expected_gst(fee) == Decimal("27.90")


def test_t_plus_two_skips_weekend() -> None:
    friday = datetime(2026, 8, 21, 10, tzinfo=timezone.utc)
    expected = add_business_days(friday, 2)
    assert expected.date().isoformat() == "2026-08-25"


def test_control_rates_and_money_tolerances_require_decimal_strings() -> None:
    parsed = MdrRateParameters.model_validate({"rate": "0.0155", "tolerance": "0.01"})
    assert parsed.rate == Decimal("0.0155")
    assert parsed.tolerance == Decimal("0.01")
    with pytest.raises(ValidationError):
        MdrRateParameters.model_validate({"rate": 0.0155, "tolerance": "0.01"})
    with pytest.raises(ValidationError):
        MdrRateParameters.model_validate({"rate": "0.0155", "tolerance": 0.01})
