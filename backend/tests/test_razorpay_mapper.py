from decimal import Decimal

from app.integrations.razorpay.mapper import map_recon_item
from app.integrations.razorpay.schemas import ReconItem


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
