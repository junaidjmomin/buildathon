"""Create canonical sl3dge persistence schema.

Revision ID: 0001_initial
Revises:
Create Date: 2026-08-26
"""

from alembic import op

from app.persistence.orm import Base

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())
