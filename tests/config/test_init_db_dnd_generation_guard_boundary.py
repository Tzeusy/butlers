"""Static source coverage for the canonical DND authority boundary.

These checks deliberately do not execute ``init-db.sql`` or start PostgreSQL.
The companion integration suite must exercise the catalog/RLS/role contract in
an explicitly authorized database environment.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).resolve().parents[2]
_INIT_DB = _REPO_ROOT / "scripts" / "init-db.sql"
_MIGRATION = (
    _REPO_ROOT / "alembic" / "versions" / "core" / "core_197_canonical_dnd_generation_guard.py"
)


def test_dnd_boundary_uses_trusted_installer_not_migration_owned_ddl() -> None:
    source = _INIT_DB.read_text(encoding="utf-8")
    migration = _MIGRATION.read_text(encoding="utf-8")

    assert "CREATE OR REPLACE FUNCTION dnd_generation_admin.install_interface()" in source
    assert "CREATE OR REPLACE FUNCTION dnd_generation_admin.finalize_interface()" in source
    assert "DND authority interface must be absent before fixed bootstrap installation" in source
    assert "the pre-DND table must have no user policies at" in source
    assert "entire known core shape rather than adopting a compatible-looking table" in source
    assert "constraint_row.contype = 'u'" in source
    assert "constraint_row.conname = 'user_context_confidence_check'" in source
    assert "index_row.indexprs IS NOT NULL" in source
    assert "idx_user_context_active_signals" in source
    assert source.count("LOCK TABLE public.user_context IN ACCESS EXCLUSIVE MODE") == 2
    assert "CREATE ROLE dnd_generation_owner" in source
    assert (
        "NOLOGIN NOINHERIT NOSUPERUSER NOCREATEROLE NOCREATEDB NOREPLICATION NOBYPASSRLS" in source
    )
    assert "roleid = v_owner OR member = v_owner" in source
    assert "DND generation owner role is untrusted or has memberships" in source
    assert "ALTER TABLE public.user_context OWNER TO dnd_generation_owner" in source
    assert "ALTER TABLE public.user_context ENABLE ROW LEVEL SECURITY" in source
    assert "ALTER TABLE public.user_context FORCE ROW LEVEL SECURITY" in source

    assert "_TRUSTED_FINALIZED_INTERFACE_SQL" in migration
    assert "_TRUSTED_BOOTSTRAP_INSTALLER_SQL" in migration
    assert 'op.execute(f"SELECT {_ADMIN_INSTALLER}()")' in migration
    assert "CREATE TABLE" not in migration
    assert "CREATE FUNCTION" not in migration
    assert "ALTER TABLE" not in migration


def test_dnd_gateway_checks_active_role_before_private_definer() -> None:
    source = _INIT_DB.read_text(encoding="utf-8")

    assert "CREATE FUNCTION public.context_dnd_mutate(" in source
    assert "SECURITY INVOKER" in source
    assert "IF current_user = 'butler_general_rw'" in source
    assert "ELSIF current_user = 'butler_switchboard_rw'" in source
    assert "CREATE FUNCTION dnd_generation_private.mutate(" in source
    assert "CREATE FUNCTION dnd_generation_private.canonical_json(p_document JSONB)" in source
    assert "SECURITY DEFINER" in source
    assert "current_setting('role', true)" in source
    assert "\"normalize\"(p_value, 'NFC')" in source
    assert "DND metadata has duplicate NFC-normalized keys" in source
    assert "RETURN trim_scale((p_document #>> '{}')::numeric)::text" in source
    assert "DND writer does not match the active runtime role" in source
    assert "polname NOT IN (" in source
    assert "REVOKE ALL PRIVILEGES ON FUNCTION public.context_dnd_mutate" in source
    assert "REVOKE ALL PRIVILEGES ON FUNCTION dnd_generation_private.mutate" in source


def test_dnd_receipt_schema_is_content_minimizing_and_role_catalog_gated() -> None:
    source = _INIT_DB.read_text(encoding="utf-8")
    migration = _MIGRATION.read_text(encoding="utf-8")

    audit_start = source.index("CREATE TABLE public.dnd_generation_mutations")
    audit_end = source.index(
        "CREATE UNIQUE INDEX dnd_generation_mutations_generation_key", audit_start
    )
    audit = source[audit_start:audit_end]
    assert "mutation_id UUID PRIMARY KEY" in audit
    assert "semantic_fingerprint_version" in audit
    assert "semantic_fingerprint TEXT NOT NULL" in audit
    assert "value TEXT" not in audit
    assert "metadata JSONB" not in audit

    assert "relrowsecurity" in migration
    assert "relforcerowsecurity" in migration
    assert "NOT dnd_owner.rolcanlogin" in migration
    assert "NOT dnd_owner.rolbypassrls" in migration
    assert "migration_role.rolname = current_user" in migration
    assert "acl.grantee = migration_role.oid" in migration
    assert "effective inherited gateway" in migration
    assert "general_runtime.rolname = 'butler_general_rw'" in migration
    assert "switchboard_runtime.rolname = 'butler_switchboard_rw'" in migration
    assert "DND authority ACL finalization is incomplete" in source
    assert "REVOKE DELETE ON TABLE public.user_context" in source
