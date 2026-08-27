from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import TypeVar

from pydantic import BaseModel

from app.agents.control_workflows import AgreementControlCompiler, BlindSpotRemediationController
from app.agents.investigation import InvestigationController
from app.agents.models import (
    AgentEvidence,
    HypothesisKind,
    StructuredHypothesis,
    TypedControlCandidate,
)

SchemaT = TypeVar("SchemaT", bound=BaseModel)


def evidence() -> list[AgentEvidence]:
    return [
        AgentEvidence(
            id="EVIDENCE_AGREEMENT_4_2",
            kind="APPROVED_CONTROL",
            source="CLAUSE_4_2",
            summary="Approved domestic MDR is 1.55%.",
            verified=True,
        ),
        AgentEvidence(
            id="EVIDENCE_RAZORPAY_ACTUAL",
            kind="OBSERVED_EVENT",
            source="PAY_82HD9",
            summary="Observed MDR is 1.75%.",
            verified=True,
        ),
    ]


def run(controller: InvestigationController):  # type: ignore[no-untyped-def]
    return asyncio.run(
        controller.run(
            tenant_id="novacart_demo",
            run_id="RUN_NOVACART_AUG_2026",
            root_cause_id="RC_MDR_01",
            violation_ids=["V_0001"],
            evidence=evidence(),
            razorpay_context={
                "observed_rate": "0.0175",
                "difference_amount": "20.00",
            },
            contract_controls=[
                {
                    "control_id": "CTRL_MDR_DOMESTIC",
                    "rate": "0.0155",
                    "tolerance": "0.01",
                }
            ],
            case_id="CASE_PAY_82HD9",
        )
    )


def test_investigation_rejects_first_hypothesis_then_proves_alternative() -> None:
    result = run(InvestigationController(provider=None, max_attempts=2))
    assert result.status == "PROVEN"
    assert result.attempt_count == 2
    assert result.case_id == "CASE_PAY_82HD9"
    assert [hypothesis.kind for hypothesis in result.hypotheses] == [
        HypothesisKind.CONTRACT_CHANGE,
        HypothesisKind.GATEWAY_RATE_DEVIATION,
    ]
    verify_steps = [step for step in result.trace if step.node == "verify_hypothesis"]
    assert [step.message for step in verify_steps] == [
        "Deterministic verifier returned REJECTED.",
        "Deterministic verifier returned PROVEN.",
    ]
    assert result.verification is not None
    assert result.verification.verifier == "sl3dge-deterministic-verifier"


class MisleadingProvider:
    async def generate(self, *, system: str, prompt: str) -> str:
        return "not used"

    async def generate_structured(
        self,
        *,
        schema: type[SchemaT],
        system: str,
        prompt: str,
    ) -> SchemaT:
        candidate = StructuredHypothesis(
            hypothesis_id="HYP_LLM_FORCED",
            kind=HypothesisKind.CONTRACT_CHANGE,
            statement="The 1.75% contract change is proven.",
            rationale="The model claims it is true.",
            claimed_rate="0.0175",
            evidence_ids=["EVIDENCE_AGREEMENT_4_2", "EVIDENCE_RAZORPAY_ACTUAL"],
            confidence=Decimal("1"),
        )
        return schema.model_validate(candidate.model_dump(mode="json"))


def test_llm_cannot_force_a_hypothesis_past_deterministic_verification() -> None:
    result = run(InvestigationController(provider=MisleadingProvider(), max_attempts=2))
    assert result.status == "UNRESOLVED"
    assert result.attempt_count == 2
    assert result.verification is not None
    assert result.verification.status == "REJECTED"
    assert result.case_id == "CASE_PAY_82HD9"
    assert result.trace[-1].node == "escalate_unresolved"


def test_unverified_evidence_cannot_prove_financial_conclusion() -> None:
    controller = InvestigationController(provider=None, max_attempts=1)
    result = asyncio.run(
        controller.run(
            tenant_id="novacart_demo",
            run_id="RUN_1",
            root_cause_id="RC_MDR_01",
            violation_ids=["V_1"],
            evidence=[
                AgentEvidence(
                    id="EVIDENCE_UNVERIFIED",
                    kind="OBSERVED_EVENT",
                    source="PAY_1",
                    summary="Unverified payload.",
                    verified=False,
                )
            ],
            razorpay_context={
                "observed_rate": "0.0175",
                "difference_amount": "20.00",
            },
            contract_controls=[{"control_id": "CTRL_1", "rate": "0.0155", "tolerance": "0.01"}],
        )
    )
    assert result.status == "UNRESOLVED"
    assert result.verification is not None
    assert result.verification.status == "UNRESOLVED"


def unsupported_fee_candidate() -> TypedControlCandidate:
    return TypedControlCandidate(
        candidate_id="CTRL_UNSUPPORTED_FEE_CANDIDATE",
        logical_control_key="UNLISTED_SETTLEMENT_FEE",
        control_type="UNSUPPORTED_FEE",
        name="Unlisted settlement fee",
        clause_id="CLAUSE_4_6",
        version=1,
        effective_from="2026-01-01",
        parameters={
            "allowlist": ["processing_fee", "gst", "refund_principal"],
            "tolerance": "0.01",
        },
        conditions=["deduction_type not in allowlist"],
        rationale="Clause 4.6 prohibits unlisted deductions.",
        confidence=Decimal("0.93"),
    )


def test_blind_spot_graph_stops_at_human_approval_after_deterministic_backtests() -> None:
    result = asyncio.run(
        BlindSpotRemediationController(provider=None).run(
            tenant_id="novacart_demo",
            run_id="RUN_NOVACART_AUG_2026",
            mutation_ids=["M_048", "M_049"],
            gap={"relationship": "SETTLEMENT -> OTHER_DEDUCTION", "clause_id": "CLAUSE_4_6"},
            clauses=[{"id": "CLAUSE_4_6", "text": "Unlisted fees are prohibited."}],
            seed_candidate=unsupported_fee_candidate(),
            historical_backtest={"false_positive_count": 0},
            mutation_backtest={"before_detected": 47, "after_detected": 49},
            comparison={"detection_rate_delta": "0.04", "false_positive_delta": 0},
        )
    )
    assert result.status == "AWAITING_HUMAN_APPROVAL"
    assert result.schema_valid is True
    assert result.human_approval_required is True
    assert result.trace[-1].node == "human_approval"
    assert result.trace[-1].status == "AWAITING_HUMAN_APPROVAL"


def test_agreement_compiler_returns_unapproved_schema_valid_drafts() -> None:
    result = asyncio.run(
        AgreementControlCompiler(provider=None).run(
            tenant_id="novacart_demo",
            agreement_id="AGR_NOVACART_2026",
            clauses=[{"id": "CLAUSE_4_6", "text": "Unlisted fees are prohibited."}],
            seed_candidates=[unsupported_fee_candidate()],
        )
    )
    assert result.status == "AWAITING_HUMAN_APPROVAL"
    assert result.schema_valid is True
    assert result.conflict_count == 0
    assert result.proposals[0].parameters["tolerance"] == "0.01"
    assert result.trace[-1].node == "human_approval"


def test_control_candidate_rejects_binary_float_financial_values() -> None:
    payload = unsupported_fee_candidate().model_dump(mode="json")
    payload["parameters"]["tolerance"] = 0.01
    try:
        TypedControlCandidate.model_validate(payload)
    except ValueError as exc:
        assert "floating-point" in str(exc) or "decimal string" in str(exc)
    else:
        raise AssertionError("A binary float financial tolerance must be rejected")
