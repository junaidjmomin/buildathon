from __future__ import annotations

import os

from app.domain.models import McpEvidenceCapability

ALLOWED_EVIDENCE_TOOLS = [
    "fetch_payment",
    "fetch_all_payments",
    "fetch_refund",
    "fetch_all_refunds",
    "fetch_multiple_refunds_for_payment",
    "fetch_all_settlements",
    "fetch_settlement_with_id",
    "fetch_settlement_recon_details",
]

PROHIBITED_TOOL_CLASSES = [
    "payment_creation_or_capture",
    "refund_initiation",
    "payout_or_transfer",
    "instant_settlement",
    "account_or_webhook_mutation",
]


def capability() -> McpEvidenceCapability:
    """Describe the optional MCP boundary without invoking an external agent.

    Direct API ingestion remains the input of record. Enabling MCP only makes
    bounded read-only evidence lookups available to an investigator; it never
    changes a control, calculation, case status, or hypothesis verdict.
    """

    enabled = os.getenv("RAZORPAY_MCP_ENABLED", "false").lower() == "true"
    return McpEvidenceCapability(
        enabled=enabled,
        authoritative=False,
        provider="Official Razorpay MCP · https://mcp.razorpay.com/mcp",
        allowed_tools=ALLOWED_EVIDENCE_TOOLS,
        prohibited_tool_classes=PROHIBITED_TOOL_CLASSES,
        result_policy=(
            "Supplementary evidence only. Any AI-derived hypothesis must be independently "
            "classified PROVEN, REJECTED or UNRESOLVED by sl3dge."
        ),
    )
