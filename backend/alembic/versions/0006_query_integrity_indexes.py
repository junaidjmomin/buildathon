"""Add tenant-leading read indexes and tenant-unique root-cause identifiers.

Revision ID: 0006_query_integrity_indexes
Revises: 0005_exception_cases
Create Date: 2026-08-27
"""

from alembic import op

revision = "0006_query_integrity_indexes"
down_revision = "0005_exception_cases"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_runs_tenant_completed",
        "runs",
        ["tenant_id", "completed_at", "created_at"],
    )
    op.create_index(
        "ix_events_tenant_run_type_external",
        "events",
        ["tenant_id", "run_id", "event_type", "external_id"],
    )
    op.create_index(
        "ix_violations_tenant_run_occurred",
        "violations",
        ["tenant_id", "run_id", "occurred_at", "id"],
    )
    op.create_index(
        "ix_violations_tenant_root_occurred",
        "violations",
        ["tenant_id", "root_cause_id", "occurred_at"],
    )
    op.create_index(
        "ix_control_evaluations_tenant_run_target_outcome",
        "control_evaluations",
        [
            "tenant_id",
            "run_id",
            "target_type",
            "target_id",
            "outcome",
            "evaluated_at",
        ],
    )
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("root_causes") as batch_op:
            batch_op.create_unique_constraint(
                "uq_root_causes_tenant_id",
                ["tenant_id", "id"],
            )
    else:
        op.create_unique_constraint(
            "uq_root_causes_tenant_id",
            "root_causes",
            ["tenant_id", "id"],
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("root_causes") as batch_op:
            batch_op.drop_constraint("uq_root_causes_tenant_id", type_="unique")
    else:
        op.drop_constraint(
            "uq_root_causes_tenant_id",
            "root_causes",
            type_="unique",
        )
    op.drop_index(
        "ix_control_evaluations_tenant_run_target_outcome",
        table_name="control_evaluations",
    )
    op.drop_index(
        "ix_violations_tenant_root_occurred",
        table_name="violations",
    )
    op.drop_index(
        "ix_violations_tenant_run_occurred",
        table_name="violations",
    )
    op.drop_index(
        "ix_events_tenant_run_type_external",
        table_name="events",
    )
    op.drop_index("ix_runs_tenant_completed", table_name="runs")
