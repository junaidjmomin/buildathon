from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from pydantic import BaseModel, Field, field_validator


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


class RefundIntegrityParameters(BaseModel):
    maximum_deductions: int = Field(ge=1, le=10)
    refund_fee: Decimal
    tolerance: Decimal

    @field_validator("refund_fee", "tolerance", mode="before")
    @classmethod
    def parse_decimal_strings(cls, value: Any) -> Decimal:
        return _decimal_string(value)


class SettlementSlaParameters(BaseModel):
    business_days: int = Field(ge=0, le=30)


class UnsupportedFeeParameters(BaseModel):
    allowlist: list[str] = Field(min_length=1, max_length=100)
    tolerance: Decimal

    @field_validator("tolerance", mode="before")
    @classmethod
    def parse_decimal_strings(cls, value: Any) -> Decimal:
        return _decimal_string(value)
