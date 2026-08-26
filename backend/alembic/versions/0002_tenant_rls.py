"""Force tenant isolation on every tenant-owned table.

Revision ID: 0002_tenant_rls
Revises: 0001_initial
Create Date: 2026-08-26
"""

from alembic import op

revision = "0002_tenant_rls"
down_revision = "0001_initial"
branch_labels = None
depends_on = None

TENANT_TABLES = (
    "runs",
    "events",
    "event_edges",
    "controls",
    "violations",
    "root_causes",
    "mutation_tests",
    "artifacts",
    "audit_log",
)


def upgrade() -> None:
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


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    for table in reversed(TENANT_TABLES):
        op.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{table}"')
        op.execute(f'ALTER TABLE "{table}" NO FORCE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY')
