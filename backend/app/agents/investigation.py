from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from operator import add
from typing import Annotated, Any, TypedDict
from uuid import uuid4

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from app.agents.models import (
    AgentEvidence,
    AgentTraceStep,
    DeterministicVerification,
    HypothesisKind,
    InvestigationExecution,
    StructuredHypothesis,
    VerificationCheck,
)
from app.ai.provider import StructuredProvider


class InvestigationState(TypedDict, total=False):
    execution_id: str
    tenant_id: str
    run_id: str
    source_type: str
    violation_ids: list[str]
    root_cause_id: str
    evidence: list[dict[str, Any]]
    razorpay_context: dict[str, str]
    contract_controls: list[dict[str, str]]
    hypotheses: Annotated[list[dict[str, Any]], add]
    current_hypothesis: dict[str, Any]
    verification_result: dict[str, Any]
    attempt_count: int
    max_attempts: int
    final_status: str
    case_id: str | None
    trace: Annotated[list[dict[str, Any]], add]
    ai_configured: bool
    llm_used: bool
    started_at: str


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _trace(
    state: InvestigationState,
    node: str,
    message: str,
    *,
    status: str = "COMPLETE",
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return AgentTraceStep(
        sequence=len(state.get("trace", [])) + 1,
        node=node,
        status=status,
        message=message,
        occurred_at=_now(),
        details=details or {},
    ).model_dump(mode="json")


def _decimal(value: str | None) -> Decimal | None:
    if value is None:
        return None
    try:
        parsed = Decimal(value)
    except InvalidOperation:
        return None
    return parsed if parsed.is_finite() else None


def verify_hypothesis(state: InvestigationState) -> DeterministicVerification:
    """Pure verifier. Only this function decides whether a hypothesis is proven."""

    hypothesis = StructuredHypothesis.model_validate(state["current_hypothesis"])
    controls = state.get("contract_controls", [])
    context = state.get("razorpay_context", {})
    evidence = [AgentEvidence.model_validate(item) for item in state.get("evidence", [])]
    expected_rate = _decimal(controls[0].get("rate")) if controls else None
    tolerance = _decimal(controls[0].get("tolerance")) if controls else None
    observed_rate = _decimal(context.get("observed_rate"))
    claimed_rate = _decimal(hypothesis.claimed_rate)
    verified_ids = {item.id for item in evidence if item.verified}
    cited_verified = bool(hypothesis.evidence_ids) and set(hypothesis.evidence_ids).issubset(
        verified_ids
    )

    checks = [
        VerificationCheck(
            label="approved control rate",
            result="AVAILABLE" if expected_rate is not None else "MISSING",
            expected=str(expected_rate) if expected_rate is not None else None,
            evidence_ids=[item.id for item in evidence if item.kind == "APPROVED_CONTROL"],
        ),
        VerificationCheck(
            label="observed gateway rate",
            result="AVAILABLE" if observed_rate is not None else "MISSING",
            observed=str(observed_rate) if observed_rate is not None else None,
            evidence_ids=[item.id for item in evidence if item.kind == "OBSERVED_EVENT"],
        ),
        VerificationCheck(
            label="cited evidence",
            result="VERIFIED" if cited_verified else "UNVERIFIED",
            evidence_ids=hypothesis.evidence_ids,
        ),
    ]
    if expected_rate is None or observed_rate is None or not cited_verified:
        return DeterministicVerification(
            status="UNRESOLVED",
            classification="INSUFFICIENT_VERIFIED_EVIDENCE",
            checks=checks,
            conclusion="The deterministic verifier lacks the evidence needed to decide.",
        )

    if hypothesis.kind == HypothesisKind.CONTRACT_CHANGE:
        matched = claimed_rate is not None and claimed_rate == expected_rate
        checks.append(
            VerificationCheck(
                label="claimed rate is effective",
                result="MATCH" if matched else "CONTRADICTED",
                expected=str(expected_rate),
                observed=str(claimed_rate) if claimed_rate is not None else None,
            )
        )
        return DeterministicVerification(
            status="PROVEN" if matched else "REJECTED",
            classification="APPROVED_CONTRACT_CHANGE" if matched else "NO_EFFECTIVE_AMENDMENT",
            checks=checks,
            conclusion=(
                "The claimed rate matches the approved effective control."
                if matched
                else (
                    "The claimed contract change is contradicted by the approved effective control."
                )
            ),
        )

    if hypothesis.kind == HypothesisKind.GATEWAY_RATE_DEVIATION:
        rate_diff = abs(observed_rate - expected_rate)
        amount_diff = _decimal(context.get("difference_amount"))
        amount_exceeds = tolerance is None or (
            amount_diff is not None and abs(amount_diff) > tolerance
        )
        proven = observed_rate != expected_rate and amount_exceeds
        checks.append(
            VerificationCheck(
                label="gateway rate differs from effective control",
                result="REPRODUCED" if proven else "NOT_REPRODUCED",
                expected=str(expected_rate),
                observed=str(observed_rate),
            )
        )
        checks.append(
            VerificationCheck(
                label="currency tolerance",
                result="EXCEEDED" if amount_exceeds else "WITHIN_TOLERANCE",
                expected=str(tolerance) if tolerance is not None else None,
                observed=str(amount_diff) if amount_diff is not None else None,
            )
        )
        return DeterministicVerification(
            status="PROVEN" if proven else "REJECTED",
            classification="SYSTEMIC_GATEWAY_RATE_DEVIATION" if proven else "NOT_REPRODUCED",
            checks=checks,
            conclusion=(
                f"Observed rate {observed_rate} differs from approved rate {expected_rate}; "
                f"rate delta {rate_diff} is deterministic evidence of the deviation."
                if proven
                else "The asserted gateway rate deviation was not reproduced."
            ),
        )

    return DeterministicVerification(
        status="UNRESOLVED",
        classification="NO_APPLICABLE_DETERMINISTIC_VERIFIER",
        checks=checks,
        conclusion=(
            "This hypothesis requires a typed deterministic verifier before it can be proven."
        ),
    )


def _fallback_hypothesis(state: InvestigationState, *, alternative: bool) -> StructuredHypothesis:
    evidence_ids = [item["id"] for item in state.get("evidence", []) if bool(item.get("verified"))]
    if alternative:
        return StructuredHypothesis(
            hypothesis_id=f"HYP_{state['root_cause_id']}_02",
            kind=HypothesisKind.GATEWAY_RATE_DEVIATION,
            statement=(
                "Razorpay applied a rate that differs from the approved effective MDR control."
            ),
            rationale=(
                "The observed gateway fee reproduces a 1.75% rate while the approved "
                "effective control remains 1.55%."
            ),
            claimed_rate="0.0175",
            evidence_ids=evidence_ids,
            confidence=Decimal("0.99"),
        )
    return StructuredHypothesis(
        hypothesis_id=f"HYP_{state['root_cause_id']}_01",
        kind=HypothesisKind.CONTRACT_CHANGE,
        statement="The contractual MDR rate may have changed to 1.75%.",
        rationale="A uniform observed rate shift can be caused by an effective contract amendment.",
        claimed_rate="0.0175",
        evidence_ids=evidence_ids,
        confidence=Decimal("0.65"),
    )


class InvestigationController:
    """LangGraph controller; deterministic verification remains authoritative."""

    def __init__(
        self,
        *,
        provider: StructuredProvider | None,
        max_attempts: int = 2,
        checkpointer: BaseCheckpointSaver[Any] | None = None,
    ) -> None:
        self.provider = provider
        self.max_attempts = max_attempts
        self.graph = self._build_graph().compile(checkpointer=checkpointer or InMemorySaver())

    def _build_graph(self) -> StateGraph[InvestigationState]:
        builder = StateGraph(InvestigationState)
        builder.add_node("collect_evidence", self._collect_evidence)
        builder.add_node("load_source_context", self._load_source_context)
        builder.add_node("load_contract_context", self._load_contract_context)
        builder.add_node("generate_hypothesis", self._generate_hypothesis)
        builder.add_node("verify_hypothesis", self._verify_hypothesis)
        builder.add_node("generate_alternative_hypothesis", self._generate_alternative)
        builder.add_node("create_case", self._create_case)
        builder.add_node("escalate_unresolved", self._escalate_unresolved)
        builder.add_edge(START, "collect_evidence")
        builder.add_edge("collect_evidence", "load_source_context")
        builder.add_edge("load_source_context", "load_contract_context")
        builder.add_edge("load_contract_context", "generate_hypothesis")
        builder.add_edge("generate_hypothesis", "verify_hypothesis")
        builder.add_conditional_edges(
            "verify_hypothesis",
            self._verification_route,
            {
                "proven": "create_case",
                "retry": "generate_alternative_hypothesis",
                "unresolved": "escalate_unresolved",
            },
        )
        builder.add_edge("generate_alternative_hypothesis", "verify_hypothesis")
        builder.add_edge("create_case", END)
        builder.add_edge("escalate_unresolved", END)
        return builder

    async def _collect_evidence(self, state: InvestigationState) -> InvestigationState:
        verified = sum(1 for item in state.get("evidence", []) if item.get("verified"))
        return {
            "trace": [
                _trace(
                    state,
                    "collect_evidence",
                    f"Collected {verified} deterministically verified evidence items.",
                    details={"verified_evidence_count": verified},
                )
            ]
        }

    async def _load_source_context(self, state: InvestigationState) -> InvestigationState:
        available = bool(state.get("razorpay_context"))
        source_type = state.get("source_type", "CSV_UPLOAD")
        return {
            "trace": [
                _trace(
                    state,
                    "load_source_context",
                    (
                        f"Loaded {source_type} context from canonical source evidence."
                        if available
                        else (
                            f"No supplementary {source_type} context was available; no external "
                            "tool was attempted."
                        )
                    ),
                    status="COMPLETE" if available else "DEGRADED",
                )
            ]
        }

    async def _load_contract_context(self, state: InvestigationState) -> InvestigationState:
        controls = state.get("contract_controls", [])
        return {
            "trace": [
                _trace(
                    state,
                    "load_contract_context",
                    f"Loaded {len(controls)} approved effective control version(s).",
                    status="COMPLETE" if controls else "DEGRADED",
                )
            ]
        }

    async def _model_hypothesis(
        self, state: InvestigationState, *, alternative: bool
    ) -> tuple[StructuredHypothesis, list[dict[str, Any]], bool]:
        if self.provider is None:
            return _fallback_hypothesis(state, alternative=alternative), [], False
        safe_context = {
            "root_cause_id": state["root_cause_id"],
            "verified_evidence": state.get("evidence", []),
            "razorpay_context": state.get("razorpay_context", {}),
            "contract_controls": state.get("contract_controls", []),
            "rejected_hypotheses": state.get("hypotheses", []) if alternative else [],
        }
        try:
            hypothesis = await self.provider.generate_structured(
                schema=StructuredHypothesis,
                system=(
                    "You are a bounded finance investigation assistant. Return only the "
                    "requested schema. Never decide pass/fail, calculate authoritative money, "
                    "create EventEdges, change controls, or call write-capable tools. Cite only "
                    "provided verified evidence IDs. Encode every financial rate as a "
                    "decimal string."
                ),
                prompt=json.dumps(safe_context, separators=(",", ":"), ensure_ascii=True),
            )
            return hypothesis, [], True
        except Exception as exc:
            degraded = _trace(
                state,
                "generate_alternative_hypothesis" if alternative else "generate_hypothesis",
                "The configured model failed; continued with a deterministic fallback candidate.",
                status="DEGRADED",
                details={"error_type": type(exc).__name__},
            )
            return _fallback_hypothesis(state, alternative=alternative), [degraded], False

    async def _generate_hypothesis(self, state: InvestigationState) -> InvestigationState:
        hypothesis, degraded, llm_used = await self._model_hypothesis(state, alternative=False)
        return {
            "attempt_count": 1,
            "current_hypothesis": hypothesis.model_dump(mode="json"),
            "hypotheses": [hypothesis.model_dump(mode="json")],
            "trace": degraded
            + [
                _trace(
                    state,
                    "generate_hypothesis",
                    "Generated a schema-validated hypothesis for deterministic testing.",
                    details={"hypothesis_id": hypothesis.hypothesis_id},
                )
            ],
            "llm_used": llm_used,
        }

    async def _generate_alternative(self, state: InvestigationState) -> InvestigationState:
        hypothesis, degraded, llm_used = await self._model_hypothesis(state, alternative=True)
        return {
            "attempt_count": state.get("attempt_count", 1) + 1,
            "current_hypothesis": hypothesis.model_dump(mode="json"),
            "hypotheses": [hypothesis.model_dump(mode="json")],
            "trace": degraded
            + [
                _trace(
                    state,
                    "generate_alternative_hypothesis",
                    "Generated an alternate schema-validated hypothesis after rejection.",
                    details={"hypothesis_id": hypothesis.hypothesis_id},
                )
            ],
            "llm_used": llm_used,
        }

    async def _verify_hypothesis(self, state: InvestigationState) -> InvestigationState:
        result = verify_hypothesis(state)
        return {
            "verification_result": result.model_dump(mode="json"),
            "trace": [
                _trace(
                    state,
                    "verify_hypothesis",
                    f"Deterministic verifier returned {result.status}.",
                    details={
                        "classification": result.classification,
                        "verifier": result.verifier,
                    },
                )
            ],
        }

    def _verification_route(self, state: InvestigationState) -> str:
        status = state["verification_result"]["status"]
        if status == "PROVEN":
            return "proven"
        if status == "REJECTED" and state.get("attempt_count", 0) < state["max_attempts"]:
            return "retry"
        return "unresolved"

    async def _create_case(self, state: InvestigationState) -> InvestigationState:
        case_id = state.get("case_id") or f"CASE_{state['root_cause_id']}"
        return {
            "case_id": case_id,
            "final_status": "PROVEN",
            "trace": [
                _trace(
                    state,
                    "create_case",
                    (
                        "Created an evidence-backed case reference; human workflow remains "
                        "authoritative."
                    ),
                    details={"case_id": case_id},
                )
            ],
        }

    async def _escalate_unresolved(self, state: InvestigationState) -> InvestigationState:
        return {
            "final_status": "UNRESOLVED",
            "trace": [
                _trace(
                    state,
                    "escalate_unresolved",
                    "Escalated for human review without forcing an ambiguous conclusion.",
                )
            ],
        }

    async def run(
        self,
        *,
        tenant_id: str,
        run_id: str,
        source_type: str = "CSV_UPLOAD",
        root_cause_id: str,
        violation_ids: list[str],
        evidence: list[AgentEvidence],
        razorpay_context: dict[str, str],
        contract_controls: list[dict[str, str]],
        case_id: str | None = None,
    ) -> InvestigationExecution:
        execution_id = f"INV_{uuid4().hex.upper()}"
        started_at = _now()
        result = await self.graph.ainvoke(
            {
                "execution_id": execution_id,
                "tenant_id": tenant_id,
                "run_id": run_id,
                "source_type": source_type,
                "root_cause_id": root_cause_id,
                "violation_ids": violation_ids,
                "evidence": [item.model_dump(mode="json") for item in evidence],
                "razorpay_context": razorpay_context,
                "contract_controls": contract_controls,
                "hypotheses": [],
                "attempt_count": 0,
                "max_attempts": self.max_attempts,
                "trace": [],
                "ai_configured": self.provider is not None,
                "case_id": case_id,
                "started_at": started_at.isoformat(),
            },
            {
                "configurable": {"thread_id": execution_id},
                "recursion_limit": 20,
            },
        )
        return InvestigationExecution(
            execution_id=execution_id,
            tenant_id=tenant_id,
            run_id=run_id,
            source_type=result.get("source_type", "CSV_UPLOAD"),
            root_cause_id=root_cause_id,
            violation_ids=violation_ids,
            status=result["final_status"],
            attempt_count=result["attempt_count"],
            ai_configured=result["ai_configured"],
            orchestration_used=True,
            orchestration_provider="langgraph",
            llm_used=bool(result.get("llm_used", False)),
            llm_provider=(
                getattr(self.provider, "provider_name", None) if result.get("llm_used") else None
            ),
            llm_model=getattr(self.provider, "model_name", None)
            if result.get("llm_used")
            else None,
            mcp_used=False,
            razorpay_context_used=(source_type.upper() == "RAZORPAY" and bool(razorpay_context)),
            evidence_sources=sorted({item.source for item in evidence}),
            hypotheses=[StructuredHypothesis.model_validate(item) for item in result["hypotheses"]],
            verification=DeterministicVerification.model_validate(result["verification_result"]),
            case_id=result.get("case_id"),
            trace=[AgentTraceStep.model_validate(item) for item in result["trace"]],
            started_at=started_at,
            completed_at=_now(),
        )
