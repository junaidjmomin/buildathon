from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class RazorpayModel(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True, str_strip_whitespace=True)


class RazorpayCollection(RazorpayModel):
    entity: str = "collection"
    count: int = Field(ge=0)
    items: list[dict[str, object]]


class ReconItem(RazorpayModel):
    entity_id: str = Field(min_length=1, max_length=160)
    type: str = Field(min_length=1, max_length=80)
    debit: int = Field(default=0, ge=0)
    credit: int = Field(default=0, ge=0)
    amount: int = Field(ge=0)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    fee: int = Field(default=0, ge=0)
    tax: int = Field(default=0, ge=0)
    on_hold: bool = False
    settled: bool = False
    created_at: int = Field(ge=0)
    settled_at: int | None = Field(default=None, ge=0)
    settlement_id: str | None = Field(default=None, max_length=160)
    payment_id: str | None = Field(default=None, max_length=160)
    settlement_utr: str | None = Field(default=None, max_length=160)
    order_id: str | None = Field(default=None, max_length=160)
    method: str | None = Field(default=None, max_length=80)
    card_network: str | None = Field(default=None, max_length=80)
    card_type: str | None = Field(default=None, max_length=80)


class PaymentItem(RazorpayModel):
    id: str = Field(min_length=1, max_length=160)
    entity: str = "payment"
    amount: int = Field(ge=0)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    status: str = Field(min_length=1, max_length=80)
    order_id: str | None = Field(default=None, max_length=160)
    international: bool = False
    method: str = Field(min_length=1, max_length=80)
    amount_refunded: int = Field(default=0, ge=0)
    captured: bool = False
    fee: int | None = Field(default=None, ge=0)
    tax: int | None = Field(default=None, ge=0)
    created_at: int = Field(ge=0)


class RefundItem(RazorpayModel):
    id: str = Field(min_length=1, max_length=160)
    entity: str = "refund"
    amount: int = Field(ge=0)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    payment_id: str = Field(min_length=1, max_length=160)
    created_at: int = Field(ge=0)
    status: str = Field(min_length=1, max_length=80)
    receipt: str | None = Field(default=None, max_length=160)


class SettlementItem(RazorpayModel):
    id: str = Field(min_length=1, max_length=160)
    entity: str = "settlement"
    amount: int = Field(ge=0)
    status: str = Field(min_length=1, max_length=80)
    fees: int = Field(default=0, ge=0)
    tax: int = Field(default=0, ge=0)
    utr: str | None = Field(default=None, max_length=160)
    created_at: int = Field(ge=0)
