"""Tests for memory migration chain registration in the daemon migration runner."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

# ---------------------------------------------------------------------------
# Load the migrations module from src/butlers/migrations.py
# ---------------------------------------------------------------------------
_MIGRATIONS_PATH = (
    Path(__file__).resolve().parent.parent.parent / "src" / "butlers" / "migrations.py"
)


def _load_migrations_module():
    spec = importlib.util.spec_from_file_location("butlers.migrations", _MIGRATIONS_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_mod = _load_migrations_module()
get_all_chains = _mod.get_all_chains
_SHARED_CHAINS = _mod._SHARED_CHAINS
_resolve_chain_dir = _mod._resolve_chain_dir
has_butler_chain = _mod.has_butler_chain

# ---------------------------------------------------------------------------
# Migration chain discovery for module-local memory migrations
# ---------------------------------------------------------------------------
MODULES_DIR = Path(__file__).resolve().parent.parent.parent / "src" / "butlers" / "modules"
MEMORY_MIGRATIONS_DIR = MODULES_DIR / "memory" / "migrations"


class TestMemoryChainRegistration:
    """Verify that the memory chain is registered and discoverable."""

    def test_chain_registration_and_ordering(self) -> None:
        """memory not in shared; in get_all_chains; core in shared; shared come first."""
        assert "memory" not in _SHARED_CHAINS
        assert "memory" in get_all_chains()
        assert "core" in _SHARED_CHAINS

        chains = get_all_chains()
        shared_indices = [i for i, c in enumerate(chains) if c in _SHARED_CHAINS]
        non_shared_indices = [i for i, c in enumerate(chains) if c not in _SHARED_CHAINS]
        if shared_indices and non_shared_indices:
            assert max(shared_indices) < min(non_shared_indices), (
                "Shared chains should appear before non-shared chains"
            )

    def test_memory_chain_dir(self) -> None:
        """_resolve_chain_dir('memory') returns a valid directory with correct migration files."""
        chain_dir = _resolve_chain_dir("memory")
        assert chain_dir is not None
        assert chain_dir.is_dir()
        migration_files = sorted(
            f.name for f in chain_dir.iterdir() if f.suffix == ".py" and f.name != "__init__.py"
        )
        assert migration_files == [
            "001_memory_schema.py",
            "002_seed_predicates.py",
        ], f"Unexpected migration files: {migration_files}"

    def test_has_butler_chain(self) -> None:
        """has_butler_chain returns False for module-owned and nonexistent butlers."""
        assert has_butler_chain("memory") is False
        assert has_butler_chain("nonexistent_butler_xyz") is False


class TestBaselineRevisionChain:
    """Validate the single baseline revision chain for memory."""

    EXPECTED_CHAIN = [
        ("001_memory_schema.py", "mem_001", None),
        ("002_seed_predicates.py", "mem_002", "mem_001"),
    ]

    @staticmethod
    def _load_migration(filename: str):
        """Load a migration module by filename from the memory migrations dir."""
        filepath = MEMORY_MIGRATIONS_DIR / filename
        spec = importlib.util.spec_from_file_location(filename.removesuffix(".py"), filepath)
        assert spec is not None and spec.loader is not None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_migration_files_and_metadata(self) -> None:
        """Files exist; revision/down_revision correct; branch_label on root; no depends_on."""
        for filename, expected_rev, expected_down_rev in self.EXPECTED_CHAIN:
            filepath = MEMORY_MIGRATIONS_DIR / filename
            assert filepath.exists(), f"Missing migration: {filepath}"
            mod = self._load_migration(filename)
            assert mod.revision == expected_rev
            assert mod.down_revision == expected_down_rev
            assert mod.depends_on is None
            assert callable(getattr(mod, "upgrade", None))
            assert callable(getattr(mod, "downgrade", None))

        # Branch label on root
        root_filename, _, _ = self.EXPECTED_CHAIN[0]
        root = self._load_migration(root_filename)
        assert root.branch_labels == ("memory",)

    def test_revision_chain_structure(self) -> None:
        """No duplicate revisions; chain is linear mem_001 -> mem_002."""
        revisions = []
        chain_map = {}
        for filename, _, _ in self.EXPECTED_CHAIN:
            mod = self._load_migration(filename)
            revisions.append(mod.revision)
            chain_map[mod.revision] = mod.down_revision

        assert len(revisions) == len(set(revisions)), f"Duplicate revisions: {revisions}"

        current = "mem_002"
        path = [current]
        while chain_map.get(current) is not None:
            current = chain_map[current]
            path.append(current)
        path.reverse()
        assert path == ["mem_001", "mem_002"]
