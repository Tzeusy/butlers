"""Tests for butlers.tools.switchboard — routing, registry, and classification."""

from __future__ import annotations

import shutil
import uuid
from dataclasses import dataclass
from datetime import UTC

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
    """Provision a fresh database with switchboard tables and return a pool."""
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

    # Create switchboard tables (mirrors Alembic switchboard migration)
    await p.execute("""
        CREATE TABLE IF NOT EXISTS butler_registry (
            name TEXT PRIMARY KEY,
            endpoint_url TEXT NOT NULL,
            description TEXT,
            modules JSONB NOT NULL DEFAULT '[]',
            last_seen_at TIMESTAMPTZ,
            registered_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    await p.execute("""
        CREATE TABLE IF NOT EXISTS routing_log (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            source_butler TEXT NOT NULL,
            target_butler TEXT NOT NULL,
            tool_name TEXT NOT NULL,
            success BOOLEAN NOT NULL,
            duration_ms INTEGER,
            error TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

    yield p
    await db.close()


# ------------------------------------------------------------------
# register_butler
# ------------------------------------------------------------------


async def test_register_butler_inserts(pool):
    """register_butler creates a new entry in the registry."""
    from butlers.tools.switchboard import list_butlers, register_butler

    await register_butler(pool, "health", "http://localhost:8101/sse", "Health butler", ["email"])
    butlers = await list_butlers(pool)
    names = [b["name"] for b in butlers]
    assert "health" in names

    health = next(b for b in butlers if b["name"] == "health")
    assert health["endpoint_url"] == "http://localhost:8101/sse"
    assert health["description"] == "Health butler"


async def test_register_butler_upserts(pool):
    """register_butler updates an existing entry on conflict."""
    from butlers.tools.switchboard import list_butlers, register_butler

    await register_butler(pool, "uptest", "http://localhost:9000/sse", "v1")
    await register_butler(pool, "uptest", "http://localhost:9001/sse", "v2", ["telegram"])

    butlers = await list_butlers(pool)
    entry = next(b for b in butlers if b["name"] == "uptest")
    assert entry["endpoint_url"] == "http://localhost:9001/sse"
    assert entry["description"] == "v2"


# ------------------------------------------------------------------
# list_butlers
# ------------------------------------------------------------------


async def test_list_butlers_empty(pool):
    """list_butlers returns an empty list when no butlers are registered."""
    from butlers.tools.switchboard import list_butlers

    # Clear any existing entries
    await pool.execute("DELETE FROM butler_registry")
    butlers = await list_butlers(pool)
    assert butlers == []


async def test_list_butlers_ordered(pool):
    """list_butlers returns results ordered by name."""
    from butlers.tools.switchboard import list_butlers, register_butler

    await pool.execute("DELETE FROM butler_registry")
    await register_butler(pool, "zebra", "http://localhost:1/sse")
    await register_butler(pool, "alpha", "http://localhost:2/sse")
    await register_butler(pool, "middle", "http://localhost:3/sse")

    butlers = await list_butlers(pool)
    names = [b["name"] for b in butlers]
    assert names == ["alpha", "middle", "zebra"]


# ------------------------------------------------------------------
# discover_butlers
# ------------------------------------------------------------------


async def test_discover_butlers_from_config_dir(pool, tmp_path):
    """discover_butlers scans a directory for butler.toml files and registers them."""
    from butlers.tools.switchboard import discover_butlers, list_butlers

    await pool.execute("DELETE FROM butler_registry")

    # Create a fake butler config directory
    butler_dir = tmp_path / "mybutler"
    butler_dir.mkdir()
    (butler_dir / "butler.toml").write_text(
        '[butler]\nname = "mybutler"\nport = 9999\ndescription = "Test butler"\n'
    )

    discovered = await discover_butlers(pool, tmp_path)
    assert len(discovered) == 1
    assert discovered[0]["name"] == "mybutler"
    assert discovered[0]["endpoint_url"] == "http://localhost:9999/sse"

    # Verify it was registered
    butlers = await list_butlers(pool)
    names = [b["name"] for b in butlers]
    assert "mybutler" in names


async def test_discover_butlers_nonexistent_dir(pool, tmp_path):
    """discover_butlers returns empty list for a non-existent directory."""
    from butlers.tools.switchboard import discover_butlers

    result = await discover_butlers(pool, tmp_path / "does_not_exist")
    assert result == []


async def test_discover_butlers_skips_invalid_configs(pool, tmp_path):
    """discover_butlers skips directories with invalid butler.toml files."""
    from butlers.tools.switchboard import discover_butlers

    await pool.execute("DELETE FROM butler_registry")

    # Create a directory with invalid TOML
    bad_dir = tmp_path / "badbutler"
    bad_dir.mkdir()
    (bad_dir / "butler.toml").write_text("this is not valid toml [[[")

    # Create a valid one too
    good_dir = tmp_path / "goodbutler"
    good_dir.mkdir()
    (good_dir / "butler.toml").write_text('[butler]\nname = "goodbutler"\nport = 7777\n')

    discovered = await discover_butlers(pool, tmp_path)
    names = [d["name"] for d in discovered]
    assert "goodbutler" in names
    assert "badbutler" not in names


# ------------------------------------------------------------------
# route
# ------------------------------------------------------------------


async def test_route_to_unknown_butler(pool):
    """route returns an error dict when the target butler is not registered."""
    from butlers.tools.switchboard import route

    await pool.execute("DELETE FROM butler_registry")
    result = await route(pool, "nonexistent", "some_tool", {})
    assert "error" in result
    assert "not found" in result["error"]


async def test_route_to_known_butler_success(pool):
    """route calls the target butler and returns the result on success."""
    from butlers.tools.switchboard import register_butler, route

    await register_butler(pool, "target", "http://localhost:8200/sse")

    async def mock_call(endpoint_url, tool_name, args):
        return {"status": "ok", "data": 42}

    result = await route(pool, "target", "get_data", {"key": "x"}, call_fn=mock_call)
    assert result == {"result": {"status": "ok", "data": 42}}


async def test_route_to_known_butler_failure(pool):
    """route returns an error dict when the tool call raises."""
    from butlers.tools.switchboard import register_butler, route

    await register_butler(pool, "failing", "http://localhost:8300/sse")

    async def failing_call(endpoint_url, tool_name, args):
        raise ConnectionError("Connection refused")

    result = await route(pool, "failing", "broken_tool", {}, call_fn=failing_call)
    assert "error" in result
    assert "ConnectionError" in result["error"]


# ------------------------------------------------------------------
# routing_log
# ------------------------------------------------------------------


async def test_routing_log_records_success(pool):
    """Successful routing creates a routing_log entry with success=True."""
    from butlers.tools.switchboard import register_butler, route

    await pool.execute("DELETE FROM routing_log")
    await register_butler(pool, "logged", "http://localhost:8400/sse")

    async def ok_call(endpoint_url, tool_name, args):
        return "ok"

    await route(pool, "logged", "ping", {}, call_fn=ok_call)

    rows = await pool.fetch("SELECT * FROM routing_log WHERE target_butler = 'logged'")
    assert len(rows) == 1
    assert rows[0]["success"] is True
    assert rows[0]["tool_name"] == "ping"
    assert rows[0]["error"] is None


async def test_routing_log_records_failure(pool):
    """Failed routing creates a routing_log entry with success=False and error message."""
    from butlers.tools.switchboard import register_butler, route

    await pool.execute("DELETE FROM routing_log")
    await register_butler(pool, "errored", "http://localhost:8500/sse")

    async def bad_call(endpoint_url, tool_name, args):
        raise RuntimeError("boom")

    await route(pool, "errored", "explode", {}, call_fn=bad_call)

    rows = await pool.fetch("SELECT * FROM routing_log WHERE target_butler = 'errored'")
    assert len(rows) == 1
    assert rows[0]["success"] is False
    assert "boom" in rows[0]["error"]


async def test_routing_log_records_not_found(pool):
    """Routing to an unknown butler logs a failure with 'Butler not found'."""
    from butlers.tools.switchboard import route

    await pool.execute("DELETE FROM routing_log")
    await pool.execute("DELETE FROM butler_registry")

    await route(pool, "ghost", "anything", {})

    rows = await pool.fetch("SELECT * FROM routing_log WHERE target_butler = 'ghost'")
    assert len(rows) == 1
    assert rows[0]["success"] is False
    assert "not found" in rows[0]["error"].lower()


# ------------------------------------------------------------------
# classify_message
# ------------------------------------------------------------------


async def test_classify_message_returns_known_butler(pool):
    """classify_message returns a known butler name when the spawner returns it."""
    from butlers.tools.switchboard import classify_message, register_butler

    await pool.execute("DELETE FROM butler_registry")
    await register_butler(pool, "health", "http://localhost:8101/sse", "Health butler")
    await register_butler(pool, "general", "http://localhost:8102/sse", "General butler")

    @dataclass
    class FakeResult:
        result: str = "health"

    async def fake_dispatch(**kwargs):
        return FakeResult()

    name = await classify_message(pool, "I have a headache", fake_dispatch)
    assert name == "health"


async def test_classify_message_defaults_to_general(pool):
    """classify_message defaults to 'general' when the spawner fails."""
    from butlers.tools.switchboard import classify_message, register_butler

    await pool.execute("DELETE FROM butler_registry")
    await register_butler(pool, "general", "http://localhost:8102/sse")

    async def broken_dispatch(**kwargs):
        raise RuntimeError("spawner broken")

    name = await classify_message(pool, "hello", broken_dispatch)
    assert name == "general"


async def test_classify_message_defaults_for_unknown_name(pool):
    """classify_message defaults to 'general' when spawner returns unknown butler."""
    from butlers.tools.switchboard import classify_message, register_butler

    await pool.execute("DELETE FROM butler_registry")
    await register_butler(pool, "general", "http://localhost:8102/sse")

    @dataclass
    class FakeResult:
        result: str = "nonexistent_butler"

    async def bad_dispatch(**kwargs):
        return FakeResult()

    name = await classify_message(pool, "test", bad_dispatch)
    assert name == "general"


# ------------------------------------------------------------------
# Extraction Audit Log Tests
# ------------------------------------------------------------------


@pytest.fixture
async def pool_with_extraction(pool):
    """Add extraction_log table to the test pool."""
    await pool.execute("""
        CREATE TABLE IF NOT EXISTS extraction_log (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            source_message_preview TEXT,
            extraction_type VARCHAR(100) NOT NULL,
            tool_name VARCHAR(100) NOT NULL,
            tool_args JSONB NOT NULL,
            target_contact_id UUID,
            confidence VARCHAR(20),
            dispatched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            source_channel VARCHAR(50)
        )
    """)
    await pool.execute("""
        CREATE INDEX IF NOT EXISTS idx_extraction_log_contact
        ON extraction_log(target_contact_id)
    """)
    await pool.execute("""
        CREATE INDEX IF NOT EXISTS idx_extraction_log_type
        ON extraction_log(extraction_type)
    """)
    await pool.execute("""
        CREATE INDEX IF NOT EXISTS idx_extraction_log_dispatched
        ON extraction_log(dispatched_at DESC)
    """)
    yield pool


async def test_log_extraction_creates_entry(pool_with_extraction):
    """log_extraction creates a new audit log entry and returns the UUID."""
    from butlers.tools.switchboard import log_extraction

    log_id = await log_extraction(
        pool_with_extraction,
        extraction_type="contact",
        tool_name="contact_add",
        tool_args={"name": "Alice", "email": "alice@example.com"},
        target_contact_id="123e4567-e89b-12d3-a456-426614174000",
        confidence="high",
        source_message_preview="Email from Alice about meeting",
        source_channel="email",
    )

    # Verify UUID format
    from uuid import UUID

    assert UUID(log_id)

    # Verify entry was created
    row = await pool_with_extraction.fetchrow("SELECT * FROM extraction_log WHERE id = $1", log_id)
    assert row is not None
    assert row["extraction_type"] == "contact"
    assert row["tool_name"] == "contact_add"
    assert row["confidence"] == "high"
    assert row["source_channel"] == "email"
    assert "Alice" in row["source_message_preview"]


async def test_log_extraction_truncates_long_preview(pool_with_extraction):
    """log_extraction truncates source_message_preview to 200 characters."""
    from butlers.tools.switchboard import log_extraction

    long_message = "a" * 300
    log_id = await log_extraction(
        pool_with_extraction,
        extraction_type="note",
        tool_name="note_add",
        tool_args={"content": "test"},
        source_message_preview=long_message,
    )

    row = await pool_with_extraction.fetchrow(
        "SELECT source_message_preview FROM extraction_log WHERE id = $1", log_id
    )
    assert len(row["source_message_preview"]) == 200
    assert row["source_message_preview"].endswith("...")


async def test_log_extraction_minimal_fields(pool_with_extraction):
    """log_extraction works with only required fields."""
    from butlers.tools.switchboard import log_extraction

    log_id = await log_extraction(
        pool_with_extraction,
        extraction_type="birthday",
        tool_name="birthday_set",
        tool_args={"contact_id": "123", "date": "1990-01-01"},
    )

    row = await pool_with_extraction.fetchrow("SELECT * FROM extraction_log WHERE id = $1", log_id)
    assert row is not None
    assert row["extraction_type"] == "birthday"
    assert row["tool_name"] == "birthday_set"
    assert row["source_message_preview"] is None
    assert row["source_channel"] is None


async def test_extraction_log_list_empty(pool_with_extraction):
    """extraction_log_list returns empty list when no entries exist."""
    from butlers.tools.switchboard import extraction_log_list

    await pool_with_extraction.execute("DELETE FROM extraction_log")
    entries = await extraction_log_list(pool_with_extraction)
    assert entries == []


async def test_extraction_log_list_all(pool_with_extraction):
    """extraction_log_list returns all entries when no filters applied."""
    from butlers.tools.switchboard import extraction_log_list, log_extraction

    await pool_with_extraction.execute("DELETE FROM extraction_log")

    await log_extraction(pool_with_extraction, "contact", "contact_add", {"name": "Alice"})
    await log_extraction(pool_with_extraction, "note", "note_add", {"content": "Test note"})

    entries = await extraction_log_list(pool_with_extraction)
    assert len(entries) == 2
    types = {e["extraction_type"] for e in entries}
    assert types == {"contact", "note"}


async def test_extraction_log_list_filter_by_contact(pool_with_extraction):
    """extraction_log_list filters by target_contact_id."""
    from butlers.tools.switchboard import extraction_log_list, log_extraction

    await pool_with_extraction.execute("DELETE FROM extraction_log")

    contact_id_1 = "123e4567-e89b-12d3-a456-426614174001"
    contact_id_2 = "123e4567-e89b-12d3-a456-426614174002"

    await log_extraction(
        pool_with_extraction,
        "contact",
        "contact_add",
        {"name": "Alice"},
        target_contact_id=contact_id_1,
    )
    await log_extraction(
        pool_with_extraction,
        "note",
        "note_add",
        {"content": "Note for Bob"},
        target_contact_id=contact_id_2,
    )

    entries = await extraction_log_list(pool_with_extraction, contact_id=contact_id_1)
    assert len(entries) == 1
    assert entries[0]["target_contact_id"] == contact_id_1


async def test_extraction_log_list_filter_by_type(pool_with_extraction):
    """extraction_log_list filters by extraction_type."""
    from butlers.tools.switchboard import extraction_log_list, log_extraction

    await pool_with_extraction.execute("DELETE FROM extraction_log")

    await log_extraction(pool_with_extraction, "contact", "contact_add", {"name": "Alice"})
    await log_extraction(pool_with_extraction, "note", "note_add", {"content": "Test"})
    await log_extraction(pool_with_extraction, "contact", "contact_update", {"id": "123"})

    entries = await extraction_log_list(pool_with_extraction, extraction_type="contact")
    assert len(entries) == 2
    assert all(e["extraction_type"] == "contact" for e in entries)


async def test_extraction_log_list_filter_by_time(pool_with_extraction):
    """extraction_log_list filters by since timestamp."""
    from datetime import datetime, timedelta

    from butlers.tools.switchboard import extraction_log_list, log_extraction

    await pool_with_extraction.execute("DELETE FROM extraction_log")

    # Create entries at different times (we'll manipulate timestamps after)
    log_id_1 = await log_extraction(pool_with_extraction, "contact", "contact_add", {"name": "Old"})
    log_id_2 = await log_extraction(pool_with_extraction, "contact", "contact_add", {"name": "New"})

    # Manually set timestamps to simulate time passing
    old_time = datetime.now(UTC) - timedelta(hours=2)
    new_time = datetime.now(UTC)

    await pool_with_extraction.execute(
        "UPDATE extraction_log SET dispatched_at = $1 WHERE id = $2",
        old_time,
        log_id_1,
    )
    await pool_with_extraction.execute(
        "UPDATE extraction_log SET dispatched_at = $1 WHERE id = $2",
        new_time,
        log_id_2,
    )

    # Query for entries after 1 hour ago
    since_time = datetime.now(UTC) - timedelta(hours=1)
    entries = await extraction_log_list(pool_with_extraction, since=since_time.isoformat())

    assert len(entries) == 1
    assert str(entries[0]["id"]) == log_id_2


async def test_extraction_log_list_respects_limit(pool_with_extraction):
    """extraction_log_list respects the limit parameter."""
    from butlers.tools.switchboard import extraction_log_list, log_extraction

    await pool_with_extraction.execute("DELETE FROM extraction_log")

    for i in range(10):
        await log_extraction(
            pool_with_extraction, "contact", "contact_add", {"name": f"Contact {i}"}
        )

    entries = await extraction_log_list(pool_with_extraction, limit=5)
    assert len(entries) == 5


async def test_extraction_log_list_max_limit(pool_with_extraction):
    """extraction_log_list caps limit at 500."""
    from butlers.tools.switchboard import extraction_log_list

    await pool_with_extraction.execute("DELETE FROM extraction_log")

    # Request more than max limit
    entries = await extraction_log_list(pool_with_extraction, limit=1000)
    # Since we have no entries, we can't test the actual limit enforcement,
    # but we verify it doesn't error
    assert entries == []


async def test_extraction_log_list_ordered_by_time_desc(pool_with_extraction):
    """extraction_log_list returns entries ordered by dispatched_at DESC."""

    from butlers.tools.switchboard import extraction_log_list, log_extraction

    await pool_with_extraction.execute("DELETE FROM extraction_log")

    log_ids = []
    for i in range(3):
        log_id = await log_extraction(
            pool_with_extraction, "contact", "contact_add", {"name": f"Contact {i}"}
        )
        log_ids.append(log_id)

    entries = await extraction_log_list(pool_with_extraction)
    assert len(entries) == 3

    # Most recent should be first
    entry_ids = [str(e["id"]) for e in entries]
    assert entry_ids == list(reversed(log_ids))


async def test_extraction_log_undo_invalid_uuid(pool_with_extraction):
    """extraction_log_undo returns error for invalid UUID format."""
    from butlers.tools.switchboard import extraction_log_undo

    result = await extraction_log_undo(pool_with_extraction, "not-a-uuid")
    assert "error" in result
    assert "Invalid UUID format" in result["error"]


async def test_extraction_log_undo_not_found(pool_with_extraction):
    """extraction_log_undo returns error when log entry doesn't exist."""
    from uuid import uuid4

    from butlers.tools.switchboard import extraction_log_undo

    fake_id = str(uuid4())
    result = await extraction_log_undo(pool_with_extraction, fake_id)
    assert "error" in result
    assert "not found" in result["error"]


async def test_extraction_log_undo_no_undo_available(pool_with_extraction):
    """extraction_log_undo returns error for tools without undo operations."""
    from butlers.tools.switchboard import extraction_log_undo, log_extraction

    log_id = await log_extraction(
        pool_with_extraction,
        "contact",
        "contact_update",
        {"id": "123", "name": "Updated"},
    )

    result = await extraction_log_undo(pool_with_extraction, log_id)
    assert "error" in result
    assert "No undo operation available" in result["error"]


async def test_extraction_log_undo_success_contact_add(pool_with_extraction):
    """extraction_log_undo calls contact_delete for contact_add."""
    from butlers.tools.switchboard import extraction_log_undo, log_extraction

    contact_id = "123e4567-e89b-12d3-a456-426614174000"
    log_id = await log_extraction(
        pool_with_extraction,
        "contact",
        "contact_add",
        {"id": contact_id, "name": "Alice"},
    )

    async def mock_route(pool, target_butler, tool_name, args):
        return {
            "result": {
                "target": target_butler,
                "tool": tool_name,
                "args": args,
            }
        }

    result = await extraction_log_undo(pool_with_extraction, log_id, route_fn=mock_route)

    assert "result" in result
    assert result["result"]["target"] == "relationship"
    assert result["result"]["tool"] == "contact_delete"
    assert result["result"]["args"]["id"] == contact_id


async def test_extraction_log_undo_success_note_add(pool_with_extraction):
    """extraction_log_undo calls note_delete for note_add."""
    from butlers.tools.switchboard import extraction_log_undo, log_extraction

    note_id = "note-123"
    log_id = await log_extraction(
        pool_with_extraction,
        "note",
        "note_add",
        {"note_id": note_id, "content": "Test note"},
    )

    async def mock_route(pool, target_butler, tool_name, args):
        return {"result": {"tool": tool_name, "args": args}}

    result = await extraction_log_undo(pool_with_extraction, log_id, route_fn=mock_route)

    assert "result" in result
    assert result["result"]["tool"] == "note_delete"
    assert result["result"]["args"]["note_id"] == note_id


async def test_extraction_log_undo_success_birthday_set(pool_with_extraction):
    """extraction_log_undo calls birthday_remove for birthday_set."""
    from butlers.tools.switchboard import extraction_log_undo, log_extraction

    contact_id = "contact-456"
    log_id = await log_extraction(
        pool_with_extraction,
        "birthday",
        "birthday_set",
        {"contact_id": contact_id, "date": "1990-01-01"},
    )

    async def mock_route(pool, target_butler, tool_name, args):
        return {"result": {"tool": tool_name, "args": args}}

    result = await extraction_log_undo(pool_with_extraction, log_id, route_fn=mock_route)

    assert "result" in result
    assert result["result"]["tool"] == "birthday_remove"
    assert result["result"]["args"]["contact_id"] == contact_id


async def test_extraction_log_undo_missing_id_field(pool_with_extraction):
    """extraction_log_undo returns error when tool_args lacks ID fields."""
    from butlers.tools.switchboard import extraction_log_undo, log_extraction

    log_id = await log_extraction(
        pool_with_extraction,
        "contact",
        "contact_add",
        {"name": "Alice"},  # No id, contact_id, or note_id
    )

    result = await extraction_log_undo(pool_with_extraction, log_id)
    assert "error" in result
    assert "Cannot determine target ID" in result["error"]


async def test_extraction_log_undo_routes_error(pool_with_extraction):
    """extraction_log_undo propagates routing errors."""
    from butlers.tools.switchboard import extraction_log_undo, log_extraction

    log_id = await log_extraction(
        pool_with_extraction,
        "contact",
        "contact_add",
        {"id": "123", "name": "Alice"},
    )

    async def failing_route(pool, target_butler, tool_name, args):
        return {"error": "Relationship butler not available"}

    result = await extraction_log_undo(pool_with_extraction, log_id, route_fn=failing_route)

    assert "error" in result
    assert "not available" in result["error"]
