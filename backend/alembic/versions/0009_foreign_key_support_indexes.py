"""Add indexes supporting agreement and case foreign keys.

Revision ID: 0009_foreign_key_support_indexes
Revises: 0008_control_proposal_reviews
Create Date: 2026-08-27
"""

from alembic import op

revision = "0009_foreign_key_support_indexes"
down_revision = "0008_control_proposal_reviews"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_control_proposals_tenant_agreement_clause",
        "control_proposals",
        ["tenant_id", "agreement_id", "clause_id"],
    )
    op.create_index(
        "ix_exception_cases_tenant_run_violation",
        "exception_cases",
        ["tenant_id", "run_id", "primary_violation_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_exception_cases_tenant_run_violation",
        table_name="exception_cases",
    )
    op.drop_index(
        "ix_control_proposals_tenant_agreement_clause",
        table_name="control_proposals",
    )
