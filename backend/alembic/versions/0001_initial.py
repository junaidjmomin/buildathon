"""Create the immutable canonical sl3dge persistence schema.

Revision ID: 0001_initial
Revises:
Create Date: 2026-08-26
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

JSON_DOCUMENT = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
MONEY = sa.Numeric(20, 2)
RATE = sa.Numeric(12, 8)


def upgrade() -> None:
    op.create_table(
        "audit_log",
        sa.Column("tenant_id", sa.String(120), nullable=False),
        sa.Column("id", sa.String(80), nullable=False),
        sa.Column("actor_id", sa.String(160), nullable=False),
        sa.Column("action", sa.String(80), nullable=False),
        sa.Column("resource_type", sa.String(80), nullable=False),
        sa.Column("resource_id", sa.String(160), nullable=False),
        sa.Column("outcome", sa.String(32), nullable=False),
        sa.Column("details", JSON_DOCUMENT, nullable=False),
        sa.Column("request_id", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("tenant_id", "id"),
    )
    op.create_index("ix_audit_tenant_created", "audit_log", ["tenant_id", "created_at"])
    op.create_index(
        "ix_audit_tenant_resource",
        "audit_log",
        ["tenant_id", "resource_type", "resource_id"],
    )

    op.create_table(
        "controls",
        sa.Column("tenant_id", sa.String(120), nullable=False),
        sa.Column("id", sa.String(120), nullable=False),
        sa.Column("logical_control_key", sa.String(120), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("control_type", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("agreement_id", sa.String(120), nullable=False),
        sa.Column("clause_id", sa.String(120), nullable=True),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("parameters", JSON_DOCUMENT, nullable=False),
        sa.Column("definition", JSON_DOCUMENT, nullable=False),
        sa.PrimaryKeyConstraint("tenant_id", "id"),
    )
    op.create_index("ix_controls_control_type", "controls", ["control_type"])
    op.create_index("ix_controls_status", "controls", ["status"])
    op.create_index(
        "ix_controls_tenant_logical_effective",
        "controls",
        ["tenant_id", "logical_control_key", "effective_from"],
    )

    op.create_table(
        "runs",
        sa.Column("tenant_id", sa.String(120), nullable=False),
        sa.Column("id", sa.String(80), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("seed", sa.Integer(), nullable=True),
        sa.Column("manifest", JSON_DOCUMENT, nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("tenant_id", "id"),
    )
    op.create_index("ix_runs_status", "runs", ["status"])

    op.create_table(
        "artifacts",
        sa.Column("tenant_id", sa.String(120), nullable=False),
        sa.Column("id", sa.String(120), nullable=False),
        sa.Column("run_id", sa.String(80), nullable=True),
        sa.Column("case_id", sa.String(120), nullable=True),
        sa.Column("kind", sa.String(48), nullable=False),
        sa.Column("bucket", sa.String(80), nullable=False),
        sa.Column("object_path", sa.Text(), nullable=False),
        sa.Column("content_type", sa.String(120), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "run_id"],
            ["runs.tenant_id", "runs.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "id"),
    )
    op.create_index("ix_artifacts_case_id", "artifacts", ["case_id"])
    op.create_index(
        "ix_artifacts_tenant_run_kind", "artifacts", ["tenant_id", "run_id", "kind"]
    )

    op.create_table(
        "events",
        sa.Column("tenant_id", sa.String(120), nullable=False),
        sa.Column("run_id", sa.String(80), nullable=False),
        sa.Column("id", sa.String(120), nullable=False),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("external_id", sa.String(120), nullable=False),
        sa.Column("event_type", sa.String(48), nullable=False),
        sa.Column("amount", MONEY, nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(48), nullable=True),
        sa.Column("raw_payload", JSON_DOCUMENT, nullable=False),
        sa.Column("normalized_payload", JSON_DOCUMENT, nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "run_id"],
            ["runs.tenant_id", "runs.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "run_id", "id"),
    )
    op.create_index("ix_events_occurred_at", "events", ["occurred_at"])
    op.create_index("ix_events_tenant_external", "events", ["tenant_id", "external_id"])
    op.create_index(
        "ix_events_tenant_run_type", "events", ["tenant_id", "run_id", "event_type"]
    )

    op.create_table(
        "mutation_tests",
        sa.Column("tenant_id", sa.String(120), nullable=False),
        sa.Column("run_id", sa.String(80), nullable=False),
        sa.Column("id", sa.String(120), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("mutation_count", sa.Integer(), nullable=False),
        sa.Column("detected_count", sa.Integer(), nullable=False),
        sa.Column("missed_count", sa.Integer(), nullable=False),
        sa.Column("detection_rate", RATE, nullable=False),
        sa.Column("false_positive_count", sa.Integer(), nullable=False),
        sa.Column("results", JSON_DOCUMENT, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "run_id"],
            ["runs.tenant_id", "runs.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "run_id", "id"),
    )

    op.create_table(
        "root_causes",
        sa.Column("tenant_id", sa.String(120), nullable=False),
        sa.Column("run_id", sa.String(80), nullable=False),
        sa.Column("id", sa.String(120), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("category", sa.String(80), nullable=False),
        sa.Column("affected_count", sa.Integer(), nullable=False),
        sa.Column("verified_impact", MONEY, nullable=False),
        sa.Column("verification_status", sa.String(32), nullable=False),
        sa.Column("evidence", JSON_DOCUMENT, nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "run_id"],
            ["runs.tenant_id", "runs.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "run_id", "id"),
    )

    op.create_table(
        "violations",
        sa.Column("tenant_id", sa.String(120), nullable=False),
        sa.Column("run_id", sa.String(80), nullable=False),
        sa.Column("id", sa.String(120), nullable=False),
        sa.Column("payment_id", sa.String(120), nullable=False),
        sa.Column("category", sa.String(80), nullable=False),
        sa.Column("control_type", sa.String(64), nullable=False),
        sa.Column("difference", MONEY, nullable=False),
        sa.Column("financial_impact", MONEY, nullable=False),
        sa.Column("confidence", RATE, nullable=False),
        sa.Column("root_cause_id", sa.String(120), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("evidence", JSON_DOCUMENT, nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "run_id"],
            ["runs.tenant_id", "runs.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "run_id", "id"),
    )
    op.create_index("ix_violations_payment_id", "violations", ["payment_id"])
    op.create_index("ix_violations_root_cause_id", "violations", ["root_cause_id"])
    op.create_index(
        "ix_violations_tenant_run_category",
        "violations",
        ["tenant_id", "run_id", "category"],
    )

    op.create_table(
        "event_edges",
        sa.Column("tenant_id", sa.String(120), nullable=False),
        sa.Column("run_id", sa.String(80), nullable=False),
        sa.Column("id", sa.String(140), nullable=False),
        sa.Column("from_event_id", sa.String(120), nullable=False),
        sa.Column("to_event_id", sa.String(120), nullable=False),
        sa.Column("relationship", sa.String(64), nullable=False),
        sa.Column("confidence", RATE, nullable=False),
        sa.Column("method", sa.String(32), nullable=False),
        sa.Column("evidence", JSON_DOCUMENT, nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "run_id"],
            ["runs.tenant_id", "runs.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "run_id", "from_event_id"],
            ["events.tenant_id", "events.run_id", "events.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "run_id", "to_event_id"],
            ["events.tenant_id", "events.run_id", "events.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "run_id", "id"),
    )
    op.create_index("ix_event_edges_from_event_id", "event_edges", ["from_event_id"])
    op.create_index("ix_event_edges_to_event_id", "event_edges", ["to_event_id"])
    op.create_index(
        "ix_edges_tenant_run_relationship",
        "event_edges",
        ["tenant_id", "run_id", "relationship"],
    )


def downgrade() -> None:
    op.drop_table("event_edges")
    op.drop_table("violations")
    op.drop_table("root_causes")
    op.drop_table("mutation_tests")
    op.drop_table("events")
    op.drop_table("artifacts")
    op.drop_table("runs")
    op.drop_table("controls")
    op.drop_table("audit_log")
