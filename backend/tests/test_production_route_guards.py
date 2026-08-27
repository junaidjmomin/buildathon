from __future__ import annotations

from contextlib import nullcontext
from datetime import datetime, timezone
from decimal import Decimal
from importlib import import_module

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.domain.models import ConfusionMatrix, RunSummary, StatusBreakdown
from app.main import app
from app.security.auth import Principal, get_current_principal
from app.services.demo import DEMO_RUN_ID

api_router = import_module("app.api.router")


class _ForbiddenDemoState:
    def __getattribute__(self, name: str):
        if name.startswith("__"):
            return object.__getattribute__(self, name)
        raise AssertionError(f"production route touched process-local demo state: {name}")


PRODUCTION_DEMO_ROUTES = [
    ("POST", "/api/v1/demo/load", None),
    ("GET", "/api/v1/controls", None),
    ("GET", "/api/v1/agreements", None),
    ("GET", "/api/v1/agreements/AGR_NOVACART_2026", None),
    ("POST", "/api/v1/agreements/AGR_NOVACART_2026/extract-controls", None),
    ("GET", "/api/v1/agreements/AGR_NOVACART_2026/control-proposals", None),
    ("POST", "/api/v1/agreements/AGR_NOVACART_2026/compile-controls", None),
    ("GET", "/api/v1/controls/DOMESTIC_CARD_MDR/versions", None),
    ("GET", "/api/v1/controls/DOMESTIC_CARD_MDR/effective?at=2026-08-31", None),
    ("GET", "/api/v1/runs", None),
    ("GET", f"/api/v1/runs/{DEMO_RUN_ID}/summary", None),
    ("GET", f"/api/v1/runs/{DEMO_RUN_ID}/violations", None),
    ("GET", f"/api/v1/runs/{DEMO_RUN_ID}/root-causes", None),
    ("GET", f"/api/v1/runs/{DEMO_RUN_ID}/control-coverage", None),
    ("GET", f"/api/v1/runs/{DEMO_RUN_ID}/cases", None),
    ("GET", f"/api/v1/runs/{DEMO_RUN_ID}/unresolved", None),
    ("GET", "/api/v1/cases/CASE_PAY_82HD9", None),
    ("POST", "/api/v1/cases/CASE_PAY_82HD9/verify", {"note": "verify"}),
    (
        "GET",
        f"/api/v1/runs/{DEMO_RUN_ID}/payments/PAY_82HD9/expected-vs-actual",
        None,
    ),
    ("GET", f"/api/v1/runs/{DEMO_RUN_ID}/payments/PAY_82HD9/graph", None),
    ("GET", f"/api/v1/runs/{DEMO_RUN_ID}/payments/PAY_82HD9/lineage", None),
    ("GET", f"/api/v1/runs/{DEMO_RUN_ID}/payments/PAY_82HD9/counterfactual", None),
    ("GET", "/api/v1/root-causes/RC_MDR_01", None),
    ("POST", "/api/v1/root-causes/RC_MDR_01/generate-hypothesis", None),
    ("POST", "/api/v1/root-causes/RC_MDR_01/verify-hypothesis", None),
    ("POST", "/api/v1/root-causes/RC_MDR_01/investigate", None),
    ("GET", "/api/v1/agent/investigations/EXEC_DEMO", None),
    ("POST", f"/api/v1/runs/{DEMO_RUN_ID}/mutation-tests", None),
    ("POST", f"/api/v1/runs/{DEMO_RUN_ID}/blind-spots/remediate", None),
    ("GET", "/api/v1/mutation-tests/MUT_TEST_001", None),
    ("POST", "/api/v1/controls/CTRL_UNSUPPORTED_FEE_CANDIDATE/backtest", None),
    ("POST", "/api/v1/controls/CTRL_UNSUPPORTED_FEE_CANDIDATE/approve", None),
]


def _principal(tenant_id: str) -> Principal:
    return Principal(
        subject="production-user",
        tenant_id=tenant_id,
        roles=frozenset({"viewer", "analyst", "approver", "admin"}),
        auth_mode="oidc",
    )


@pytest.mark.parametrize(("method", "path", "payload"), PRODUCTION_DEMO_ROUTES)
def test_production_routes_never_touch_seeded_or_process_local_state(
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    path: str,
    payload: dict[str, str] | None,
) -> None:
    settings = Settings(ENVIRONMENT="production", DATABASE_URL="")
    monkeypatch.setattr(api_router, "get_settings", lambda: settings)
    forbidden = _ForbiddenDemoState()
    monkeypatch.setattr(api_router, "store", forbidden)
    monkeypatch.setattr(api_router, "governance", forbidden)
    monkeypatch.setattr(api_router, "CONTROLS", forbidden)
    monkeypatch.setattr(api_router, "AGREEMENT", forbidden)
    monkeypatch.setattr(api_router, "mutation_test", forbidden)
    monkeypatch.setattr(api_router, "investigation_runs", forbidden)
    app.dependency_overrides[get_current_principal] = lambda: _principal("novacart_demo")
    try:
        response = TestClient(app).request(method, path, json=payload)
    finally:
        app.dependency_overrides.pop(get_current_principal, None)

    assert response.status_code == 404


def test_non_demo_tenant_cannot_share_seeded_state_in_development(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(ENVIRONMENT="development", DATABASE_URL="")
    monkeypatch.setattr(api_router, "get_settings", lambda: settings)
    monkeypatch.setattr(api_router, "store", _ForbiddenDemoState())
    app.dependency_overrides[get_current_principal] = lambda: _principal("merchant_other")
    try:
        response = TestClient(app).post("/api/v1/demo/load")
    finally:
        app.dependency_overrides.pop(get_current_principal, None)

    assert response.status_code == 404


def test_production_live_run_summary_still_uses_tenant_repository(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(ENVIRONMENT="production", DATABASE_URL="postgresql://configured")
    summary = RunSummary(
        id="RUN_LIVE_001",
        name="Razorpay live run",
        status="COMPLETE",
        transaction_count=1,
        event_count=3,
        relationship_count=2,
        control_evaluation_count=1,
        breakdown=StatusBreakdown(passed=1, violation=0, warning=0, unresolved=0),
        precision=Decimal("0"),
        recall=Decimal("0"),
        false_positive_rate=Decimal("0"),
        verified_leakage=Decimal("0.00"),
        cash_delayed=Decimal("0.00"),
        unresolved_count=0,
        processing_ms=1,
        evaluations_per_second=1000,
        confusion_matrix=ConfusionMatrix(
            true_positive=0,
            false_positive=0,
            true_negative=0,
            false_negative=0,
        ),
        completed_at=datetime(2026, 8, 27, tzinfo=timezone.utc),
        ground_truth_available=False,
        metrics_scope="LIVE_CONTROL_OUTCOMES_NO_GROUND_TRUTH",
    )

    class _RunRepository:
        def __init__(self, _session: object) -> None:
            pass

        def live_run_summary(self, *, tenant_id: str, run_id: str) -> RunSummary:
            assert tenant_id == "merchant_live"
            assert run_id == summary.id
            return summary

    monkeypatch.setattr(api_router, "get_settings", lambda: settings)
    monkeypatch.setattr(api_router, "session_scope", lambda **_: nullcontext(object()))
    monkeypatch.setattr(api_router, "RunRepository", _RunRepository)
    monkeypatch.setattr(api_router, "store", _ForbiddenDemoState())
    app.dependency_overrides[get_current_principal] = lambda: _principal("merchant_live")
    try:
        response = TestClient(app).get(f"/api/v1/runs/{summary.id}/summary")
    finally:
        app.dependency_overrides.pop(get_current_principal, None)

    assert response.status_code == 200
    assert response.json()["id"] == summary.id
    assert response.json()["metrics_scope"] == "LIVE_CONTROL_OUTCOMES_NO_GROUND_TRUTH"
