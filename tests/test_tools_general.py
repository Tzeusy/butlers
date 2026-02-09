"""Tests for butlers.tools.general — entity and collection management."""

from __future__ import annotations

import shutil
import uuid

import asyncpg
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
    """Provision a fresh database with general tables and return a pool."""
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

    # Create the general tables (mirrors Alembic general migration)
    await p.execute("""
        CREATE TABLE IF NOT EXISTS collections (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name TEXT NOT NULL UNIQUE,
            description TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    await p.execute("""
        CREATE TABLE IF NOT EXISTS entities (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            collection_id UUID NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
            data JSONB NOT NULL DEFAULT '{}',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    await p.execute("""
        CREATE INDEX IF NOT EXISTS idx_entities_data_gin ON entities USING GIN (data)
    """)
    await p.execute("""
        CREATE INDEX IF NOT EXISTS idx_entities_collection_id ON entities (collection_id)
    """)

    yield p
    await db.close()


# ------------------------------------------------------------------
# collection_create
# ------------------------------------------------------------------


async def test_collection_create(pool):
    """collection_create inserts a new collection and returns its UUID."""
    from butlers.tools.general import collection_create

    cid = await collection_create(pool, "books", description="My book collection")
    assert isinstance(cid, uuid.UUID)

    row = await pool.fetchrow("SELECT * FROM collections WHERE id = $1", cid)
    assert row is not None
    assert row["name"] == "books"
    assert row["description"] == "My book collection"


async def test_collection_create_no_description(pool):
    """collection_create works without a description."""
    from butlers.tools.general import collection_create

    cid = await collection_create(pool, "movies")
    assert isinstance(cid, uuid.UUID)

    row = await pool.fetchrow("SELECT * FROM collections WHERE id = $1", cid)
    assert row["description"] is None


async def test_collection_create_duplicate_name(pool):
    """collection_create raises on duplicate collection name."""
    from butlers.tools.general import collection_create

    await collection_create(pool, "unique_coll")
    with pytest.raises(asyncpg.UniqueViolationError):
        await collection_create(pool, "unique_coll")


# ------------------------------------------------------------------
# collection_list
# ------------------------------------------------------------------


async def test_collection_list(pool):
    """collection_list returns all collections ordered by name."""
    from butlers.tools.general import collection_create, collection_list

    await collection_create(pool, "zeta_list")
    await collection_create(pool, "alpha_list")

    colls = await collection_list(pool)
    names = [c["name"] for c in colls]
    assert "alpha_list" in names
    assert "zeta_list" in names
    # Verify ordering
    alpha_idx = names.index("alpha_list")
    zeta_idx = names.index("zeta_list")
    assert alpha_idx < zeta_idx


# ------------------------------------------------------------------
# collection_delete
# ------------------------------------------------------------------


async def test_collection_delete(pool):
    """collection_delete removes the collection."""
    from butlers.tools.general import collection_create, collection_delete, collection_list

    cid = await collection_create(pool, "doomed_coll")
    await collection_delete(pool, cid)

    colls = await collection_list(pool)
    names = [c["name"] for c in colls]
    assert "doomed_coll" not in names


async def test_collection_delete_not_found(pool):
    """collection_delete raises ValueError for non-existent collection."""
    from butlers.tools.general import collection_delete

    with pytest.raises(ValueError, match="not found"):
        await collection_delete(pool, uuid.uuid4())


async def test_collection_delete_cascades_entities(pool):
    """Deleting a collection cascades to its entities."""
    from butlers.tools.general import (
        collection_create,
        collection_delete,
        entity_create,
        entity_get,
    )

    cid = await collection_create(pool, "cascade_test")
    eid = await entity_create(pool, "cascade_test", {"key": "value"})

    await collection_delete(pool, cid)

    # Entity should be gone too
    result = await entity_get(pool, eid)
    assert result is None


# ------------------------------------------------------------------
# entity_create
# ------------------------------------------------------------------


async def test_entity_create(pool):
    """entity_create stores an entity with JSON data."""
    from butlers.tools.general import collection_create, entity_create, entity_get

    await collection_create(pool, "people")
    eid = await entity_create(pool, "people", {"name": "Alice", "age": 30})
    assert isinstance(eid, uuid.UUID)

    entity = await entity_get(pool, eid)
    assert entity is not None
    assert entity["data"]["name"] == "Alice"
    assert entity["data"]["age"] == 30


async def test_entity_create_collection_not_found(pool):
    """entity_create raises ValueError for non-existent collection."""
    from butlers.tools.general import entity_create

    with pytest.raises(ValueError, match="not found"):
        await entity_create(pool, "nonexistent_collection", {"a": 1})


# ------------------------------------------------------------------
# entity_get
# ------------------------------------------------------------------


async def test_entity_get_missing(pool):
    """entity_get returns None for a non-existent entity."""
    from butlers.tools.general import entity_get

    result = await entity_get(pool, uuid.uuid4())
    assert result is None


# ------------------------------------------------------------------
# entity_update with deep merge
# ------------------------------------------------------------------


async def test_entity_update_shallow(pool):
    """entity_update merges top-level keys."""
    from butlers.tools.general import collection_create, entity_create, entity_get, entity_update

    await collection_create(pool, "update_shallow")
    eid = await entity_create(pool, "update_shallow", {"a": 1, "b": 2})

    await entity_update(pool, eid, {"b": 99, "c": 3})

    entity = await entity_get(pool, eid)
    assert entity["data"] == {"a": 1, "b": 99, "c": 3}


async def test_entity_update_deep_merge(pool):
    """entity_update deep merges nested objects."""
    from butlers.tools.general import collection_create, entity_create, entity_get, entity_update

    await collection_create(pool, "update_deep")
    eid = await entity_create(
        pool,
        "update_deep",
        {"config": {"theme": "dark", "lang": "en"}, "name": "test"},
    )

    await entity_update(pool, eid, {"config": {"lang": "fr", "font_size": 14}})

    entity = await entity_get(pool, eid)
    assert entity["data"]["config"] == {"theme": "dark", "lang": "fr", "font_size": 14}
    assert entity["data"]["name"] == "test"


async def test_entity_update_not_found(pool):
    """entity_update raises ValueError for non-existent entity."""
    from butlers.tools.general import entity_update

    with pytest.raises(ValueError, match="not found"):
        await entity_update(pool, uuid.uuid4(), {"a": 1})


# ------------------------------------------------------------------
# entity_delete
# ------------------------------------------------------------------


async def test_entity_delete(pool):
    """entity_delete removes the entity."""
    from butlers.tools.general import collection_create, entity_create, entity_delete, entity_get

    await collection_create(pool, "del_entity")
    eid = await entity_create(pool, "del_entity", {"x": 1})

    await entity_delete(pool, eid)
    assert await entity_get(pool, eid) is None


async def test_entity_delete_not_found(pool):
    """entity_delete raises ValueError for non-existent entity."""
    from butlers.tools.general import entity_delete

    with pytest.raises(ValueError, match="not found"):
        await entity_delete(pool, uuid.uuid4())


# ------------------------------------------------------------------
# entity_search
# ------------------------------------------------------------------


async def test_entity_search_by_collection(pool):
    """entity_search filters by collection name."""
    from butlers.tools.general import collection_create, entity_create, entity_search

    await collection_create(pool, "search_a")
    await collection_create(pool, "search_b")
    await entity_create(pool, "search_a", {"type": "alpha"})
    await entity_create(pool, "search_b", {"type": "beta"})

    results = await entity_search(pool, collection_name="search_a")
    assert len(results) == 1
    assert results[0]["data"]["type"] == "alpha"
    assert results[0]["collection_name"] == "search_a"


async def test_entity_search_by_jsonb_query(pool):
    """entity_search filters by JSONB containment."""
    from butlers.tools.general import collection_create, entity_create, entity_search

    await collection_create(pool, "search_jsonb")
    await entity_create(pool, "search_jsonb", {"color": "red", "size": "large"})
    await entity_create(pool, "search_jsonb", {"color": "blue", "size": "small"})
    await entity_create(pool, "search_jsonb", {"color": "red", "size": "small"})

    results = await entity_search(pool, query={"color": "red"})
    assert len(results) == 2
    for r in results:
        assert r["data"]["color"] == "red"


async def test_entity_search_combined(pool):
    """entity_search filters by both collection and JSONB query."""
    from butlers.tools.general import collection_create, entity_create, entity_search

    await collection_create(pool, "search_combo_x")
    await collection_create(pool, "search_combo_y")
    await entity_create(pool, "search_combo_x", {"status": "active"})
    await entity_create(pool, "search_combo_y", {"status": "active"})
    await entity_create(pool, "search_combo_x", {"status": "inactive"})

    results = await entity_search(
        pool, collection_name="search_combo_x", query={"status": "active"}
    )
    assert len(results) == 1
    assert results[0]["data"]["status"] == "active"
    assert results[0]["collection_name"] == "search_combo_x"


async def test_entity_search_no_filters(pool):
    """entity_search with no filters returns all entities."""
    from butlers.tools.general import entity_search

    results = await entity_search(pool)
    # Just verify it returns a list (other tests may have populated entities)
    assert isinstance(results, list)


# ------------------------------------------------------------------
# collection_export
# ------------------------------------------------------------------


async def test_collection_export(pool):
    """collection_export returns all entities from a collection."""
    from butlers.tools.general import collection_create, collection_export, entity_create

    await collection_create(pool, "export_coll")
    await entity_create(pool, "export_coll", {"item": 1})
    await entity_create(pool, "export_coll", {"item": 2})
    await entity_create(pool, "export_coll", {"item": 3})

    exported = await collection_export(pool, "export_coll")
    assert len(exported) == 3
    items = [e["data"]["item"] for e in exported]
    assert sorted(items) == [1, 2, 3]


async def test_collection_export_empty(pool):
    """collection_export returns empty list for a collection with no entities."""
    from butlers.tools.general import collection_create, collection_export

    await collection_create(pool, "empty_export")
    exported = await collection_export(pool, "empty_export")
    assert exported == []


# ------------------------------------------------------------------
# _deep_merge
# ------------------------------------------------------------------


def test_deep_merge_basic():
    """_deep_merge merges two flat dicts."""
    from butlers.tools.general import _deep_merge

    result = _deep_merge({"a": 1, "b": 2}, {"b": 3, "c": 4})
    assert result == {"a": 1, "b": 3, "c": 4}


def test_deep_merge_nested():
    """_deep_merge recursively merges nested dicts."""
    from butlers.tools.general import _deep_merge

    base = {"x": {"y": 1, "z": 2}, "top": "value"}
    override = {"x": {"z": 99, "w": 3}}
    result = _deep_merge(base, override)
    assert result == {"x": {"y": 1, "z": 99, "w": 3}, "top": "value"}


def test_deep_merge_override_replaces_non_dict():
    """_deep_merge replaces non-dict values even if base has a dict."""
    from butlers.tools.general import _deep_merge

    result = _deep_merge({"a": {"nested": 1}}, {"a": "string_now"})
    assert result == {"a": "string_now"}


def test_deep_merge_empty_override():
    """_deep_merge with empty override returns base unchanged."""
    from butlers.tools.general import _deep_merge

    result = _deep_merge({"a": 1}, {})
    assert result == {"a": 1}


# ------------------------------------------------------------------
# JSONB freeform value types
# ------------------------------------------------------------------


@pytest.mark.parametrize(
    "data",
    [
        {"string_val": "hello"},
        {"int_val": 42},
        {"float_val": 3.14},
        {"bool_val": True},
        {"null_val": None},
        {"list_val": [1, 2, 3]},
        {"nested": {"deep": {"value": "found"}}},
        {"mixed": [1, "two", {"three": 3}]},
    ],
    ids=["string", "integer", "float", "boolean", "null", "list", "nested", "mixed"],
)
async def test_freeform_jsonb_types(pool, data):
    """Entities accept various freeform JSONB data types."""
    from butlers.tools.general import collection_create, entity_create, entity_get

    coll_name = f"jsonb_types_{list(data.keys())[0]}"
    try:
        await collection_create(pool, coll_name)
    except Exception:
        pass  # May already exist from parametrize

    eid = await entity_create(pool, coll_name, data)
    entity = await entity_get(pool, eid)
    assert entity["data"] == data
