"""Alembic environment for multi-chain butler migrations.

Supports:
- Programmatic invocation from the daemon (not just CLI)
- Targeting a specific butler's database via connection URL
- Multiple version chains (core + module + butler-specific)
- Raw SQL via op.execute() (no SQLAlchemy models)
"""

from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine, pool

from alembic import context

# The directory containing shared version chain subdirectories (core only)
VERSIONS_DIR = Path(__file__).parent / "versions"

# The directory containing butler config dirs (each may have a migrations/ folder)
ROSTER_DIR = Path(__file__).parent.parent / "roster"

# The directory containing module packages (each may have a migrations/ folder)
MODULES_DIR = Path(__file__).parent.parent / "src" / "butlers" / "modules"

# Shared chains that live in alembic/versions/ (core only)
_SHARED_CHAINS = ["core"]


def _discover_module_chains() -> list[str]:
    """Discover module-local migration chains from module directories.

    Scans ``src/butlers/modules/*/migrations/`` for directories that contain
    at least one ``.py`` migration file (excluding ``__init__.py``).
    """
    if not MODULES_DIR.is_dir():
        return []
    chains = []
    for entry in sorted(MODULES_DIR.iterdir()):
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


def _discover_butler_chains() -> list[str]:
    """Discover butler-specific migration chains from butler config dirs.

    Scans ``roster/*/migrations/`` for directories that contain at least one
    ``.py`` migration file (excluding ``__init__.py``).
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


def get_url() -> str:
    """Resolve the database URL from context or environment."""
    url = context.config.get_main_option("sqlalchemy.url")
    if url:
        return url
    return os.environ.get(
        "BUTLERS_DATABASE_URL",
        "postgresql://postgres:postgres@localhost:5432/butlers",
    )


def get_version_locations() -> list[str]:
    """Build the version_locations list for all chains.

    Includes shared chains from alembic/versions/, module chains from
    src/butlers/modules/*/migrations/, and butler-specific chains from
    roster/<name>/migrations/.
    """
    locations = []

    # Shared chains (core) in alembic/versions/
    for chain in _SHARED_CHAINS:
        chain_dir = VERSIONS_DIR / chain
        if chain_dir.is_dir():
            locations.append(str(chain_dir))

    # Module-local chains in src/butlers/modules/<name>/migrations/
    for module_name in _discover_module_chains():
        mig_dir = MODULES_DIR / module_name / "migrations"
        locations.append(str(mig_dir))

    # Butler-specific chains in roster/<name>/migrations/
    for butler_name in _discover_butler_chains():
        mig_dir = ROSTER_DIR / butler_name / "migrations"
        locations.append(str(mig_dir))

    return locations


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emit SQL without a live connection)."""
    url = get_url()
    context.configure(
        url=url,
        target_metadata=None,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        version_locations=get_version_locations(),
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode (with a live database connection)."""
    url = get_url()
    connectable = create_engine(url, poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=None,
            version_locations=get_version_locations(),
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
