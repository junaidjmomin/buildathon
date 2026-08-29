"""Canonical violation taxonomy on persisted violations.

Revision ID: 0013_violation_taxonomy
Revises: 0012_durable_lineage_metrics
Create Date: 2026-08-29
"""

import sqlalchemy as sa

from alembic import op

revision = "0013_violation_taxonomy"
down_revision = "0012_durable_lineage_metrics"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "violations",
        sa.Column("violation_type", sa.String(length=64), nullable=False, server_default=""),
    )
    op.add_column(
        "violations",
        sa.Column("target_type", sa.String(length=32), nullable=False, server_default="PAYMENT"),
    )
    op.create_index(
        "ix_violations_tenant_run_vtype",
        "violations",
        ["tenant_id", "run_id", "violation_type"],
    )


def downgrade() -> None:
    op.drop_index("ix_violations_tenant_run_vtype", table_name="violations")
    op.drop_column("violations", "target_type")
    op.drop_column("violations", "violation_type")
