"""Add immutable source evidence, control evaluations, and durable jobs.

Revision ID: 0003_durable_evidence_jobs
Revises: 0002_tenant_rls
Create Date: 2026-08-26
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0003_durable_evidence_jobs"
down_revision = "0002_tenant_rls"
branch_labels = None
depends_on = None

JSON_DOCUMENT = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
MONEY = sa.Numeric(20, 2)
RATE = sa.Numeric(12, 8)
TENANT_TABLES = ("source_snapshots", "control_evaluations", "background_jobs")


def _enable_rls() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    for table in TENANT_TABLES:
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
        op.execute(
            f'''CREATE POLICY tenant_isolation ON "{table}"
                USING (tenant_id = current_setting('app.tenant_id', true))
                WITH CHECK (tenant_id = current_setting('app.tenant_id', true))'''
        )


def upgrade() -> None:
    op.create_table(
        "source_snapshots",
        sa.Column("tenant_id", sa.String(120), nullable=False),
        sa.Column("id", sa.String(120), nullable=False),
        sa.Column("run_id", sa.String(80), nullable=True),
        sa.Column("job_id", sa.String(120), nullable=True),
        sa.Column("source_system", sa.String(64), nullable=False),
        sa.Column("resource_type", sa.String(80), nullable=False),
        sa.Column("external_id", sa.String(160), nullable=False),
        sa.Column("source_version", sa.String(120), nullable=True),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("payload", JSON_DOCUMENT, nullable=False),
        sa.Column("provenance", JSON_DOCUMENT, nullable=False),
        sa.Column("source_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("tenant_id", "id"),
        sa.UniqueConstraint(
            "tenant_id",
            "source_system",
            "resource_type",
            "external_id",
            "content_sha256",
            name="uq_source_snapshots_tenant_fingerprint",
        ),
    )
    op.create_index(
        "ix_source_snapshots_tenant_external",
        "source_snapshots",
        ["tenant_id", "source_system", "resource_type", "external_id", "captured_at"],
    )
    op.create_index(
        "ix_source_snapshots_tenant_hash",
        "source_snapshots",
        ["tenant_id", "content_sha256"],
    )
    op.create_index("ix_source_snapshots_tenant_run", "source_snapshots", ["tenant_id", "run_id"])

    op.create_table(
        "control_evaluations",
        sa.Column("tenant_id", sa.String(120), nullable=False),
        sa.Column("run_id", sa.String(80), nullable=False),
        sa.Column("id", sa.String(120), nullable=False),
        sa.Column("control_id", sa.String(120), nullable=False),
        sa.Column("control_version", sa.Integer(), nullable=False),
        sa.Column("target_type", sa.String(64), nullable=False),
        sa.Column("target_id", sa.String(160), nullable=False),
        sa.Column("outcome", sa.String(32), nullable=False),
        sa.Column("expected_amount", MONEY, nullable=True),
        sa.Column("actual_amount", MONEY, nullable=True),
        sa.Column("tolerance_amount", MONEY, nullable=True),
        sa.Column("difference_amount", MONEY, nullable=True),
        sa.Column("financial_impact", MONEY, nullable=True),
        sa.Column("confidence", RATE, nullable=False),
        sa.Column("input_fingerprint", sa.String(64), nullable=False),
        sa.Column("engine_version", sa.String(80), nullable=False),
        sa.Column("source_snapshot_ids", JSON_DOCUMENT, nullable=False),
        sa.Column("evidence", JSON_DOCUMENT, nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "outcome IN ('PASS', 'VIOLATION', 'WARNING', 'UNRESOLVED')",
            name="ck_control_evaluations_outcome",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "run_id"],
            ["runs.tenant_id", "runs.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "control_id"],
            ["controls.tenant_id", "controls.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "run_id", "id"),
        sa.UniqueConstraint(
            "tenant_id",
            "run_id",
            "control_id",
            "target_type",
            "target_id",
            name="uq_control_evaluations_target",
        ),
    )
    op.create_index(
        "ix_control_evaluations_tenant_control",
        "control_evaluations",
        ["tenant_id", "control_id", "evaluated_at"],
    )
    op.create_index(
        "ix_control_evaluations_tenant_run_outcome",
        "control_evaluations",
        ["tenant_id", "run_id", "outcome"],
    )
    op.create_index(
        "ix_control_evaluations_tenant_target",
        "control_evaluations",
        ["tenant_id", "target_type", "target_id"],
    )

    op.create_table(
        "background_jobs",
        sa.Column("tenant_id", sa.String(120), nullable=False),
        sa.Column("id", sa.String(120), nullable=False),
        sa.Column("run_id", sa.String(80), nullable=True),
        sa.Column("job_type", sa.String(80), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("idempotency_key", sa.String(200), nullable=False),
        sa.Column("payload", JSON_DOCUMENT, nullable=False),
        sa.Column("result", JSON_DOCUMENT, nullable=True),
        sa.Column("error", JSON_DOCUMENT, nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("leased_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_owner", sa.String(160), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("attempt_count >= 0", name="ck_background_jobs_attempt_count"),
        sa.CheckConstraint("max_attempts >= 1", name="ck_background_jobs_max_attempts"),
        sa.CheckConstraint(
            "status IN ('QUEUED', 'RUNNING', 'RETRYABLE', 'SUCCEEDED', 'FAILED', 'CANCELLED')",
            name="ck_background_jobs_status",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "id"),
        sa.UniqueConstraint(
            "tenant_id",
            "job_type",
            "idempotency_key",
            name="uq_background_jobs_tenant_idempotency",
        ),
    )
    op.create_index(
        "ix_background_jobs_tenant_claim",
        "background_jobs",
        [
            "tenant_id",
            "status",
            "available_at",
            "lease_expires_at",
            "priority",
            "created_at",
        ],
    )
    op.create_index(
        "ix_background_jobs_tenant_run",
        "background_jobs",
        ["tenant_id", "run_id", "created_at"],
    )
    op.create_index(
        "ix_background_jobs_tenant_updated", "background_jobs", ["tenant_id", "updated_at"]
    )
    _enable_rls()


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        for table in reversed(TENANT_TABLES):
            op.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{table}"')
    op.drop_table("background_jobs")
    op.drop_table("control_evaluations")
    op.drop_table("source_snapshots")
