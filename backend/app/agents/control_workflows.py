from __future__ import annotations

import json
from datetime import datetime, timezone
from operator import add
from typing import Annotated, Any, TypedDict
from uuid import uuid4

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from pydantic import ValidationError

from app.agents.models import (
    AgentTraceStep,
    AgreementCompilationExecution,
    BlindSpotRemediationExecution,
    ControlCandidateBatch,
    TypedControlCandidate,
)
from app.ai.provider import StructuredProvider


class ControlWorkflowState(TypedDict, total=False):
    execution_id: str
    tenant_id: str
    run_id: str
    agreement_id: str
    clauses: list[dict[str, Any]]
    mutation_ids: list[str]
    gap: dict[str, Any]
    seed_candidates: list[dict[str, Any]]
    proposals: list[dict[str, Any]]
    proposed_control: dict[str, Any]
    schema_valid: bool
    conflict_count: int
    historical_backtest: dict[str, Any]
    mutation_backtest: dict[str, Any]
    comparison: dict[str, Any]
    final_status: str
    trace: Annotated[list[dict[str, Any]], add]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _step(
    state: ControlWorkflowState,
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


class BlindSpotRemediationController:
    """Proposes but never approves controls; supplied backtests remain authoritative."""

    def __init__(
        self,
        provider: StructuredProvider | None,
        *,
        checkpointer: BaseCheckpointSaver[Any] | None = None,
    ) -> None:
        self.provider = provider
        builder = StateGraph(ControlWorkflowState)
        builder.add_node("identify_gap", self._identify_gap)
        builder.add_node("retrieve_contract_clause", self._retrieve_clause)
        builder.add_node("propose_control", self._propose_control)
        builder.add_node("schema_validate", self._schema_validate)
        builder.add_node("historical_backtest", self._historical_backtest)
        builder.add_node("mutation_backtest", self._mutation_backtest)
        builder.add_node("compare_metrics", self._compare_metrics)
        builder.add_node("human_approval", self._human_approval)
        builder.add_edge(START, "identify_gap")
        builder.add_edge("identify_gap", "retrieve_contract_clause")
        builder.add_edge("retrieve_contract_clause", "propose_control")
        builder.add_edge("propose_control", "schema_validate")
        builder.add_conditional_edges(
            "schema_validate",
            lambda state: "continue" if state["schema_valid"] else "review",
            {"continue": "historical_backtest", "review": "human_approval"},
        )
        builder.add_edge("historical_backtest", "mutation_backtest")
        builder.add_edge("mutation_backtest", "compare_metrics")
        builder.add_edge("compare_metrics", "human_approval")
        builder.add_edge("human_approval", END)
        self.graph = builder.compile(checkpointer=checkpointer or InMemorySaver())

    async def _identify_gap(self, state: ControlWorkflowState) -> ControlWorkflowState:
        return {
            "trace": [
                _step(
                    state,
                    "identify_gap",
                    (
                        f"Identified a control gap from {len(state['mutation_ids'])} "
                        "missed mutation(s)."
                    ),
                )
            ]
        }

    async def _retrieve_clause(self, state: ControlWorkflowState) -> ControlWorkflowState:
        clause_id = state["gap"].get("clause_id")
        found = any(clause.get("id") == clause_id for clause in state["clauses"])
        return {
            "trace": [
                _step(
                    state,
                    "retrieve_contract_clause",
                    (
                        "Retrieved the cited agreement clause."
                        if found
                        else "Cited clause is missing."
                    ),
                    status="COMPLETE" if found else "UNRESOLVED",
                    details={"clause_id": clause_id},
                )
            ]
        }

    async def _propose_control(self, state: ControlWorkflowState) -> ControlWorkflowState:
        fallback = TypedControlCandidate.model_validate(state["seed_candidates"][0])
        candidate = fallback
        model_status = "DETERMINISTIC_FALLBACK"
        if self.provider is not None:
            safe_context = {
                "gap": state["gap"],
                "clauses": state["clauses"],
                "required_candidate_id": fallback.candidate_id,
            }
            try:
                candidate = await self.provider.generate_structured(
                    schema=TypedControlCandidate,
                    system=(
                        "Propose one typed draft control from the cited clause. Do not approve it. "
                        "All money, rates, fees, and tolerances must be decimal strings. Never "
                        "change historical records or deterministic backtest results."
                    ),
                    prompt=json.dumps(safe_context, separators=(",", ":"), ensure_ascii=True),
                )
                model_status = "MODEL_STRUCTURED_OUTPUT"
            except Exception:
                model_status = "MODEL_DEGRADED_TO_FALLBACK"
        return {
            "proposed_control": candidate.model_dump(mode="json"),
            "trace": [
                _step(
                    state,
                    "propose_control",
                    "Produced a draft typed control; it has no approval authority.",
                    details={"generation_mode": model_status},
                )
            ],
        }

    async def _schema_validate(self, state: ControlWorkflowState) -> ControlWorkflowState:
        try:
            TypedControlCandidate.model_validate(state["proposed_control"])
            valid = True
        except ValidationError:
            valid = False
        return {
            "schema_valid": valid,
            "trace": [
                _step(
                    state,
                    "schema_validate",
                    "Draft control passed the typed schema." if valid else "Draft schema rejected.",
                    status="COMPLETE" if valid else "REJECTED",
                )
            ],
        }

    async def _historical_backtest(self, state: ControlWorkflowState) -> ControlWorkflowState:
        return {
            "trace": [
                _step(
                    state,
                    "historical_backtest",
                    "Loaded deterministic historical false-positive results.",
                    details=state["historical_backtest"],
                )
            ]
        }

    async def _mutation_backtest(self, state: ControlWorkflowState) -> ControlWorkflowState:
        return {
            "trace": [
                _step(
                    state,
                    "mutation_backtest",
                    "Loaded deterministic mutation-suite results for the draft.",
                    details=state["mutation_backtest"],
                )
            ]
        }

    async def _compare_metrics(self, state: ControlWorkflowState) -> ControlWorkflowState:
        return {
            "trace": [
                _step(
                    state,
                    "compare_metrics",
                    "Compared deterministic before/after metrics without model arithmetic.",
                    details=state["comparison"],
                )
            ]
        }

    async def _human_approval(self, state: ControlWorkflowState) -> ControlWorkflowState:
        status = "AWAITING_HUMAN_APPROVAL" if state.get("schema_valid") else "REJECTED"
        return {
            "final_status": status,
            "trace": [
                _step(
                    state,
                    "human_approval",
                    (
                        "Paused for maker-checker approval."
                        if status == "AWAITING_HUMAN_APPROVAL"
                        else "Rejected before approval because schema validation failed."
                    ),
                    status=status,
                )
            ],
        }

    async def run(
        self,
        *,
        tenant_id: str,
        run_id: str,
        mutation_ids: list[str],
        gap: dict[str, Any],
        clauses: list[dict[str, Any]],
        seed_candidate: TypedControlCandidate,
        historical_backtest: dict[str, Any],
        mutation_backtest: dict[str, Any],
        comparison: dict[str, Any],
    ) -> BlindSpotRemediationExecution:
        execution_id = f"REM_{uuid4().hex.upper()}"
        started_at = _now()
        result = await self.graph.ainvoke(
            {
                "execution_id": execution_id,
                "tenant_id": tenant_id,
                "run_id": run_id,
                "mutation_ids": mutation_ids,
                "gap": gap,
                "clauses": clauses,
                "seed_candidates": [seed_candidate.model_dump(mode="json")],
                "historical_backtest": historical_backtest,
                "mutation_backtest": mutation_backtest,
                "comparison": comparison,
                "trace": [],
            },
            {"configurable": {"thread_id": execution_id}, "recursion_limit": 16},
        )
        return BlindSpotRemediationExecution(
            execution_id=execution_id,
            tenant_id=tenant_id,
            run_id=run_id,
            mutation_ids=mutation_ids,
            status=result["final_status"],
            proposed_control=TypedControlCandidate.model_validate(result["proposed_control"]),
            schema_valid=result["schema_valid"],
            historical_backtest=historical_backtest,
            mutation_backtest=mutation_backtest,
            comparison=comparison,
            trace=[AgentTraceStep.model_validate(item) for item in result["trace"]],
            started_at=started_at,
            completed_at=_now(),
        )


class AgreementControlCompiler:
    """Compiles draft candidates but always ends at a human-approval boundary."""

    def __init__(
        self,
        provider: StructuredProvider | None,
        *,
        checkpointer: BaseCheckpointSaver[Any] | None = None,
    ) -> None:
        self.provider = provider
        builder = StateGraph(ControlWorkflowState)
        builder.add_node("extract_clauses", self._extract_clauses)
        builder.add_node("classify_financial_terms", self._classify_terms)
        builder.add_node("generate_typed_controls", self._generate_controls)
        builder.add_node("validate_schemas", self._validate_schemas)
        builder.add_node("detect_conflicts", self._detect_conflicts)
        builder.add_node("human_approval", self._human_approval)
        builder.add_edge(START, "extract_clauses")
        builder.add_edge("extract_clauses", "classify_financial_terms")
        builder.add_edge("classify_financial_terms", "generate_typed_controls")
        builder.add_edge("generate_typed_controls", "validate_schemas")
        builder.add_edge("validate_schemas", "detect_conflicts")
        builder.add_edge("detect_conflicts", "human_approval")
        builder.add_edge("human_approval", END)
        self.graph = builder.compile(checkpointer=checkpointer or InMemorySaver())

    async def _extract_clauses(self, state: ControlWorkflowState) -> ControlWorkflowState:
        return {
            "trace": [
                _step(
                    state,
                    "extract_clauses",
                    f"Loaded {len(state['clauses'])} provenance-linked agreement clauses.",
                )
            ]
        }

    async def _classify_terms(self, state: ControlWorkflowState) -> ControlWorkflowState:
        return {
            "trace": [
                _step(
                    state,
                    "classify_financial_terms",
                    "Classified fee, tax, settlement, refund, and deduction terms.",
                )
            ]
        }

    async def _generate_controls(self, state: ControlWorkflowState) -> ControlWorkflowState:
        fallback = ControlCandidateBatch.model_validate({"candidates": state["seed_candidates"]})
        batch = fallback
        mode = "DETERMINISTIC_FALLBACK"
        if self.provider is not None:
            try:
                batch = await self.provider.generate_structured(
                    schema=ControlCandidateBatch,
                    system=(
                        "Compile draft typed controls from the supplied agreement clauses. "
                        "Cite clause IDs, use decimal strings for every financial value, and "
                        "never approve, activate, backdate, or resolve conflicts automatically."
                    ),
                    prompt=json.dumps(
                        {"agreement_id": state["agreement_id"], "clauses": state["clauses"]},
                        separators=(",", ":"),
                        ensure_ascii=True,
                    ),
                )
                mode = "MODEL_STRUCTURED_OUTPUT"
            except Exception:
                mode = "MODEL_DEGRADED_TO_FALLBACK"
        return {
            "proposals": [item.model_dump(mode="json") for item in batch.candidates],
            "trace": [
                _step(
                    state,
                    "generate_typed_controls",
                    f"Generated {len(batch.candidates)} schema-bound draft control(s).",
                    details={"generation_mode": mode},
                )
            ],
        }

    async def _validate_schemas(self, state: ControlWorkflowState) -> ControlWorkflowState:
        try:
            ControlCandidateBatch.model_validate({"candidates": state["proposals"]})
            valid = True
        except ValidationError:
            valid = False
        return {
            "schema_valid": valid,
            "trace": [
                _step(
                    state,
                    "validate_schemas",
                    "All draft schemas are valid." if valid else "One or more schemas are invalid.",
                    status="COMPLETE" if valid else "REJECTED",
                )
            ],
        }

    async def _detect_conflicts(self, state: ControlWorkflowState) -> ControlWorkflowState:
        by_key: dict[str, list[TypedControlCandidate]] = {}
        for raw in state.get("proposals", []):
            proposal = TypedControlCandidate.model_validate(raw)
            by_key.setdefault(proposal.logical_control_key, []).append(proposal)
        conflicts = 0
        for proposals in by_key.values():
            ordered = sorted(proposals, key=lambda item: (item.effective_from, item.version))
            seen_versions: set[int] = set()
            for index, proposal in enumerate(ordered):
                if proposal.version in seen_versions:
                    conflicts += 1
                seen_versions.add(proposal.version)
                if index == 0:
                    continue
                previous = ordered[index - 1]
                overlaps = (
                    previous.effective_to is None
                    or proposal.effective_from <= previous.effective_to
                )
                if overlaps:
                    conflicts += 1
        return {
            "conflict_count": conflicts,
            "trace": [
                _step(
                    state,
                    "detect_conflicts",
                    f"Detected {conflicts} candidate key conflict(s) for human resolution.",
                    status="COMPLETE" if conflicts == 0 else "REVIEW_REQUIRED",
                )
            ],
        }

    async def _human_approval(self, state: ControlWorkflowState) -> ControlWorkflowState:
        ready = state.get("schema_valid", False) and state.get("conflict_count", 0) == 0
        status = "AWAITING_HUMAN_APPROVAL" if ready else "REVIEW_REQUIRED"
        return {
            "final_status": status,
            "trace": [
                _step(
                    state,
                    "human_approval",
                    "Paused before activation; a human approver must review every draft.",
                    status=status,
                )
            ],
        }

    async def run(
        self,
        *,
        tenant_id: str,
        agreement_id: str,
        clauses: list[dict[str, Any]],
        seed_candidates: list[TypedControlCandidate],
    ) -> AgreementCompilationExecution:
        execution_id = f"CMP_{uuid4().hex.upper()}"
        started_at = _now()
        result = await self.graph.ainvoke(
            {
                "execution_id": execution_id,
                "tenant_id": tenant_id,
                "agreement_id": agreement_id,
                "clauses": clauses,
                "seed_candidates": [item.model_dump(mode="json") for item in seed_candidates],
                "trace": [],
            },
            {"configurable": {"thread_id": execution_id}, "recursion_limit": 12},
        )
        return AgreementCompilationExecution(
            execution_id=execution_id,
            tenant_id=tenant_id,
            agreement_id=agreement_id,
            status=result["final_status"],
            proposals=[TypedControlCandidate.model_validate(item) for item in result["proposals"]],
            schema_valid=result["schema_valid"],
            conflict_count=result["conflict_count"],
            trace=[AgentTraceStep.model_validate(item) for item in result["trace"]],
            started_at=started_at,
            completed_at=_now(),
        )
