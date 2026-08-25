from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.domain.models import (
    Control,
    DemoLoadResponse,
    ExpectedActualResponse,
    HypothesisResponse,
    HypothesisVerification,
    PaymentGraph,
    RootCause,
    RunSummary,
    Violation,
)
from app.services.demo import CONTROLS, DEMO_RUN_ID, store

router = APIRouter(prefix="/api/v1")


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "sl3dge-api"}


@router.post("/demo/load", response_model=DemoLoadResponse)
def load_demo() -> DemoLoadResponse:
    return store.load()


@router.get("/controls", response_model=list[Control])
def list_controls() -> list[Control]:
    return CONTROLS


@router.get("/runs/{run_id}/summary", response_model=RunSummary)
def run_summary(run_id: str) -> RunSummary:
    if run_id != DEMO_RUN_ID:
        raise HTTPException(status_code=404, detail="Run not found")
    store.ensure_loaded()
    assert store.summary is not None
    return store.summary


@router.get("/runs/{run_id}/violations", response_model=list[Violation])
def violations(run_id: str) -> list[Violation]:
    if run_id != DEMO_RUN_ID:
        raise HTTPException(status_code=404, detail="Run not found")
    store.ensure_loaded()
    return store.violations


@router.get("/runs/{run_id}/root-causes", response_model=list[RootCause])
def root_causes(run_id: str) -> list[RootCause]:
    if run_id != DEMO_RUN_ID:
        raise HTTPException(status_code=404, detail="Run not found")
    store.ensure_loaded()
    return store.root_causes


@router.get(
    "/runs/{run_id}/payments/{payment_id}/expected-vs-actual",
    response_model=ExpectedActualResponse,
)
def expected_vs_actual(run_id: str, payment_id: str) -> ExpectedActualResponse:
    if run_id != DEMO_RUN_ID:
        raise HTTPException(status_code=404, detail="Run not found")
    try:
        return store.expected_actual(payment_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Payment not found") from exc


@router.get("/runs/{run_id}/payments/{payment_id}/graph", response_model=PaymentGraph)
def payment_graph(run_id: str, payment_id: str) -> PaymentGraph:
    if run_id != DEMO_RUN_ID:
        raise HTTPException(status_code=404, detail="Run not found")
    try:
        return store.graph(payment_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Payment not found") from exc


@router.get("/root-causes/{root_cause_id}", response_model=RootCause)
def root_cause(root_cause_id: str) -> RootCause:
    try:
        return store.get_root_cause(root_cause_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Root cause not found") from exc


@router.post(
    "/root-causes/{root_cause_id}/generate-hypothesis", response_model=HypothesisResponse
)
def generate_hypothesis(root_cause_id: str) -> HypothesisResponse:
    try:
        return store.generate_hypothesis(root_cause_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Root cause not found") from exc


@router.post(
    "/root-causes/{root_cause_id}/verify-hypothesis", response_model=HypothesisVerification
)
def verify_hypothesis(root_cause_id: str) -> HypothesisVerification:
    try:
        return store.verify_hypothesis(root_cause_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Root cause not found") from exc

