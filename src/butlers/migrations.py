"""Programmatic Alembic migration runner for butlers.

Allows the daemon to run migrations at startup without shelling out to the
Alembic CLI. Supports targeting a specific version chain (core or butler-specific).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from alembic.config import Config

from alembic import command

logger = logging.getLogger(__name__)

# Root of the alembic directory (sibling to src/)
ALEMBIC_DIR = Path(__file__).resolve().parent.parent.parent / "alembic"

# Root of the butler config directories (sibling to src/)
ROSTER_DIR = Path(__file__).resolve().parent.parent.parent / "roster"

# Shared chains that live in alembic/versions/ (core infra + shared modules)
_SHARED_CHAINS = ["core", "mailbox", "approvals"]


def _discover_butler_chains() -> list[str]:
    """Discover butler-specific migration chains from butler config dirs.

    Scans ``roster/*/migrations/`` for directories that contain at least one
    ``.py`` migration file (excluding ``__init__.py``).

    Returns:
        Sorted list of butler names that have a migrations/ folder with files.
    """
    if not ROSTER_DIR.is_dir():
        return []
    chains = []
    for entry in sorted(ROSTER_DIR.iterdir()):
        if not entry.is_dir():
            continue
        mig_dir = entry / "migrations"
        if not mig_dir.is_dir():
            continue
        migration_files = [
            f for f in mig_dir.iterdir() if f.suffix == ".py" and f.name != "__init__.py"
        ]
        if migration_files:
            chains.append(entry.name)
    return chains


def _resolve_chain_dir(chain: str) -> Path | None:
    """Resolve the filesystem path for a given chain name.

    Shared chains (core, mailbox) live in ``alembic/versions/<chain>/``.
    Butler-specific chains live in ``roster/<chain>/migrations/``.

    Returns:
        The chain directory Path if it exists, otherwise None.
    """
    if chain in _SHARED_CHAINS:
        chain_dir = ALEMBIC_DIR / "versions" / chain
    else:
        chain_dir = ROSTER_DIR / chain / "migrations"
    return chain_dir if chain_dir.is_dir() else None


def get_all_chains() -> list[str]:
    """Return all recognized version chains (shared + butler-specific).

    Shared chains are listed first, followed by dynamically discovered
    butler-specific chains.
    """
    shared = [c for c in _SHARED_CHAINS if (ALEMBIC_DIR / "versions" / c).is_dir()]
    return shared + _discover_butler_chains()


def _build_alembic_config(db_url: str, chains: list[str] | None = None) -> Config:
    """Build an Alembic Config pointing at the correct version directories.

    Args:
        db_url: SQLAlchemy-compatible database URL.
        chains: List of version chain names to include. Defaults to all chains.

    Returns:
        A configured alembic.config.Config instance.
    """
    ini_path = ALEMBIC_DIR / "alembic.ini"
    config = Config(str(ini_path))
    config.set_main_option("script_location", str(ALEMBIC_DIR))
    config.set_main_option("sqlalchemy.url", db_url)

    # Build version_locations from requested chains
    chains = chains or get_all_chains()
    locations = []
    for chain in chains:
        chain_dir = _resolve_chain_dir(chain)
        if chain_dir is not None:
            locations.append(str(chain_dir))
    config.set_main_option("version_locations", os.pathsep.join(locations))

    return config


def has_butler_chain(butler_name: str) -> bool:
    """Check whether a butler-name-specific Alembic version chain exists.

    A chain is considered to exist when the directory
    ``roster/<butler_name>/migrations/`` is present and contains at least one
    ``.py`` migration file (excluding ``__init__.py``).

    Args:
        butler_name: The butler identity name (e.g. ``"relationship"``).

    Returns:
        ``True`` if a non-empty migration chain directory exists for the butler.
    """
    chain_dir = ROSTER_DIR / butler_name / "migrations"
    if not chain_dir.is_dir():
        return False
    migration_files = [
        f for f in chain_dir.iterdir() if f.suffix == ".py" and f.name != "__init__.py"
    ]
    return len(migration_files) > 0


async def run_migrations(db_url: str, chain: str = "core") -> None:
    """Run Alembic migrations programmatically for a specific chain.

    This is the primary entry point for running migrations from the butler
    daemon. It configures Alembic to use the correct version directory and
    upgrades to the latest revision.

    Args:
        db_url: SQLAlchemy-compatible database URL
            (e.g. ``postgresql://user:pass@host:port/dbname``).
        chain: Version chain to migrate. Must be one of the recognized chains
            (core, mailbox, or any butler name with a migrations/ directory).
            Pass ``"all"`` to migrate all chains.
    """
    if chain == "all":
        chains = get_all_chains()
    else:
        chains = [chain]

    config = _build_alembic_config(db_url, chains)

    if chain == "all":
        # Upgrade all chains to head
        logger.info("Running all migration chains to head")
        command.upgrade(config, "heads")
    else:
        # Upgrade a specific chain branch to its head
        logger.info("Running %s migration chain to head", chain)
        command.upgrade(config, f"{chain}@head")
