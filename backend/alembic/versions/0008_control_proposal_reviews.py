"""Add deterministic proposal verification and maker-checker activation state.

Revision ID: 0008_control_proposal_reviews
Revises: 0007_tenant_agreement_governance
Create Date: 2026-08-27
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0008_control_proposal_reviews"
down_revision = "0007_tenant_agreement_governance"
branch_labels = None
depends_on = None

JSON_DOCUMENT = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    with op.batch_alter_table("control_proposals") as batch_op:
        batch_op.add_column(sa.Column("version", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("verification_status", sa.String(32), nullable=True))
        batch_op.add_column(sa.Column("verification_result", JSON_DOCUMENT, nullable=True))
        batch_op.add_column(sa.Column("verified_by", sa.String(160), nullable=True))
        batch_op.add_column(sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("approved_by", sa.String(160), nullable=True))
        batch_op.add_column(sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE control_proposals SET version = 1, verification_status = 'NOT_RUN'")
    with op.batch_alter_table("control_proposals") as batch_op:
        batch_op.alter_column("version", existing_type=sa.Integer(), nullable=False)
        batch_op.alter_column(
            "verification_status",
            existing_type=sa.String(32),
            nullable=False,
        )
        batch_op.create_check_constraint("ck_control_proposals_version", "version >= 1")
        batch_op.create_unique_constraint(
            "uq_control_proposals_tenant_control",
            ["tenant_id", "control_id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("control_proposals") as batch_op:
        batch_op.drop_constraint(
            "uq_control_proposals_tenant_control",
            type_="unique",
        )
        batch_op.drop_constraint("ck_control_proposals_version", type_="check")
        batch_op.drop_column("approved_at")
        batch_op.drop_column("approved_by")
        batch_op.drop_column("verified_at")
        batch_op.drop_column("verified_by")
        batch_op.drop_column("verification_result")
        batch_op.drop_column("verification_status")
        batch_op.drop_column("version")
