"""Unit tests for Memory Butler migration files."""

from __future__ import annotations

import importlib
import importlib.util
import inspect
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


class TestVectorIndexesMigration:
    """Tests for 005_add_vector_indexes migration."""

    def test_migration_file_exists(self) -> None:
        """The migration file should exist on disk."""
        filepath = MIGRATIONS_DIR / "005_add_vector_indexes.py"
        assert filepath.exists(), f"Expected migration at {filepath}"

    def test_revision_identifiers(self) -> None:
        """The migration should have correct Alembic revision metadata."""
        mod = _load_migration("005_add_vector_indexes.py")
        assert mod.revision == "005"
        assert mod.down_revision == "004"

    def test_branch_labels(self) -> None:
        """005 is not the branch root, so branch_labels should be None."""
        mod = _load_migration("005_add_vector_indexes.py")
        assert mod.branch_labels is None

    def test_depends_on(self) -> None:
        """depends_on should be None (chaining is via down_revision)."""
        mod = _load_migration("005_add_vector_indexes.py")
        assert mod.depends_on is None

    def test_has_upgrade_function(self) -> None:
        """The migration must define an upgrade() callable."""
        mod = _load_migration("005_add_vector_indexes.py")
        assert callable(getattr(mod, "upgrade", None))

    def test_has_downgrade_function(self) -> None:
        """The migration must define a downgrade() callable."""
        mod = _load_migration("005_add_vector_indexes.py")
        assert callable(getattr(mod, "downgrade", None))

    def test_upgrade_creates_vector_extension(self) -> None:
        """Upgrade should enable the vector extension."""
        mod = _load_migration("005_add_vector_indexes.py")
        source = inspect.getsource(mod.upgrade)
        assert "CREATE EXTENSION IF NOT EXISTS vector" in source

    def test_upgrade_creates_uuid_ossp_extension(self) -> None:
        """Upgrade should enable the uuid-ossp extension."""
        mod = _load_migration("005_add_vector_indexes.py")
        source = inspect.getsource(mod.upgrade)
        assert 'uuid-ossp' in source

    def test_upgrade_creates_episodes_ivfflat_index(self) -> None:
        """Upgrade should create IVFFlat index on episodes.embedding."""
        mod = _load_migration("005_add_vector_indexes.py")
        source = inspect.getsource(mod.upgrade)
        assert "idx_episodes_embedding" in source
        assert "ivfflat" in source
        assert "vector_cosine_ops" in source

    def test_upgrade_creates_facts_ivfflat_index(self) -> None:
        """Upgrade should create IVFFlat index on facts.embedding."""
        mod = _load_migration("005_add_vector_indexes.py")
        source = inspect.getsource(mod.upgrade)
        assert "idx_facts_embedding" in source

    def test_upgrade_creates_rules_ivfflat_index(self) -> None:
        """Upgrade should create IVFFlat index on rules.embedding."""
        mod = _load_migration("005_add_vector_indexes.py")
        source = inspect.getsource(mod.upgrade)
        assert "idx_rules_embedding" in source

    def test_upgrade_uses_20_lists(self) -> None:
        """All IVFFlat indexes should use 20 lists."""
        mod = _load_migration("005_add_vector_indexes.py")
        source = inspect.getsource(mod.upgrade)
        assert source.count("lists = 20") == 3

    def test_downgrade_drops_indexes(self) -> None:
        """Downgrade should drop all three IVFFlat indexes."""
        mod = _load_migration("005_add_vector_indexes.py")
        source = inspect.getsource(mod.downgrade)
        assert "DROP INDEX IF EXISTS idx_episodes_embedding" in source
        assert "DROP INDEX IF EXISTS idx_facts_embedding" in source
        assert "DROP INDEX IF EXISTS idx_rules_embedding" in source
