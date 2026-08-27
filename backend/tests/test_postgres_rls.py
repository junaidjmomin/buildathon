from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError

POSTGRES_URL = os.getenv("TEST_POSTGRES_URL", "")
RUNTIME_ROLE = "sl3dge_ci_runtime"
RUNTIME_PASSWORD = "sl3dge-ci-runtime-password"

pytestmark = pytest.mark.skipif(
    not POSTGRES_URL,
    reason="TEST_POSTGRES_URL is required for PostgreSQL RLS integration tests",
)


def test_every_tenant_table_forces_rls_and_enforces_tenant_visibility() -> None:
    owner_engine = create_engine(POSTGRES_URL)
    runtime_engine = None
    now = datetime.now(timezone.utc)
    try:
        with owner_engine.begin() as connection:
            connection.execute(
                text(
                    f"""
                    DO $$
                    BEGIN
                        IF NOT EXISTS (
                            SELECT 1 FROM pg_roles WHERE rolname = '{RUNTIME_ROLE}'
                        ) THEN
                            CREATE ROLE {RUNTIME_ROLE} LOGIN PASSWORD '{RUNTIME_PASSWORD}'
                                NOINHERIT NOBYPASSRLS;
                        END IF;
                    END
                    $$;
                    """
                )
            )
            connection.execute(text(f"ALTER ROLE {RUNTIME_ROLE} PASSWORD '{RUNTIME_PASSWORD}'"))
            connection.execute(text(f"GRANT USAGE ON SCHEMA public TO {RUNTIME_ROLE}"))
            connection.execute(
                text(
                    "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA "
                    f"public TO {RUNTIME_ROLE}"
                )
            )
            connection.execute(
                text(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {RUNTIME_ROLE}")
            )
            policies = connection.execute(
                text(
                    """
                    SELECT c.relname,
                           c.relrowsecurity,
                           c.relforcerowsecurity,
                           EXISTS (
                               SELECT 1
                               FROM pg_policies p
                               WHERE p.schemaname = 'public'
                                 AND p.tablename = c.relname
                                 AND p.policyname = 'tenant_isolation'
                           ) AS has_tenant_policy
                    FROM pg_class c
                    JOIN pg_namespace n ON n.oid = c.relnamespace
                    JOIN pg_attribute a ON a.attrelid = c.oid
                    WHERE n.nspname = 'public'
                      AND c.relkind = 'r'
                      AND a.attname = 'tenant_id'
                      AND NOT a.attisdropped
                    ORDER BY c.relname
                    """
                )
            ).all()
            assert policies
            assert all(row.relrowsecurity for row in policies)
            assert all(row.relforcerowsecurity for row in policies)
            assert all(row.has_tenant_policy for row in policies)
            connection.execute(
                text(
                    """
                    INSERT INTO runs (
                        tenant_id, id, name, status, seed, manifest,
                        completed_at, created_at
                    ) VALUES
                        ('merchant_a', 'RUN_RLS_A', 'Tenant A', 'COMPLETE', NULL,
                         CAST('{}' AS jsonb), :now, :now),
                        ('merchant_b', 'RUN_RLS_B', 'Tenant B', 'COMPLETE', NULL,
                         CAST('{}' AS jsonb), :now, :now)
                    ON CONFLICT (tenant_id, id) DO NOTHING
                    """
                ),
                {"now": now},
            )

        runtime_url = make_url(POSTGRES_URL).set(
            username=RUNTIME_ROLE,
            password=RUNTIME_PASSWORD,
        )
        runtime_engine = create_engine(runtime_url)
        with runtime_engine.begin() as connection:
            connection.execute(text("SELECT set_config('app.tenant_id', 'merchant_a', true)"))
            visible = connection.execute(
                text("SELECT tenant_id, id FROM runs ORDER BY tenant_id, id")
            ).all()
            assert visible == [("merchant_a", "RUN_RLS_A")]
            changed = connection.execute(
                text("UPDATE runs SET name = 'blocked' WHERE tenant_id = 'merchant_b'")
            )
            assert changed.rowcount == 0

        with pytest.raises(DBAPIError), runtime_engine.begin() as connection:
            connection.execute(text("SELECT set_config('app.tenant_id', 'merchant_a', true)"))
            connection.execute(
                text(
                    """
                    INSERT INTO runs (
                        tenant_id, id, name, status, seed, manifest,
                        completed_at, created_at
                    ) VALUES (
                        'merchant_b', 'RUN_RLS_BLOCKED', 'Blocked', 'COMPLETE',
                        NULL, CAST('{}' AS jsonb), :now, :now
                    )
                    """
                ),
                {"now": now},
            )
    finally:
        if runtime_engine is not None:
            runtime_engine.dispose()
        with owner_engine.begin() as connection:
            connection.execute(
                text("DELETE FROM runs WHERE id IN ('RUN_RLS_A', 'RUN_RLS_B', 'RUN_RLS_BLOCKED')")
            )
            connection.execute(text(f"DROP OWNED BY {RUNTIME_ROLE}"))
            connection.execute(text(f"DROP ROLE IF EXISTS {RUNTIME_ROLE}"))
        owner_engine.dispose()
