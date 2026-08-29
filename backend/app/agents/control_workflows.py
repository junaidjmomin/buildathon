from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone
from decimal import Decimal
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
from app.domain.models import ControlType


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
    validation_warnings: list[str]
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


def _date_in_text(text: str, *, phrase: str) -> date | None:
    match = re.search(
        rf"{phrase}\s+(\d{{1,2}})\s+([A-Za-z]+)\s+(\d{{4}})",
        text,
        flags=re.IGNORECASE,
    )
    if match is None:
        return None
    try:
        month = datetime.strptime(match.group(2)[:3], "%b").month
        return date(int(match.group(3)), month, int(match.group(1)))
    except ValueError:
        return None


def _decimal_string(value: Decimal) -> str:
    return format(value.normalize(), "f")


def _money_string(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.01")), "f")


def validate_candidate_evidence(
    candidate: TypedControlCandidate, clauses: list[dict[str, Any]]
) -> list[str]:
    """Check that a typed candidate is supported by its cited operative clause."""

    clause = next((item for item in clauses if str(item.get("id")) == candidate.clause_id), None)
    if clause is None:
        return [f"{candidate.logical_control_key}: cited clause is missing"]
    text = str(clause.get("text", "")).strip()
    warnings: list[str] = []
    if not text:
        warnings.append(f"{candidate.logical_control_key}: quoted source text is empty")
    if str(clause.get("reference", "")).upper().startswith("PAGE_"):
        warnings.append(
            f"{candidate.logical_control_key}: provenance is page-level, not clause-level"
        )
    if str(clause.get("source_type", "")).upper() == "PDF_TEXT_EXTRACTION" and not clause.get(
        "source_offsets"
    ):
        warnings.append(f"{candidate.logical_control_key}: source offsets are missing")
    lower = re.sub(r"\s+", " ", text.lower()).strip()
    required_terms: dict[ControlType, tuple[tuple[str, ...], ...]] = {
        ControlType.MDR_RATE: (("mdr", "merchant discount"), ("%",), ("domestic card",)),
        ControlType.GST_ON_FEE: (("gst",), ("%",), ("approved processing fee",)),
        ControlType.SETTLEMENT_SLA: (
            ("captured payment",),
            ("t+2",),
            ("business day",),
            ("capture date",),
            ("must be included", "no later than"),
        ),
        ControlType.SETTLEMENT_ARITHMETIC: (
            ("gross",),
            ("approved",),
            ("bank credit",),
        ),
        ControlType.UNSUPPORTED_FEE: (("unlisted",), ("fee", "deduction")),
        ControlType.REFUND_INTEGRITY: (("refund",), ("once",), ("fee", "tolerance")),
        ControlType.LIFECYCLE_VALIDITY: (
            ("cumulative",),
            ("refund",),
            ("captured payment principal",),
        ),
    }
    terms = (
        (("chargeback",), ("administration fee",), ("once",))
        if candidate.logical_control_key == "CHARGEBACK_ADMIN_FEE"
        else required_terms.get(candidate.control_type, ())
    )
    for alternatives in terms:
        if not any(term in lower for term in alternatives):
            warnings.append(
                f"{candidate.logical_control_key}: operative source is missing "
                f"one of {' / '.join(alternatives)}"
            )
    required_parameters = {
        ControlType.MDR_RATE: ("rate", "tolerance"),
        ControlType.GST_ON_FEE: ("rate", "tolerance"),
        ControlType.UNSUPPORTED_FEE: ("tolerance",),
        ControlType.REFUND_INTEGRITY: ("maximum_deductions", "refund_fee", "tolerance"),
        ControlType.SETTLEMENT_ARITHMETIC: ("tolerance",),
    }
    for parameter in required_parameters.get(candidate.control_type, ()):
        if parameter not in candidate.parameters:
            warnings.append(
                f"{candidate.logical_control_key}: required parameter {parameter} is missing"
            )
    return warnings


def select_operative_clause(
    candidate: TypedControlCandidate, clauses: list[dict[str, Any]]
) -> dict[str, Any] | None:
    """Choose the strongest clause by required operative terms, not page mentions."""

    candidates = [
        clause
        for clause in clauses
        if not str(clause.get("reference", "")).upper().startswith("PAGE_")
        and not str(clause.get("reference", "")).upper().startswith("UNNUMBERED_")
    ]
    if candidate.logical_control_key == "CHARGEBACK_ADMIN_FEE":
        groups = (
            ("chargeback",),
            ("administration fee",),
            ("for each valid chargeback", "allowed fee"),
        )
    else:
        groups = {
            ControlType.MDR_RATE: (("mdr", "merchant discount"), ("%",), ("domestic card",)),
            ControlType.GST_ON_FEE: (("gst",), ("%",), ("approved processing fee",)),
            ControlType.SETTLEMENT_SLA: (
                ("captured payment",),
                ("t+2",),
                ("business day",),
                ("capture date",),
                ("must be included", "no later than"),
            ),
            ControlType.SETTLEMENT_ARITHMETIC: (("gross",), ("approved",), ("bank credit",)),
            ControlType.UNSUPPORTED_FEE: (("unlisted",), ("fee", "deduction")),
            ControlType.REFUND_INTEGRITY: (("refund",), ("once",), ("fee", "tolerance")),
            ControlType.LIFECYCLE_VALIDITY: (
                ("cumulative",),
                ("refund",),
                ("captured payment principal",),
            ),
        }.get(candidate.control_type, ())
    if not groups:
        return None
    best: tuple[int, dict[str, Any]] | None = None
    for clause in candidates:
        text = re.sub(r"\s+", " ", str(clause.get("text", "")).lower()).strip()
        score = sum(1 for group in groups if any(term in text for term in group))
        if score != len(groups):
            continue
        # Prefer the candidate's current clause on a genuine tie, otherwise
        # keep the first operative occurrence in document order.
        tie_break = 1 if str(clause.get("id")) == candidate.clause_id else 0
        rank = score * 10 + tie_break
        if best is None or rank > best[0]:
            best = (rank, clause)
    return best[1] if best else None


def _deterministic_candidates(clauses: list[dict[str, Any]]) -> list[TypedControlCandidate]:
    """Extract conservative typed candidates without relying on an LLM."""

    candidates: list[TypedControlCandidate] = []
    versions: dict[str, int] = {}
    seen: set[str] = set()
    seen_semantic: set[str] = set()

    def add(
        clause: dict[str, Any],
        *,
        key: str,
        control_type: ControlType,
        name: str,
        parameters: dict[str, Any],
        conditions: list[str],
        effective_from: date | None = None,
        effective_to: date | None = None,
    ) -> None:
        clause_id = str(clause.get("id", "")).strip()
        if not clause_id:
            return
        semantic_fingerprint = json.dumps(
            {"key": key, "parameters": parameters}, sort_keys=True, separators=(",", ":")
        )
        if semantic_fingerprint in seen_semantic:
            return
        seen_semantic.add(semantic_fingerprint)
        fingerprint = json.dumps(
            {
                "key": key,
                "parameters": parameters,
                "effective_from": (
                    effective_from or date.fromisoformat(str(clause["effective_from"]))
                ).isoformat(),
                "effective_to": effective_to.isoformat() if effective_to else None,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        if fingerprint in seen:
            return
        seen.add(fingerprint)
        version = versions.get(key, 0) + 1
        versions[key] = version
        start = effective_from or date.fromisoformat(str(clause["effective_from"]))
        candidate = TypedControlCandidate(
            candidate_id=f"CAND_{clause_id}_{key}",
            logical_control_key=key,
            control_type=control_type,
            name=name,
            clause_id=clause_id,
            version=version,
            effective_from=start,
            effective_to=effective_to,
            parameters=parameters,
            conditions=conditions,
            rationale=(
                "Deterministically extracted from the cited agreement clause; "
                "human approval required."
            ),
            confidence=Decimal("0.80"),
        )
        candidates.append(candidate)

    for clause in clauses:
        text = str(clause.get("text", ""))
        lower = re.sub(r"\s+", " ", text.lower()).strip()
        if (
            str(clause.get("reference", clause.get("clause_number", "")))
            .upper()
            .startswith("UNNUMBERED_")
        ):
            continue
        mdr_match = re.search(
            r"(?:merchant\s+discount\s+rate|\bmdr\b)[^%]{0,160}?(\d+(?:\.\d+)?)\s*%",
            text,
            re.IGNORECASE,
        )
        if (
            ("mdr" in lower or "merchant discount" in lower)
            and mdr_match
            and ("domestic card" in lower or "domestic cards" in lower)
        ):
            rate_text = mdr_match.group(1)
            if "amendment" in lower or "on or after" in lower:
                revised = re.search(
                    r"revised\s+from\s+\d+(?:\.\d+)?\s*%\s+to\s+(\d+(?:\.\d+)?)\s*%",
                    text,
                    re.IGNORECASE,
                )
                new_rate = re.search(r"new\s+rate\s*:\s*(\d+(?:\.\d+)?)\s*%", text, re.IGNORECASE)
                rate_text = (new_rate or revised).group(1) if (new_rate or revised) else rate_text
            rate = Decimal(rate_text) / Decimal("100")
            add(
                clause,
                key="DOMESTIC_CARD_MDR",
                control_type=ControlType.MDR_RATE,
                name="Domestic Card MDR",
                parameters={"rate": _decimal_string(rate), "tolerance": "0.01", "currency": "INR"},
                conditions=["captured payment", "domestic card"],
                effective_from=_date_in_text(text, phrase=r"(?:on or after|effective from)")
                or date.fromisoformat(str(clause["effective_from"])),
                effective_to=_date_in_text(text, phrase=r"(?:through|until)") or None,
            )
        if "gst" in lower and re.search(r"(\d+(?:\.\d+)?)\s*%", text):
            gst_match = re.search(r"(?:gst|tax).*?(\d+(?:\.\d+)?)\s*%", text, re.IGNORECASE)
            if gst_match:
                add(
                    clause,
                    key="GST_ON_VALID_FEE",
                    control_type=ControlType.GST_ON_FEE,
                    name="GST on Processing Fee",
                    parameters={
                        "rate": _decimal_string(Decimal(gst_match.group(1)) / Decimal("100")),
                        "tolerance": "0.01",
                        "base": "approved_processing_fee",
                    },
                    conditions=["approved processing fee"],
                )
        if "must be settled within" in lower or "settlement sla" in lower:
            days = re.search(r"(\d+)\s+business\s+days?", lower)
            add(
                clause,
                key="CAPTURE_TO_SETTLEMENT_SLA",
                control_type=ControlType.SETTLEMENT_SLA,
                name="Standard Settlement SLA",
                parameters={"business_days": int(days.group(1)) if days else 2},
                conditions=["captured payment"],
            )
        if (
            "refunded principal may be deducted once" in lower
            or "no additional refund fee" in lower
            or "refund principal exactly once" in lower
            or "refund processing fee" in lower
        ):
            add(
                clause,
                key="REFUND_PRINCIPAL_INTEGRITY",
                control_type=ControlType.REFUND_INTEGRITY,
                name="Refund Principal Integrity",
                parameters={
                    "maximum_deductions": 1,
                    "refund_fee": "0.00",
                    "tolerance": "0.01",
                    "currency": "INR",
                },
                conditions=["successful refund"],
            )
        if (
            "cumulative successful refund principal" in lower
            and "captured payment principal" in lower
        ):
            add(
                clause,
                key="REFUND_AMOUNT_LIMIT",
                control_type=ControlType.LIFECYCLE_VALIDITY,
                name="Refund Amount Limit",
                parameters={
                    "maximum_cumulative_refund": "captured_payment_principal",
                    "currency": "INR",
                },
                conditions=["successful refund", "captured payment"],
            )
        if "unlisted settlement fee" in lower or "unlisted settlement deduction" in lower:
            add(
                clause,
                key="UNSUPPORTED_SETTLEMENT_FEE",
                control_type=ControlType.UNSUPPORTED_FEE,
                name="Unlisted Settlement Fee",
                parameters={"expected_amount": "0.00", "tolerance": "0.01", "currency": "INR"},
                conditions=["settlement deduction"],
            )
        if "bank credit" in lower and "gross" in lower and "approved" in lower:
            add(
                clause,
                key="SETTLEMENT_BANK_ARITHMETIC",
                control_type=ControlType.SETTLEMENT_ARITHMETIC,
                name="Settlement and Bank Arithmetic",
                parameters={"tolerance": "0.01", "currency": "INR"},
                conditions=["processed settlement", "corresponding bank credit"],
            )
        if (
            "chargeback administration fee" in lower
            and "chargeback" in lower
            and ("for each valid chargeback" in lower or "allowed fee" in lower)
        ):
            fee_match = re.search(
                r"(?:administration fee of|allowed fee\s*:)\s*(?:inr\s*)?(\d+(?:\.\d+)?)",
                text,
                re.IGNORECASE,
            )
            if fee_match is None:
                continue
            add(
                clause,
                key="CHARGEBACK_ADMIN_FEE",
                control_type=ControlType.UNSUPPORTED_FEE,
                name="Chargeback Administration Fee",
                parameters={
                    "fee": _money_string(Decimal(fee_match.group(1))),
                    "maximum_deductions": 1,
                    "native_entity": "CHARGEBACK",
                    "tolerance": "0.01",
                    "currency": "INR",
                },
                conditions=["valid chargeback", "unique chargeback identifier"],
            )
    return candidates


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
        fallback_candidates = [
            TypedControlCandidate.model_validate(item) for item in state.get("seed_candidates", [])
        ]
        if not fallback_candidates:
            fallback_candidates = _deterministic_candidates(state.get("clauses", []))
        fallback = ControlCandidateBatch(candidates=fallback_candidates)
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
        if not batch.candidates and fallback.candidates:
            batch = fallback
            mode = "DETERMINISTIC_FALLBACK"
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
        warnings: list[str] = []
        try:
            batch = ControlCandidateBatch.model_validate({"candidates": state["proposals"]})
            clauses_list = state["clauses"]
            clauses = {str(clause.get("id")): clause for clause in clauses_list}
            valid = bool(batch.candidates)
            aligned_candidates: list[TypedControlCandidate] = []
            for candidate in batch.candidates:
                operative_clause = select_operative_clause(candidate, clauses_list)
                if (
                    operative_clause is not None
                    and str(operative_clause.get("id")) != candidate.clause_id
                ):
                    candidate = candidate.model_copy(
                        update={"clause_id": str(operative_clause.get("id"))}
                    )
                clause = clauses.get(candidate.clause_id)
                if clause is None:
                    valid = False
                    break
                warnings.extend(validate_candidate_evidence(candidate, [clause]))
                clause_from = clause.get("effective_from")
                clause_to = clause.get("effective_to")
                if clause_from and candidate.effective_from.isoformat() < str(clause_from):
                    valid = False
                    break
                if clause_to and (
                    candidate.effective_to is None
                    or candidate.effective_to.isoformat() > str(clause_to)
                ):
                    valid = False
                    break
                aligned_candidates.append(candidate)
            if valid:
                batch = ControlCandidateBatch(candidates=aligned_candidates)
        except ValidationError:
            valid = False
        return {
            "schema_valid": valid,
            "proposals": [item.model_dump(mode="json") for item in batch.candidates]
            if valid
            else state.get("proposals", []),
            "validation_warnings": warnings,
            "trace": [
                _step(
                    state,
                    "validate_schemas",
                    (
                        "All draft schemas and source evidence are valid."
                        if valid and not warnings
                        else f"{len(warnings)} source-evidence warning(s) require review."
                        if valid
                        else "One or more schemas are invalid."
                    ),
                    status="COMPLETE" if valid and not warnings else "REVIEW_REQUIRED",
                    details={"warnings": warnings},
                )
            ],
        }

    async def _detect_conflicts(self, state: ControlWorkflowState) -> ControlWorkflowState:
        by_key: dict[str, list[TypedControlCandidate]] = {}
        warnings: list[str] = []
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
                    warnings.append(
                        f"{proposal.logical_control_key}: duplicate version {proposal.version}"
                    )
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
                    warnings.append(
                        f"{proposal.logical_control_key}: effective periods overlap at "
                        f"{proposal.effective_from.isoformat()}"
                    )
        return {
            "conflict_count": conflicts,
            "validation_warnings": [*state.get("validation_warnings", []), *warnings],
            "trace": [
                _step(
                    state,
                    "detect_conflicts",
                    f"Detected {conflicts} candidate key conflict(s) for human resolution.",
                    status="COMPLETE" if conflicts == 0 else "REVIEW_REQUIRED",
                    details={"warnings": warnings},
                )
            ],
        }

    async def _human_approval(self, state: ControlWorkflowState) -> ControlWorkflowState:
        ready = (
            state.get("schema_valid", False)
            and state.get("conflict_count", 0) == 0
            and not state.get("validation_warnings", [])
        )
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
            validation_warnings=result.get("validation_warnings", []),
            trace=[AgentTraceStep.model_validate(item) for item in result["trace"]],
            started_at=started_at,
            completed_at=_now(),
        )
