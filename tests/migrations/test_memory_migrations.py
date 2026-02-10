"""Tests for Memory Butler migration files."""

from __future__ import annotations

import importlib.util
import inspect
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROSTER_DIR = Path(__file__).resolve().parent.parent.parent / "roster"
MIGRATION_DIR = ROSTER_DIR / "memory" / "migrations"
MIGRATION_FILE = MIGRATION_DIR / "001_create_episodes.py"


def _load_migration(filename: str = "001_create_episodes.py", module_name: str = "migration_001"):
    """Load a migration module dynamically."""
    filepath = MIGRATION_DIR / filename
    spec = importlib.util.spec_from_file_location(module_name, filepath)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── 001_create_episodes ──────────────────────────────────────────────────


def test_migration_file_exists():
    """The 001_create_episodes migration file exists on disk."""
    assert MIGRATION_FILE.exists(), f"Migration file not found at {MIGRATION_FILE}"


def test_init_file_exists():
    """The __init__.py file exists in the migrations directory."""
    init_file = MIGRATION_DIR / "__init__.py"
    assert init_file.exists(), f"__init__.py not found at {init_file}"


def test_branch_labels():
    """The migration declares the 'memory' branch label."""
    mod = _load_migration()
    assert hasattr(mod, "branch_labels")
    assert mod.branch_labels == ("memory",)


def test_revision_identifiers():
    """The migration has correct revision identifiers."""
    mod = _load_migration()
    assert mod.revision == "001"
    assert mod.down_revision is None
    assert mod.depends_on is None


def test_upgrade_function_exists():
    """The migration has an upgrade() function."""
    mod = _load_migration()
    assert hasattr(mod, "upgrade")
    assert callable(mod.upgrade)


def test_downgrade_function_exists():
    """The migration has a downgrade() function."""
    mod = _load_migration()
    assert hasattr(mod, "downgrade")
    assert callable(mod.downgrade)


# ── 004_create_memory_links ──────────────────────────────────────────────

MEMORY_LINKS_FILE = MIGRATION_DIR / "004_create_memory_links.py"


def _load_memory_links():
    return _load_migration("004_create_memory_links.py", "migration_004")


def test_004_file_exists():
    """The 004_create_memory_links migration file exists on disk."""
    assert MEMORY_LINKS_FILE.exists(), f"Migration file not found at {MEMORY_LINKS_FILE}"


def test_004_revision_identifiers():
    """Migration 004 has correct revision chain."""
    mod = _load_memory_links()
    assert mod.revision == "004"
    assert mod.down_revision == "003"
    assert mod.depends_on is None


def test_004_upgrade_function_exists():
    """Migration 004 has an upgrade() function."""
    mod = _load_memory_links()
    assert hasattr(mod, "upgrade")
    assert callable(mod.upgrade)


def test_004_downgrade_function_exists():
    """Migration 004 has a downgrade() function."""
    mod = _load_memory_links()
    assert hasattr(mod, "downgrade")
    assert callable(mod.downgrade)


def test_004_upgrade_creates_memory_links_table():
    """The upgrade SQL contains the memory_links table definition."""
    mod = _load_memory_links()
    source = inspect.getsource(mod.upgrade)
    assert "memory_links" in source
    assert "source_type" in source
    assert "source_id" in source
    assert "target_type" in source
    assert "target_id" in source
    assert "relation" in source
    assert "created_at" in source
    assert "PRIMARY KEY" in source


def test_004_upgrade_has_check_constraint():
    """The upgrade SQL contains a CHECK constraint for valid relation values."""
    mod = _load_memory_links()
    source = inspect.getsource(mod.upgrade)
    assert "CHECK" in source
    for relation in ("derived_from", "supports", "contradicts", "supersedes", "related_to"):
        assert relation in source, f"Missing relation value: {relation}"


def test_004_upgrade_has_target_index():
    """The upgrade SQL creates an index on (target_type, target_id)."""
    mod = _load_memory_links()
    source = inspect.getsource(mod.upgrade)
    assert "idx_memory_links_target" in source
    assert "target_type" in source
    assert "target_id" in source


def test_004_downgrade_drops_table():
    """The downgrade SQL drops the memory_links table."""
    mod = _load_memory_links()
    source = inspect.getsource(mod.downgrade)
    assert "DROP TABLE" in source
    assert "memory_links" in source
