"""Tests for Memory Butler migration files."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROSTER_DIR = Path(__file__).resolve().parent.parent.parent / "roster"
MIGRATION_DIR = ROSTER_DIR / "memory" / "migrations"
MIGRATION_FILE = MIGRATION_DIR / "001_create_episodes.py"


def _load_migration():
    """Load the migration module dynamically."""
    spec = importlib.util.spec_from_file_location("migration_001", MIGRATION_FILE)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


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
