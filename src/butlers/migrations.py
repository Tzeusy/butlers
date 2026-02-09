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

# All recognized version chains
VERSION_CHAINS = ["core", "switchboard", "relationship", "health", "general"]


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
    chains = chains or VERSION_CHAINS
    locations = []
    for chain in chains:
        chain_dir = ALEMBIC_DIR / "versions" / chain
        if chain_dir.is_dir():
            locations.append(str(chain_dir))
    config.set_main_option("version_locations", os.pathsep.join(locations))

    return config


async def run_migrations(db_url: str, chain: str = "core") -> None:
    """Run Alembic migrations programmatically for a specific chain.

    This is the primary entry point for running migrations from the butler
    daemon. It configures Alembic to use the correct version directory and
    upgrades to the latest revision.

    Args:
        db_url: SQLAlchemy-compatible database URL
            (e.g. ``postgresql://user:pass@host:port/dbname``).
        chain: Version chain to migrate. Must be one of the recognized chains
            (core, switchboard, relationship, health, general).
            Pass ``"all"`` to migrate all chains.
    """
    if chain == "all":
        chains = VERSION_CHAINS
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
