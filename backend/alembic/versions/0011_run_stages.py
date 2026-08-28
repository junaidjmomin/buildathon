"""Persist per-stage progress and timing for control runs.

Revision ID: 0011_run_stages
Revises: 0010_manual_agreement_clauses
Create Date: 2026-08-28
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0011_run_stages"
down_revision = "0010_manual_agreement_clauses"
branch_labels = None
depends_on = None

JSON_DOCUMENT = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "run_stages",
        sa.Column("tenant_id", sa.String(length=120), primary_key=True),
        sa.Column("run_id", sa.String(length=80), primary_key=True),
        sa.Column("stage_index", sa.Integer(), primary_key=True),
        sa.Column("stage", sa.String(length=48), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("detail", JSON_DOCUMENT, nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "run_id"],
            ["runs.tenant_id", "runs.id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_run_stages_tenant_run_order",
        "run_stages",
        ["tenant_id", "run_id", "stage_index"],
    )
    if op.get_bind().dialect.name == "postgresql":
        op.execute('ALTER TABLE "run_stages" ENABLE ROW LEVEL SECURITY')
        op.execute('ALTER TABLE "run_stages" FORCE ROW LEVEL SECURITY')
        op.execute(
            """CREATE POLICY tenant_isolation ON "run_stages"
               USING (tenant_id = current_setting('app.tenant_id', true))
               WITH CHECK (tenant_id = current_setting('app.tenant_id', true))"""
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute('DROP POLICY IF EXISTS tenant_isolation ON "run_stages"')
    op.drop_index("ix_run_stages_tenant_run_order", table_name="run_stages")
    op.drop_table("run_stages")
