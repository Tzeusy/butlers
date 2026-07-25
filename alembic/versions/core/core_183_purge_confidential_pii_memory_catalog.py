"""Purge already-written confidential/pii rows from public.memory_catalog.

Revision ID: core_183
Revises: core_182
Create Date: 2026-07-25 00:00:00.000000

bu-6gsmh — owner ruling: EXCLUDE (defense-in-depth). Confidential/pii facts
and rules were, until now, written to ``public.memory_catalog`` (a
cross-butler-readable discovery index) and only filtered out at read time via
the ``max_sensitivity`` authorization ceiling in
``butlers/modules/memory/search.py``. The write-behind path
(``butlers/modules/memory/storage.py::_upsert_catalog`` and its two backfill
counterparts) now refuses to write those rows at all going forward -- see
``CATALOG_WRITE_EXCLUDED_SENSITIVITIES`` in that module.

This migration is the one-off backfill purge: it DELETEs the rows that were
already written under the old (write-everything, filter-on-read) behavior.
``public.memory_catalog`` is a discovery index, not a canonical store (the
canonical fact/rule rows in each butler's own schema are entirely untouched
by this migration) -- deleting a stale catalog row only removes it from
cross-butler discovery, exactly like the existing GC/disownment cascades in
``_mark_catalog_stale`` (this migration runs with elevated migration
privileges, unlike butler runtime roles, which intentionally hold no DELETE
grant on this table per core_009).

Excluded sensitivity values mirror the read-time ceiling's default: every
level strictly above ``'normal'`` in ``CATALOG_SENSITIVITY_LEVELS =
('normal', 'pii', 'confidential')`` -- i.e. exactly ``'pii'`` and
``'confidential'``. Idempotent (a second run deletes nothing) and guarded
with ``to_regclass`` so it safely no-ops on any schema context where
``public.memory_catalog`` does not exist.
"""

from __future__ import annotations

from alembic import op

revision = "core_183"
down_revision = "core_182"
branch_labels = None
depends_on = None


PURGE_CONFIDENTIAL_PII_MEMORY_CATALOG_SQL = """
DO $$
BEGIN
    IF to_regclass('public.memory_catalog') IS NULL THEN
        RETURN;
    END IF;

    DELETE FROM public.memory_catalog
    WHERE COALESCE(sensitivity, 'normal') IN ('pii', 'confidential');
END
$$;
"""


def upgrade() -> None:
    """Delete already-cataloged confidential/pii rows; canonical facts/rules untouched."""
    op.execute(PURGE_CONFIDENTIAL_PII_MEMORY_CATALOG_SQL)


def downgrade() -> None:
    """Do not resurrect purged confidential/pii catalog rows."""
