"""Persist extraction validation warnings on control proposals.

Revision ID: 0016_control_proposal_validation
Revises: 0015_clause_provenance
Create Date: 2026-08-29
"""

import sqlalchemy as sa

from alembic import op

revision = "0016_control_proposal_validation"
down_revision = "0015_clause_provenance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "control_proposals",
        sa.Column("validation_warnings", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("control_proposals", "validation_warnings")
