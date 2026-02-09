"""Alembic environment for multi-chain butler migrations.

Supports:
- Programmatic invocation from the daemon (not just CLI)
- Targeting a specific butler's database via connection URL
- Multiple version chains (core + butler-specific)
- Raw SQL via op.execute() (no SQLAlchemy models)
"""

from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine, pool

from alembic import context

# The directory containing version chain subdirectories
VERSIONS_DIR = Path(__file__).parent / "versions"

# All recognized version chains
VERSION_CHAINS = ["core", "switchboard", "relationship", "health", "general"]


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

    Returns a list of paths to chain directories under versions/.
    """
    locations = []
    for chain in VERSION_CHAINS:
        chain_dir = VERSIONS_DIR / chain
        if chain_dir.is_dir():
            locations.append(str(chain_dir))
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
