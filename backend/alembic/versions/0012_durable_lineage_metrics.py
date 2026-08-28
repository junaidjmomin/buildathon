"""Persist violation lineage and root-cause impact metrics.

Revision ID: 0012_durable_lineage_metrics
Revises: 0011_run_stages
Create Date: 2026-08-28
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

JSON_DOCUMENT = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


revision = "0012_durable_lineage_metrics"
down_revision = "0011_run_stages"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "violations",
        sa.Column("parent_violation_id", sa.String(length=120), nullable=True),
    )
    op.add_column(
        "violations",
        sa.Column("root_violation_id", sa.String(length=120), nullable=True),
    )
    op.add_column(
        "violations",
        sa.Column("lineage_type", sa.String(length=32), nullable=False, server_default="PRIMARY"),
    )
    op.add_column(
        "violations",
        sa.Column("causal_evidence", JSON_DOCUMENT, nullable=False, server_default="{}"),
    )
    op.create_index(
        "ix_violations_tenant_run_lineage",
        "violations",
        ["tenant_id", "run_id", "root_violation_id", "parent_violation_id"],
    )

    op.add_column(
        "root_causes",
        sa.Column("direct_impact", sa.Numeric(20, 2), nullable=False, server_default="0"),
    )
    op.add_column(
        "root_causes",
        sa.Column("downstream_impact", sa.Numeric(20, 2), nullable=False, server_default="0"),
    )
    op.add_column(
        "root_causes",
        sa.Column("total_impact", sa.Numeric(20, 2), nullable=False, server_default="0"),
    )
    op.add_column(
        "root_causes",
        sa.Column("primary_violation_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "root_causes",
        sa.Column("downstream_violation_count", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    for column in (
        "downstream_violation_count",
        "primary_violation_count",
        "total_impact",
        "downstream_impact",
        "direct_impact",
    ):
        op.drop_column("root_causes", column)
    op.drop_index("ix_violations_tenant_run_lineage", table_name="violations")
    for column in ("causal_evidence", "lineage_type", "root_violation_id", "parent_violation_id"):
        op.drop_column("violations", column)
