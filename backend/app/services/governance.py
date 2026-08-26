from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from hashlib import sha256

from app.domain.models import (
    Agreement,
    AgreementClause,
    Control,
    ControlCoverageItem,
    ControlCoverageSummary,
    ControlProposal,
    ControlType,
    CoverageStatus,
    PaymentLifecycle,
)

AGREEMENT_ID = "AGR_NOVACART_2026"

AGREEMENT_TEXT = """NovaCart India Merchant Services Agreement

4.2 Domestic cards. The processing fee for captured domestic card payments is
1.55 percent of the gross captured amount through 31 August 2026.

4.3 Tax. GST is 18 percent of the valid processing fee. GST must not be computed
on an amount above the fee permitted by this agreement.

4.6 Other deductions. Only deductions expressly listed in this agreement may be
applied. Unlisted platform or convenience fees are not permitted.

6.1 Settlement timing. Captured payments must be settled within two business
days of capture.

6.2 Settlement arithmetic. The settlement and corresponding bank credit must
equal gross captured value less approved fee, valid GST and valid refunds.

7.2 Refunds. Refunded principal may be deducted once. No additional refund fee
is payable.

Amendment A1. For domestic card payments captured on or after 1 September 2026,
the processing fee is 1.65 percent. All other terms remain unchanged.
"""


CLAUSES = [
    AgreementClause(
        id="CLAUSE_4_2",
        reference="4.2",
        page=4,
        heading="Domestic card processing fee",
        text=(
            "The processing fee for captured domestic card payments is 1.55% of the "
            "gross captured amount through 31 August 2026."
        ),
        effective_from=date(2026, 1, 1),
        effective_to=date(2026, 8, 31),
    ),
    AgreementClause(
        id="CLAUSE_4_3",
        reference="4.3",
        page=4,
        heading="GST on valid fee",
        text="GST is 18% of the valid processing fee and not of an excess fee.",
        effective_from=date(2026, 1, 1),
    ),
    AgreementClause(
        id="CLAUSE_4_6",
        reference="4.6",
        page=5,
        heading="Permitted deductions",
        text=(
            "Only expressly listed deductions are permitted; unlisted platform fees are prohibited."
        ),
        effective_from=date(2026, 1, 1),
    ),
    AgreementClause(
        id="CLAUSE_6_1",
        reference="6.1",
        page=6,
        heading="Settlement timing",
        text="Captured payments must be settled within two business days of capture.",
        effective_from=date(2026, 1, 1),
    ),
    AgreementClause(
        id="CLAUSE_6_2",
        reference="6.2",
        page=6,
        heading="Settlement arithmetic",
        text=(
            "Settlement and bank credit equal gross less approved fee, valid GST and valid refunds."
        ),
        effective_from=date(2026, 1, 1),
    ),
    AgreementClause(
        id="CLAUSE_7_2",
        reference="7.2",
        page=7,
        heading="Refund integrity",
        text="Refunded principal may be deducted once and no additional refund fee is payable.",
        effective_from=date(2026, 1, 1),
    ),
    AgreementClause(
        id="AMENDMENT_A1",
        reference="A1",
        page=9,
        heading="Domestic card fee amendment",
        text="Domestic card processing fee is 1.65% for captures on or after 1 September 2026.",
        effective_from=date(2026, 9, 1),
    ),
]

AGREEMENT = Agreement(
    id=AGREEMENT_ID,
    merchant="NovaCart India",
    title="Merchant Services Agreement · 2026",
    status="APPROVED",
    effective_from=date(2026, 1, 1),
    source_type="SEEDED_TEXT",
    content_hash=sha256(AGREEMENT_TEXT.encode("utf-8")).hexdigest(),
    clauses=CLAUSES,
)


def _control_templates() -> list[Control]:
    approved_at = datetime(2026, 1, 2, 10, 0, tzinfo=timezone.utc)
    return [
        Control(
            id="CTRL_MDR_DOMESTIC",
            name="Domestic Card MDR",
            control_type=ControlType.MDR_RATE,
            expected="1.55%",
            scope="Card · Domestic",
            source="NovaCart Merchant Agreement",
            source_clause="Page 4 · Clause 4.2",
            clause_id="CLAUSE_4_2",
            logical_control_key="DOMESTIC_CARD_MDR",
            version=1,
            effective_from=date(2026, 1, 1),
            effective_to=date(2026, 8, 31),
            parameters={"rate": "0.0155", "tolerance": "0.01", "currency": "INR"},
            conditions=["payment_method == card", "card_scope == domestic", "status == captured"],
            extraction_method="SEEDED_STRUCTURED_EXTRACTION",
            approved_at=approved_at,
        ),
        Control(
            id="CTRL_MDR_DOMESTIC_V2",
            name="Domestic Card MDR",
            control_type=ControlType.MDR_RATE,
            expected="1.65%",
            scope="Card · Domestic",
            source="NovaCart Merchant Agreement · Amendment A1",
            source_clause="Page 9 · Amendment A1",
            clause_id="AMENDMENT_A1",
            logical_control_key="DOMESTIC_CARD_MDR",
            version=2,
            effective_from=date(2026, 9, 1),
            supersedes_control_id="CTRL_MDR_DOMESTIC",
            parameters={"rate": "0.0165", "tolerance": "0.01", "currency": "INR"},
            conditions=["payment_method == card", "card_scope == domestic", "status == captured"],
            extraction_method="SEEDED_STRUCTURED_EXTRACTION",
            approved_at=datetime(2026, 8, 25, 10, 0, tzinfo=timezone.utc),
        ),
        Control(
            id="CTRL_GST_FEE",
            name="GST on Processing Fee",
            control_type=ControlType.GST_ON_FEE,
            expected="18% of approved fee",
            scope="Processing fee",
            source="NovaCart Merchant Agreement",
            source_clause="Page 4 · Clause 4.3",
            clause_id="CLAUSE_4_3",
            logical_control_key="GST_ON_VALID_FEE",
            parameters={
                "rate": "0.18",
                "tolerance": "0.01",
                "base": "approved_processing_fee",
            },
            conditions=["processing_fee > 0"],
            extraction_method="SEEDED_STRUCTURED_EXTRACTION",
            approved_at=approved_at,
        ),
        Control(
            id="CTRL_SETTLEMENT_SLA",
            name="Standard Settlement SLA",
            control_type=ControlType.SETTLEMENT_SLA,
            expected="T+2 business days",
            scope="Captured payments",
            source="NovaCart Merchant Agreement",
            source_clause="Page 6 · Clause 6.1",
            clause_id="CLAUSE_6_1",
            logical_control_key="CAPTURE_TO_SETTLEMENT_SLA",
            parameters={"business_days": 2},
            conditions=["status == captured"],
            extraction_method="SEEDED_STRUCTURED_EXTRACTION",
            approved_at=approved_at,
        ),
        Control(
            id="CTRL_SETTLEMENT_ARITHMETIC",
            name="Settlement and Bank Arithmetic",
            control_type=ControlType.SETTLEMENT_ARITHMETIC,
            expected="Gross less approved deductions",
            scope="Settlement · Bank credit",
            source="NovaCart Merchant Agreement",
            source_clause="Page 6 · Clause 6.2",
            clause_id="CLAUSE_6_2",
            logical_control_key="SETTLEMENT_BANK_ARITHMETIC",
            parameters={"tolerance": "0.01"},
            conditions=["settlement_status == processed"],
            extraction_method="SEEDED_STRUCTURED_EXTRACTION",
            approved_at=approved_at,
        ),
        Control(
            id="CTRL_REFUND",
            name="Refund Principal Integrity",
            control_type=ControlType.REFUND_INTEGRITY,
            expected="Deduct once · fee ₹0",
            scope="Successful refunds",
            source="NovaCart Merchant Agreement",
            source_clause="Page 7 · Clause 7.2",
            clause_id="CLAUSE_7_2",
            logical_control_key="REFUND_PRINCIPAL_INTEGRITY",
            parameters={"maximum_deductions": 1, "refund_fee": "0"},
            conditions=["refund_status == processed"],
            extraction_method="SEEDED_STRUCTURED_EXTRACTION",
            approved_at=approved_at,
        ),
        Control(
            id="CTRL_UNSUPPORTED_FEE_CANDIDATE",
            name="Unlisted Settlement Fee",
            control_type=ControlType.UNSUPPORTED_FEE,
            expected="₹0 unless expressly listed",
            scope="Settlement deductions",
            source="NovaCart Merchant Agreement",
            source_clause="Page 5 · Clause 4.6",
            status="DRAFT",
            clause_id="CLAUSE_4_6",
            logical_control_key="UNLISTED_SETTLEMENT_FEE",
            parameters={"allowlist": ["processing_fee", "gst", "refund_principal"]},
            conditions=["deduction_type not in allowlist"],
            extraction_method="BOUNDED_CANDIDATE_EXTRACTION",
        ),
    ]


class GovernanceStore:
    def __init__(self) -> None:
        self.controls: list[Control] = []
        self.backtested_control_ids: set[str] = set()
        self.backtest_actors: dict[str, str] = {}
        self.reset()

    def reset(self) -> None:
        self.controls.clear()
        self.controls.extend(control.model_copy(deep=True) for control in _control_templates())
        self.backtested_control_ids.clear()
        self.backtest_actors.clear()

    def agreement(self, agreement_id: str) -> Agreement:
        if agreement_id != AGREEMENT_ID:
            raise KeyError(agreement_id)
        return AGREEMENT

    def control(self, control_id: str) -> Control:
        for control in self.controls:
            if control.id == control_id:
                return control
        raise KeyError(control_id)

    def proposals(self, agreement_id: str) -> list[ControlProposal]:
        self.agreement(agreement_id)
        clauses = {clause.id: clause for clause in CLAUSES}
        proposals: list[ControlProposal] = []
        for control in self.controls:
            if control.clause_id is None:
                continue
            clause = clauses[control.clause_id]
            proposals.append(
                ControlProposal(
                    id=f"PROP_{control.id}",
                    agreement_id=agreement_id,
                    clause_id=clause.id,
                    control_id=control.id,
                    status=control.status,
                    confidence=Decimal("0.99") if control.status == "APPROVED" else Decimal("0.93"),
                    rationale=(
                        "Structured rate, scope and effective period were extracted from "
                        "the cited clause."
                        if control.control_type == ControlType.MDR_RATE
                        else (
                            "The clause maps to deterministic parameters and explicit "
                            "applicability conditions."
                        )
                    ),
                    source_excerpt=clause.text,
                    extraction_method=control.extraction_method,
                    proposed_control=control,
                )
            )
        return proposals

    def record_backtest(self, control_id: str, *, actor: str = "demo-reviewer") -> None:
        self.control(control_id)
        self.backtested_control_ids.add(control_id)
        self.backtest_actors[control_id] = actor

    def approve(
        self, control_id: str, *, actor: str = "demo-approver", enforce_maker_checker: bool = False
    ) -> Control:
        control = self.control(control_id)
        if control.status != "DRAFT":
            raise RuntimeError("Only draft controls can be approved")
        if control_id not in self.backtested_control_ids:
            raise RuntimeError("A successful backtest is required before approval")
        if enforce_maker_checker and self.backtest_actors.get(control_id) == actor:
            raise RuntimeError("Control approval requires a different backtester and approver")
        control.status = "APPROVED"
        control.approved_at = datetime.now(timezone.utc)
        return control

    def versions(self, logical_control_key: str) -> list[Control]:
        versions = [
            control
            for control in self.controls
            if control.logical_control_key == logical_control_key and control.status == "APPROVED"
        ]
        return sorted(versions, key=lambda control: control.version)

    def effective_control(self, logical_control_key: str, at: date) -> Control:
        matches = [
            control
            for control in self.versions(logical_control_key)
            if control.effective_from <= at
            and (control.effective_to is None or at <= control.effective_to)
        ]
        if len(matches) != 1:
            raise KeyError(
                f"No unique approved control for {logical_control_key} at {at.isoformat()}"
            )
        return matches[0]

    def coverage(self, run_id: str, payments: list[PaymentLifecycle]) -> ControlCoverageSummary:
        payment_count = len(payments)
        refund_count = sum(1 for payment in payments if payment.refund_amount > 0)
        bank_count = sum(1 for payment in payments if payment.bank_credit is not None)
        unsupported_count = sum(1 for payment in payments if payment.unsupported_fee > 0)
        unsupported_approved = self.control("CTRL_UNSUPPORTED_FEE_CANDIDATE").status == "APPROVED"
        items = [
            ControlCoverageItem(
                id="COV_PAYMENT_FEE",
                relationship="PAYMENT → FEE",
                description="Contractual processing-fee deduction",
                material_edge_count=payment_count,
                governed_edge_count=payment_count,
                status=CoverageStatus.GOVERNED,
                control_ids=["CTRL_MDR_DOMESTIC"],
            ),
            ControlCoverageItem(
                id="COV_FEE_TAX",
                relationship="FEE → TAX",
                description="GST computed on the approved processing fee",
                material_edge_count=payment_count,
                governed_edge_count=payment_count,
                status=CoverageStatus.GOVERNED,
                control_ids=["CTRL_GST_FEE"],
            ),
            ControlCoverageItem(
                id="COV_CAPTURE_SETTLEMENT",
                relationship="CAPTURE → SETTLEMENT",
                description="Settlement timing and inclusion",
                material_edge_count=payment_count,
                governed_edge_count=payment_count,
                status=CoverageStatus.GOVERNED,
                control_ids=["CTRL_SETTLEMENT_SLA"],
            ),
            ControlCoverageItem(
                id="COV_SETTLEMENT_BANK",
                relationship="SETTLEMENT → BANK",
                description="Expected settlement and observed bank credit arithmetic",
                material_edge_count=bank_count,
                governed_edge_count=bank_count,
                status=CoverageStatus.GOVERNED,
                control_ids=["CTRL_SETTLEMENT_ARITHMETIC"],
            ),
            ControlCoverageItem(
                id="COV_REFUND_SETTLEMENT",
                relationship="REFUND → SETTLEMENT",
                description="Refund principal deducted no more than once",
                material_edge_count=refund_count,
                governed_edge_count=refund_count,
                status=CoverageStatus.GOVERNED,
                control_ids=["CTRL_REFUND"],
            ),
            ControlCoverageItem(
                id="COV_OTHER_DEDUCTION",
                relationship="OTHER DEDUCTION → SETTLEMENT",
                description="Unlisted fee deductions discovered by mutation testing",
                material_edge_count=unsupported_count,
                governed_edge_count=unsupported_count if unsupported_approved else 0,
                status=(
                    CoverageStatus.GOVERNED if unsupported_approved else CoverageStatus.UNGOVERNED
                ),
                control_ids=(["CTRL_UNSUPPORTED_FEE_CANDIDATE"] if unsupported_approved else []),
                blind_spot=(
                    None
                    if unsupported_approved
                    else "Clause 4.6 exists, but its extracted control remains DRAFT."
                ),
            ),
            ControlCoverageItem(
                id="COV_METHOD_CLASSIFICATION",
                relationship="PAYMENT → METHOD CLASSIFICATION",
                description="Protection against silent method reclassification",
                material_edge_count=1,
                governed_edge_count=0,
                status=CoverageStatus.UNGOVERNED,
                control_ids=[],
                blind_spot=(
                    "No approved control attests the original payment-method classification."
                ),
            ),
        ]
        total = sum(item.material_edge_count for item in items)
        governed = sum(item.governed_edge_count for item in items)
        partial = sum(
            item.material_edge_count - item.governed_edge_count
            for item in items
            if item.status == CoverageStatus.PARTIALLY_GOVERNED
        )
        ungoverned = total - governed - partial
        percentage = (Decimal(governed) / Decimal(total)) if total else Decimal("1")
        return ControlCoverageSummary(
            run_id=run_id,
            total_material_edges=total,
            governed_edges=governed,
            partially_governed_edges=partial,
            ungoverned_edges=ungoverned,
            coverage_percentage=percentage.quantize(Decimal("0.0001")),
            items=items,
        )


governance = GovernanceStore()
CONTROLS = governance.controls
