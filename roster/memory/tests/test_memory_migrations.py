"""Unit tests for Memory Butler migration files."""

from __future__ import annotations

import importlib
import importlib.util
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"


def _load_migration(filename: str):
    """Load a migration module by filename."""
    filepath = MIGRATIONS_DIR / filename
    spec = importlib.util.spec_from_file_location(filename.removesuffix(".py"), filepath)
    assert spec is not None, f"Could not load spec for {filepath}"
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestFactsMigration:
    """Tests for 002_create_facts migration."""

    def test_migration_file_exists(self) -> None:
        """The migration file should exist on disk."""
        filepath = MIGRATIONS_DIR / "002_create_facts.py"
        assert filepath.exists(), f"Expected migration at {filepath}"

    def test_revision_identifiers(self) -> None:
        """The migration should have correct Alembic revision metadata."""
        mod = _load_migration("002_create_facts.py")
        assert mod.revision == "002"
        assert mod.down_revision == "001"

    def test_branch_labels(self) -> None:
        """002 is not the branch root, so branch_labels should be None."""
        mod = _load_migration("002_create_facts.py")
        assert mod.branch_labels is None

    def test_depends_on(self) -> None:
        """depends_on should be None (chaining is via down_revision)."""
        mod = _load_migration("002_create_facts.py")
        assert mod.depends_on is None

    def test_has_upgrade_function(self) -> None:
        """The migration must define an upgrade() callable."""
        mod = _load_migration("002_create_facts.py")
        assert callable(getattr(mod, "upgrade", None))

    def test_has_downgrade_function(self) -> None:
        """The migration must define a downgrade() callable."""
        mod = _load_migration("002_create_facts.py")
        assert callable(getattr(mod, "downgrade", None))

    def test_init_file_exists(self) -> None:
        """The migrations package should have an __init__.py."""
        init_path = MIGRATIONS_DIR / "__init__.py"
        assert init_path.exists(), f"Expected __init__.py at {init_path}"


class TestRulesMigration:
    """Tests for 003_create_rules migration."""

    def test_migration_file_exists(self) -> None:
        """The migration file should exist on disk."""
        filepath = MIGRATIONS_DIR / "003_create_rules.py"
        assert filepath.exists(), f"Expected migration at {filepath}"

    def test_revision_identifiers(self) -> None:
        """The migration should have correct Alembic revision metadata."""
        mod = _load_migration("003_create_rules.py")
        assert mod.revision == "003"
        assert mod.down_revision == "002"

    def test_branch_labels(self) -> None:
        """003 is not the branch root, so branch_labels should be None."""
        mod = _load_migration("003_create_rules.py")
        assert mod.branch_labels is None

    def test_depends_on(self) -> None:
        """depends_on should be None (chaining is via down_revision)."""
        mod = _load_migration("003_create_rules.py")
        assert mod.depends_on is None

    def test_has_upgrade_function(self) -> None:
        """The migration must define an upgrade() callable."""
        mod = _load_migration("003_create_rules.py")
        assert callable(getattr(mod, "upgrade", None))

    def test_has_downgrade_function(self) -> None:
        """The migration must define a downgrade() callable."""
        mod = _load_migration("003_create_rules.py")
        assert callable(getattr(mod, "downgrade", None))
