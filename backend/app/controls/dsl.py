from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from pydantic import BaseModel, field_validator


class ControlParameterError(ValueError):
    pass


def _decimal_string(value: Any) -> Decimal:
    if not isinstance(value, str):
        raise ControlParameterError("Financial rates and tolerances must be decimal strings")
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise ControlParameterError(f"Invalid decimal string: {value}") from exc
    if not parsed.is_finite():
        raise ControlParameterError("Financial parameters must be finite")
    return parsed


class MdrRateParameters(BaseModel):
    rate: Decimal
    tolerance: Decimal

    @field_validator("rate", "tolerance", mode="before")
    @classmethod
    def parse_decimal_strings(cls, value: Any) -> Decimal:
        return _decimal_string(value)


class GstFeeParameters(BaseModel):
    rate: Decimal
    tolerance: Decimal

    @field_validator("rate", "tolerance", mode="before")
    @classmethod
    def parse_decimal_strings(cls, value: Any) -> Decimal:
        return _decimal_string(value)


class SettlementArithmeticParameters(BaseModel):
    tolerance: Decimal

    @field_validator("tolerance", mode="before")
    @classmethod
    def parse_decimal_strings(cls, value: Any) -> Decimal:
        return _decimal_string(value)
