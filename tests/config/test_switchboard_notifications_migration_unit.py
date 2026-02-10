"""Unit tests for Switchboard notifications migration structure."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


def test_notifications_migration_file_exists():
    """Verify the 003_add_notifications_table.py migration file exists."""
    migration_file = (
        Path(__file__).parent.parent.parent
        / "butlers"
        / "switchboard"
        / "migrations"
        / "003_add_notifications_table.py"
    )
    assert migration_file.exists(), "Migration file should exist"


def test_notifications_migration_has_correct_metadata():
    """Verify migration metadata (revision, down_revision, etc.)."""
    migration_file = (
        Path(__file__).parent.parent.parent
        / "butlers"
        / "switchboard"
        / "migrations"
        / "003_add_notifications_table.py"
    )

    # Load the module
    spec = importlib.util.spec_from_file_location("migration_003", migration_file)
    assert spec is not None, "Should be able to load migration spec"
    assert spec.loader is not None, "Should have a loader"

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    # Check metadata
    assert hasattr(module, "revision"), "Should have revision attribute"
    assert module.revision == "003", "Revision should be 003"

    assert hasattr(module, "down_revision"), "Should have down_revision attribute"
    assert module.down_revision == "002", "Should revise from 002"

    assert hasattr(module, "branch_labels"), "Should have branch_labels attribute"
    assert module.branch_labels is None, "Branch labels should be None (not head of chain)"

    assert hasattr(module, "depends_on"), "Should have depends_on attribute"
    assert module.depends_on is None, "Should not have dependencies"


def test_notifications_migration_has_upgrade_function():
    """Verify upgrade function exists and is callable."""
    migration_file = (
        Path(__file__).parent.parent.parent
        / "butlers"
        / "switchboard"
        / "migrations"
        / "003_add_notifications_table.py"
    )

    spec = importlib.util.spec_from_file_location("migration_003", migration_file)
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert hasattr(module, "upgrade"), "Should have upgrade function"
    assert callable(module.upgrade), "upgrade should be callable"


def test_notifications_migration_has_downgrade_function():
    """Verify downgrade function exists and is callable."""
    migration_file = (
        Path(__file__).parent.parent.parent
        / "butlers"
        / "switchboard"
        / "migrations"
        / "003_add_notifications_table.py"
    )

    spec = importlib.util.spec_from_file_location("migration_003", migration_file)
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert hasattr(module, "downgrade"), "Should have downgrade function"
    assert callable(module.downgrade), "downgrade should be callable"


def test_switchboard_chain_includes_notifications_migration():
    """Verify the switchboard migrations directory contains the new file."""
    from butlers.migrations import _resolve_chain_dir

    chain_dir = _resolve_chain_dir("switchboard")
    assert chain_dir is not None, "Switchboard chain should exist"

    migration_files = list(chain_dir.glob("*.py"))
    migration_names = [f.name for f in migration_files if f.name != "__init__.py"]

    assert "003_add_notifications_table.py" in migration_names, (
        "Notifications migration should be in switchboard chain"
    )
