"""Persist agent execution traces and accelerate integration status reads.

Revision ID: 0004_agent_execution_state
Revises: 0003_durable_evidence_jobs
Create Date: 2026-08-26
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0004_agent_execution_state"
down_revision = "0003_durable_evidence_jobs"
branch_labels = None
depends_on = None

JSON_DOCUMENT = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_index(
        "ix_background_jobs_tenant_type_status_updated",
        "background_jobs",
        ["tenant_id", "job_type", "status", "updated_at"],
    )
    op.create_table(
        "agent_executions",
        sa.Column("tenant_id", sa.String(120), nullable=False),
        sa.Column("id", sa.String(120), nullable=False),
        sa.Column("workflow", sa.String(64), nullable=False),
        sa.Column("resource_type", sa.String(64), nullable=False),
        sa.Column("resource_id", sa.String(160), nullable=False),
        sa.Column("status", sa.String(48), nullable=False),
        sa.Column("result", JSON_DOCUMENT, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "workflow IN ('ROOT_CAUSE_INVESTIGATION', 'BLIND_SPOT_REMEDIATION', "
            "'AGREEMENT_CONTROL_COMPILER')",
            name="ck_agent_executions_workflow",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "id"),
    )
    op.create_index(
        "ix_agent_executions_tenant_resource",
        "agent_executions",
        ["tenant_id", "resource_type", "resource_id", "completed_at"],
    )
    op.create_index(
        "ix_agent_executions_tenant_updated",
        "agent_executions",
        ["tenant_id", "updated_at"],
    )
    if op.get_bind().dialect.name == "postgresql":
        op.execute('ALTER TABLE "agent_executions" ENABLE ROW LEVEL SECURITY')
        op.execute('ALTER TABLE "agent_executions" FORCE ROW LEVEL SECURITY')
        op.execute(
            """CREATE POLICY tenant_isolation ON "agent_executions"
               USING (tenant_id = current_setting('app.tenant_id', true))
               WITH CHECK (tenant_id = current_setting('app.tenant_id', true))"""
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute('DROP POLICY IF EXISTS tenant_isolation ON "agent_executions"')
    op.drop_table("agent_executions")
    op.drop_index(
        "ix_background_jobs_tenant_type_status_updated",
        table_name="background_jobs",
    )
