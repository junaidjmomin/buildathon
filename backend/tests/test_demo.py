from decimal import Decimal

from fastapi.testclient import TestClient

from app.main import app
from app.services.demo import DEMO_RUN_ID

client = TestClient(app)


def test_seeded_demo_proves_hidden_overcharge() -> None:
    loaded = client.post("/api/v1/demo/load")
    assert loaded.status_code == 200
    assert loaded.json()["counts"]["payments"] == 500

    response = client.get(
        f"/api/v1/runs/{DEMO_RUN_ID}/payments/PAY_82HD9/expected-vs-actual"
    )
    assert response.status_code == 200
    body = response.json()
    assert body["gateway_net"] == body["bank_credit"] == "9793.50"
    assert body["expected_net"] == "9817.10"
    assert body["verified_leakage"] == "23.60"


def test_demo_metrics_are_measured_from_separate_ground_truth() -> None:
    client.post("/api/v1/demo/load")
    response = client.get(f"/api/v1/runs/{DEMO_RUN_ID}/summary")
    body = response.json()
    assert Decimal(body["precision"]) >= Decimal("0.98")
    assert Decimal(body["recall"]) >= Decimal("0.95")
    assert body["unresolved_count"] == 5


def test_hypothesis_is_independently_rejected() -> None:
    client.post("/api/v1/demo/load")
    hypothesis = client.post("/api/v1/root-causes/RC_MDR_01/generate-hypothesis")
    assert hypothesis.json()["status"] == "UNVERIFIED"
    verification = client.post("/api/v1/root-causes/RC_MDR_01/verify-hypothesis")
    assert verification.json()["status"] == "REJECTED"

