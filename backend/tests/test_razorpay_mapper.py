from decimal import Decimal

from app.integrations.razorpay.mapper import map_payment, map_recon_item, map_refund
from app.integrations.razorpay.schemas import PaymentItem, ReconItem, RefundItem


def test_recon_payment_maps_into_canonical_events_and_edges() -> None:
    item = ReconItem.model_validate(
        {
            "entity_id": "pay_DEXrnipqTmWVGE",
            "type": "payment",
            "debit": 0,
            "credit": 97100,
            "amount": 100000,
            "currency": "INR",
            "fee": 2458,
            "tax": 442,
            "on_hold": False,
            "settled": True,
            "created_at": 1567692556,
            "settled_at": 1568176960,
            "settlement_id": "setl_DGlQ1Rj8os78Ec",
            "settlement_utr": "1568176960vxp0rj",
            "order_id": "order_DEXrnRiR3SNDHA",
            "method": "card",
            "card_network": "Visa",
            "card_type": "credit",
        }
    )
    events, edges = map_recon_item(item, run_id="RUN_1", sync_id="SYNC_1")
    assert [event.event_type for event in events] == ["PAYMENT", "FEE", "TAX"]
    assert events[0].amount == Decimal("1000.00")
    assert events[1].amount == Decimal("24.58")
    assert events[2].amount == Decimal("4.42")
    assert events[0].normalized_payload["settlement_utr"] == "1568176960vxp0rj"
    assert {edge.relationship for edge in edges} == {
        "CHARGED_FEE",
        "CHARGED_TAX",
        "INCLUDED_IN",
    }
    assert all(edge.run_id == "RUN_1" for edge in edges)


def test_razorpay_status_never_exposes_credentials() -> None:
    from fastapi.testclient import TestClient

    from app.main import app

    response = TestClient(app).get("/api/v1/integrations/razorpay/status")
    assert response.status_code == 200
    assert set(response.json()) == {
        "configured",
        "mode",
        "connected",
        "last_sync_status",
        "last_synced_at",
    }


def test_direct_payment_and_refund_map_into_same_canonical_model() -> None:
    payment = PaymentItem.model_validate(
        {
            "id": "pay_123",
            "amount": 100000,
            "currency": "INR",
            "status": "captured",
            "order_id": "order_123",
            "method": "card",
            "amount_refunded": 25000,
            "captured": True,
            "fee": 1550,
            "tax": 279,
            "created_at": 1567692556,
        }
    )
    refund = RefundItem.model_validate(
        {
            "id": "rfnd_123",
            "amount": 25000,
            "currency": "INR",
            "payment_id": "pay_123",
            "created_at": 1567693556,
            "status": "processed",
        }
    )
    payment_event = map_payment(payment, run_id="RUN_1", sync_id="SYNC_1")
    refund_event, refund_edge = map_refund(refund, run_id="RUN_1", sync_id="SYNC_1")

    assert payment_event.id == "rzp:payment:pay_123"
    assert payment_event.amount == Decimal("1000.00")
    assert payment_event.normalized_payload["fee"] == "15.50"
    assert refund_event.id == "rzp:refund:rfnd_123"
    assert refund_event.amount == Decimal("250.00")
    assert refund_edge.from_event_id == payment_event.id
    assert refund_edge.to_event_id == refund_event.id
    assert refund_edge.relationship == "REFUNDED_BY"
