"""Add durable evidence-backed exception cases.

Revision ID: 0005_exception_cases
Revises: 0004_agent_execution_state
Create Date: 2026-08-27
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0005_exception_cases"
down_revision = "0004_agent_execution_state"
branch_labels = None
depends_on = None

JSON_DOCUMENT = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
MONEY = sa.Numeric(20, 2)


def upgrade() -> None:
    op.create_table(
        "exception_cases",
        sa.Column("tenant_id", sa.String(120), nullable=False),
        sa.Column("id", sa.String(120), nullable=False),
        sa.Column("run_id", sa.String(80), nullable=False),
        sa.Column("root_cause_id", sa.String(120), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("payment_id", sa.String(120), nullable=False),
        sa.Column("primary_violation_id", sa.String(120), nullable=False),
        sa.Column("violation_ids", JSON_DOCUMENT, nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("verified_impact", MONEY, nullable=False),
        sa.Column("evidence", JSON_DOCUMENT, nullable=False),
        sa.Column("audit_trail", JSON_DOCUMENT, nullable=False),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('OPEN', 'VERIFIED', 'ESCALATED', 'RESOLVED')",
            name="ck_exception_cases_status",
        ),
        sa.CheckConstraint("version >= 1", name="ck_exception_cases_version"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "run_id"],
            ["runs.tenant_id", "runs.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "run_id", "primary_violation_id"],
            ["violations.tenant_id", "violations.run_id", "violations.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "run_id", "root_cause_id"],
            ["root_causes.tenant_id", "root_causes.run_id", "root_causes.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "id"),
    )
    op.create_index(
        "ix_exception_cases_tenant_run_status",
        "exception_cases",
        ["tenant_id", "run_id", "status", "updated_at"],
    )
    op.create_index(
        "ix_exception_cases_tenant_root",
        "exception_cases",
        ["tenant_id", "root_cause_id"],
    )
    if op.get_bind().dialect.name == "postgresql":
        op.execute('ALTER TABLE "exception_cases" ENABLE ROW LEVEL SECURITY')
        op.execute('ALTER TABLE "exception_cases" FORCE ROW LEVEL SECURITY')
        op.execute(
            """CREATE POLICY tenant_isolation ON "exception_cases"
               USING (tenant_id = current_setting('app.tenant_id', true))
               WITH CHECK (tenant_id = current_setting('app.tenant_id', true))"""
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute('DROP POLICY IF EXISTS tenant_isolation ON "exception_cases"')
    op.drop_table("exception_cases")
