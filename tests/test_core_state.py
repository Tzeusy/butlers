"""Tests for butlers.core.state — JSONB key-value state store."""

from __future__ import annotations

import shutil
import uuid

import pytest

# Skip all tests in this module if Docker is not available
docker_available = shutil.which("docker") is not None
pytestmark = pytest.mark.skipif(not docker_available, reason="Docker not available")


def _unique_db_name() -> str:
    return f"test_{uuid.uuid4().hex[:12]}"


@pytest.fixture(scope="module")
def postgres_container():
    """Start a PostgreSQL container for the test module."""
    from testcontainers.postgres import PostgresContainer

    with PostgresContainer("postgres:16") as pg:
        yield pg


@pytest.fixture
async def pool(postgres_container):
    """Provision a fresh database with the state table and return a pool."""
    from butlers.db import Database

    db = Database(
        db_name=_unique_db_name(),
        host=postgres_container.get_container_host_ip(),
        port=int(postgres_container.get_exposed_port(5432)),
        user=postgres_container.username,
        password=postgres_container.password,
        min_pool_size=1,
        max_pool_size=3,
    )
    await db.provision()
    p = await db.connect()

    # Create the state table (mirrors Alembic core migration)
    await p.execute("""
        CREATE TABLE IF NOT EXISTS state (
            key TEXT PRIMARY KEY,
            value JSONB NOT NULL DEFAULT '{}',
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

    yield p
    await db.close()


# ------------------------------------------------------------------
# state_get
# ------------------------------------------------------------------


async def test_get_existing_key(pool):
    """state_get returns the stored JSONB value for an existing key."""
    from butlers.core.state import state_get, state_set

    await state_set(pool, "greeting", "hello")
    result = await state_get(pool, "greeting")
    assert result == "hello"


async def test_get_missing_key(pool):
    """state_get returns None for a key that does not exist."""
    from butlers.core.state import state_get

    result = await state_get(pool, "nonexistent_key")
    assert result is None


# ------------------------------------------------------------------
# state_set
# ------------------------------------------------------------------


async def test_set_inserts_new_key(pool):
    """state_set inserts a brand-new key-value pair."""
    from butlers.core.state import state_get, state_set

    await state_set(pool, "new_key", {"a": 1})
    result = await state_get(pool, "new_key")
    assert result == {"a": 1}


async def test_set_updates_existing_key(pool):
    """state_set upserts — updates the value and updated_at on conflict."""
    from butlers.core.state import state_get, state_set

    await state_set(pool, "counter", 1)
    assert await state_get(pool, "counter") == 1

    await state_set(pool, "counter", 2)
    assert await state_get(pool, "counter") == 2

    # Verify updated_at was refreshed
    row = await pool.fetchrow("SELECT updated_at FROM state WHERE key = $1", "counter")
    assert row is not None


# ------------------------------------------------------------------
# state_delete
# ------------------------------------------------------------------


async def test_delete_existing_key(pool):
    """state_delete removes the row for the given key."""
    from butlers.core.state import state_delete, state_get, state_set

    await state_set(pool, "doomed", "bye")
    assert await state_get(pool, "doomed") == "bye"

    await state_delete(pool, "doomed")
    assert await state_get(pool, "doomed") is None


async def test_delete_missing_key_is_noop(pool):
    """state_delete does not raise when the key is absent."""
    from butlers.core.state import state_delete

    # Should complete without error
    await state_delete(pool, "never_existed")


# ------------------------------------------------------------------
# state_list
# ------------------------------------------------------------------


async def test_list_all_entries(pool):
    """state_list with keys_only=True returns list of key strings."""
    from butlers.core.state import state_list, state_set

    # Use a unique prefix to avoid collisions from other tests
    await state_set(pool, "list_all:a", 1)
    await state_set(pool, "list_all:b", 2)
    await state_set(pool, "list_all:c", 3)

    # Default behavior: keys_only=True
    keys = await state_list(pool, prefix="list_all:")
    assert isinstance(keys, list)
    assert all(isinstance(k, str) for k in keys)
    assert "list_all:a" in keys
    assert "list_all:b" in keys
    assert "list_all:c" in keys


async def test_list_with_prefix_filter(pool):
    """state_list with prefix only returns matching keys."""
    from butlers.core.state import state_list, state_set

    await state_set(pool, "proj:alpha", "a")
    await state_set(pool, "proj:beta", "b")
    await state_set(pool, "other:gamma", "g")

    # Default behavior: keys_only=True
    keys = await state_list(pool, prefix="proj:")
    assert "proj:alpha" in keys
    assert "proj:beta" in keys
    assert "other:gamma" not in keys


async def test_list_keys_only_false(pool):
    """state_list with keys_only=False returns dicts with key and value."""
    from butlers.core.state import state_list, state_set

    await state_set(pool, "compat:x", {"val": 10})
    await state_set(pool, "compat:y", {"val": 20})

    entries = await state_list(pool, prefix="compat:", keys_only=False)
    assert isinstance(entries, list)
    assert all(isinstance(e, dict) for e in entries)
    assert all("key" in e and "value" in e for e in entries)

    keys = [e["key"] for e in entries]
    assert "compat:x" in keys
    assert "compat:y" in keys

    # Verify values are included
    for e in entries:
        if e["key"] == "compat:x":
            assert e["value"] == {"val": 10}
        elif e["key"] == "compat:y":
            assert e["value"] == {"val": 20}


# ------------------------------------------------------------------
# JSONB value types
# ------------------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    [
        "a string",
        42,
        3.14,
        {"nested": {"key": "value"}},
        [1, "two", 3],
        True,
        False,
        None,
    ],
    ids=["string", "integer", "float", "object", "array", "true", "false", "null"],
)
async def test_jsonb_value_types(pool, value):
    """state_set/state_get round-trips all JSON-compatible value types."""
    from butlers.core.state import state_get, state_set

    key = f"type_test:{type(value).__name__}:{value}"
    await state_set(pool, key, value)
    result = await state_get(pool, key)
    assert result == value
