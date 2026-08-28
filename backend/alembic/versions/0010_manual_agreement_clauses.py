"""Track manual versus PDF-extracted agreement clauses.

Revision ID: 0010_manual_agreement_clauses
Revises: 0009_foreign_key_support_indexes
Create Date: 2026-08-28
"""

import sqlalchemy as sa

from alembic import op

revision = "0010_manual_agreement_clauses"
down_revision = "0009_foreign_key_support_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agreement_clauses",
        sa.Column(
            "source_type",
            sa.String(length=32),
            nullable=False,
            server_default="PDF_TEXT_EXTRACTION",
        ),
    )
    op.add_column(
        "agreement_clauses",
        sa.Column("created_by", sa.String(length=160), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("agreement_clauses", "created_by")
    op.drop_column("agreement_clauses", "source_type")
