"""Add check_name discriminator to control evaluations.

One control can execute several distinct deterministic checks on the same
target (settlement arithmetic and missing-bank evidence both run under
SETTLEMENT_BANK_ARITHMETIC). The previous unique constraint silently
collapsed those rows, hiding evaluations and desynchronizing the summary
violation count from persisted violations.

Revision ID: 0014_evaluation_check_name
Revises: 0013_violation_taxonomy
Create Date: 2026-08-29
"""

import sqlalchemy as sa

from alembic import op

revision = "0014_evaluation_check_name"
down_revision = "0013_violation_taxonomy"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "control_evaluations",
        sa.Column("check_name", sa.String(64), nullable=False, server_default=""),
    )
    with op.batch_alter_table("control_evaluations") as batch_op:
        batch_op.drop_constraint("uq_control_evaluations_target", type_="unique")
        batch_op.create_unique_constraint(
            "uq_control_evaluations_target",
            [
                "tenant_id",
                "run_id",
                "control_id",
                "target_type",
                "target_id",
                "check_name",
            ],
        )


def downgrade() -> None:
    with op.batch_alter_table("control_evaluations") as batch_op:
        batch_op.drop_constraint("uq_control_evaluations_target", type_="unique")
        batch_op.create_unique_constraint(
            "uq_control_evaluations_target",
            ["tenant_id", "run_id", "control_id", "target_type", "target_id"],
        )
    op.drop_column("control_evaluations", "check_name")
