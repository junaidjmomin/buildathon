"""Persist tenant agreements, extracted clauses, and draft control proposals.

Revision ID: 0007_tenant_agreement_governance
Revises: 0006_query_integrity_indexes
Create Date: 2026-08-27
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0007_tenant_agreement_governance"
down_revision = "0006_query_integrity_indexes"
branch_labels = None
depends_on = None

JSON_DOCUMENT = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
RATE = sa.Numeric(12, 8)
TENANT_TABLES = ("agreements", "agreement_clauses", "control_proposals")


def upgrade() -> None:
    op.create_table(
        "agreements",
        sa.Column("tenant_id", sa.String(120), nullable=False),
        sa.Column("id", sa.String(120), nullable=False),
        sa.Column("artifact_id", sa.String(120), nullable=False),
        sa.Column("merchant", sa.String(200), nullable=False),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("source_type", sa.String(64), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("created_by", sa.String(160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('UPLOADED', 'EXTRACTED', 'APPROVED', 'ARCHIVED')",
            name="ck_agreements_status",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "artifact_id"],
            ["artifacts.tenant_id", "artifacts.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "id"),
        sa.UniqueConstraint(
            "tenant_id",
            "artifact_id",
            name="uq_agreements_tenant_artifact",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "content_hash",
            name="uq_agreements_tenant_content_hash",
        ),
    )
    op.create_index(
        "ix_agreements_tenant_created",
        "agreements",
        ["tenant_id", "created_at", "id"],
    )

    op.create_table(
        "agreement_clauses",
        sa.Column("tenant_id", sa.String(120), nullable=False),
        sa.Column("agreement_id", sa.String(120), nullable=False),
        sa.Column("id", sa.String(120), nullable=False),
        sa.Column("reference", sa.String(120), nullable=False),
        sa.Column("page", sa.Integer(), nullable=False),
        sa.Column("heading", sa.String(240), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "agreement_id"],
            ["agreements.tenant_id", "agreements.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "agreement_id", "id"),
    )
    op.create_index(
        "ix_agreement_clauses_tenant_agreement_page",
        "agreement_clauses",
        ["tenant_id", "agreement_id", "page", "id"],
    )

    op.create_table(
        "control_proposals",
        sa.Column("tenant_id", sa.String(120), nullable=False),
        sa.Column("id", sa.String(120), nullable=False),
        sa.Column("agreement_id", sa.String(120), nullable=False),
        sa.Column("clause_id", sa.String(120), nullable=False),
        sa.Column("control_id", sa.String(120), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("confidence", RATE, nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("source_excerpt", sa.Text(), nullable=False),
        sa.Column("extraction_method", sa.String(80), nullable=False),
        sa.Column("proposed_control", JSON_DOCUMENT, nullable=False),
        sa.Column("execution_id", sa.String(120), nullable=True),
        sa.Column("created_by", sa.String(160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('DRAFT', 'REVIEW_REQUIRED', 'APPROVED', 'REJECTED')",
            name="ck_control_proposals_status",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "agreement_id"],
            ["agreements.tenant_id", "agreements.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "agreement_id", "clause_id"],
            [
                "agreement_clauses.tenant_id",
                "agreement_clauses.agreement_id",
                "agreement_clauses.id",
            ],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "id"),
    )
    op.create_index(
        "ix_control_proposals_tenant_agreement_status",
        "control_proposals",
        ["tenant_id", "agreement_id", "status", "created_at"],
    )

    if op.get_bind().dialect.name == "postgresql":
        for table in TENANT_TABLES:
            op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
            op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
            op.execute(
                f'''CREATE POLICY tenant_isolation ON "{table}"
                    USING (tenant_id = current_setting('app.tenant_id', true))
                    WITH CHECK (tenant_id = current_setting('app.tenant_id', true))'''
            )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        for table in reversed(TENANT_TABLES):
            op.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{table}"')
    op.drop_table("control_proposals")
    op.drop_table("agreement_clauses")
    op.drop_table("agreements")
