"""Persist clause-level numbering, titles, and source offsets.

Revision ID: 0015_clause_provenance
Revises: 0014_evaluation_check_name
Create Date: 2026-08-29
"""

import sqlalchemy as sa

from alembic import op

revision = "0015_clause_provenance"
down_revision = "0014_evaluation_check_name"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("agreement_clauses", sa.Column("clause_number", sa.String(32), nullable=True))
    op.add_column("agreement_clauses", sa.Column("clause_title", sa.String(240), nullable=True))
    op.add_column("agreement_clauses", sa.Column("source_offsets", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("agreement_clauses", "source_offsets")
    op.drop_column("agreement_clauses", "clause_title")
    op.drop_column("agreement_clauses", "clause_number")
