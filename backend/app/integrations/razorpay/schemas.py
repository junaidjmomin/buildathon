from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class RazorpayModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class RazorpayCollection(RazorpayModel):
    entity: str = "collection"
    count: int
    items: list[dict[str, Any]]


class ReconItem(RazorpayModel):
    entity_id: str
    type: str
    debit: int = 0
    credit: int = 0
    amount: int
    currency: str
    fee: int = 0
    tax: int = 0
    on_hold: bool = False
    settled: bool = False
    created_at: int
    settled_at: int | None = None
    settlement_id: str | None = None
    posted_at: int | None = None
    description: str | None = None
    notes: Any = None
    payment_id: str | None = None
    settlement_utr: str | None = None
    order_id: str | None = None
    order_receipt: str | None = None
    method: str | None = None
    card_network: str | None = None
    card_issuer: str | None = None
    card_type: str | None = None
    dispute_id: str | None = None


class PaymentItem(RazorpayModel):
    id: str
    entity: str = "payment"
    amount: int
    currency: str
    status: str
    order_id: str | None = None
    international: bool = False
    method: str
    amount_refunded: int = 0
    captured: bool = False
    fee: int | None = None
    tax: int | None = None
    created_at: int


class RefundItem(RazorpayModel):
    id: str
    entity: str = "refund"
    amount: int
    currency: str
    payment_id: str
    created_at: int
    status: str
    receipt: str | None = None


class SettlementItem(RazorpayModel):
    id: str
    entity: str = "settlement"
    amount: int
    status: str
    fees: int = 0
    tax: int = 0
    utr: str | None = None
    created_at: int
