"""Tests for butlers.tools.switchboard — routing, registry, and classification."""

from __future__ import annotations

import shutil
import uuid
from dataclasses import dataclass

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
# dispatch_decomposed
# ------------------------------------------------------------------


async def test_dispatch_decomposed_single_target(pool):
    """dispatch_decomposed dispatches exactly one route() call for a single target."""
    from butlers.tools.switchboard import dispatch_decomposed, register_butler

    await pool.execute("DELETE FROM butler_registry")
    await pool.execute("DELETE FROM routing_log")
    await register_butler(pool, "health", "http://localhost:8101/sse", "Health butler")

    async def mock_call(endpoint_url, tool_name, args):
        return {"status": "handled", "butler": "health"}

    results = await dispatch_decomposed(
        pool,
        targets=[{"butler": "health", "prompt": "I have a headache"}],
        source_channel="telegram",
        call_fn=mock_call,
    )

    assert len(results) == 1
    assert results[0]["butler"] == "health"
    assert results[0]["result"] == {"status": "handled", "butler": "health"}
    assert results[0]["error"] is None

    # Verify exactly one routing_log entry
    rows = await pool.fetch("SELECT * FROM routing_log")
    assert len(rows) == 1
    assert rows[0]["target_butler"] == "health"
    assert rows[0]["success"] is True


async def test_dispatch_decomposed_multiple_targets(pool):
    """dispatch_decomposed dispatches route() for each target sequentially."""
    from butlers.tools.switchboard import dispatch_decomposed, register_butler

    await pool.execute("DELETE FROM butler_registry")
    await pool.execute("DELETE FROM routing_log")
    await register_butler(pool, "health", "http://localhost:8101/sse")
    await register_butler(pool, "general", "http://localhost:8102/sse")

    call_order: list[str] = []

    async def mock_call(endpoint_url, tool_name, args):
        # Track call order by endpoint
        call_order.append(endpoint_url)
        return {"handled": True}

    results = await dispatch_decomposed(
        pool,
        targets=[
            {"butler": "health", "prompt": "Check my vitals"},
            {"butler": "general", "prompt": "What time is it?"},
        ],
        call_fn=mock_call,
    )

    assert len(results) == 2
    assert results[0]["butler"] == "health"
    assert results[0]["error"] is None
    assert results[1]["butler"] == "general"
    assert results[1]["error"] is None

    # Verify sequential call order
    assert call_order == [
        "http://localhost:8101/sse",
        "http://localhost:8102/sse",
    ]

    # Verify two routing_log entries
    rows = await pool.fetch("SELECT * FROM routing_log ORDER BY created_at")
    assert len(rows) == 2
    assert rows[0]["target_butler"] == "health"
    assert rows[1]["target_butler"] == "general"


async def test_dispatch_decomposed_error_does_not_block_others(pool):
    """A failure in one sub-route does not prevent subsequent sub-routes."""
    from butlers.tools.switchboard import dispatch_decomposed, register_butler

    await pool.execute("DELETE FROM butler_registry")
    await pool.execute("DELETE FROM routing_log")
    await register_butler(pool, "failing", "http://localhost:8200/sse")
    await register_butler(pool, "working", "http://localhost:8201/sse")

    async def mock_call(endpoint_url, tool_name, args):
        if "8200" in endpoint_url:
            raise ConnectionError("Connection refused")
        return {"ok": True}

    results = await dispatch_decomposed(
        pool,
        targets=[
            {"butler": "failing", "prompt": "This will fail"},
            {"butler": "working", "prompt": "This should still work"},
        ],
        call_fn=mock_call,
    )

    assert len(results) == 2

    # First target failed
    assert results[0]["butler"] == "failing"
    assert results[0]["result"] is None
    assert "ConnectionError" in results[0]["error"]

    # Second target succeeded despite first failure
    assert results[1]["butler"] == "working"
    assert results[1]["result"] == {"ok": True}
    assert results[1]["error"] is None

    # Both logged independently
    rows = await pool.fetch("SELECT * FROM routing_log ORDER BY created_at")
    assert len(rows) == 2
    assert rows[0]["target_butler"] == "failing"
    assert rows[0]["success"] is False
    assert rows[1]["target_butler"] == "working"
    assert rows[1]["success"] is True


async def test_dispatch_decomposed_unknown_butler_in_targets(pool):
    """dispatch_decomposed handles unknown butlers gracefully without blocking others."""
    from butlers.tools.switchboard import dispatch_decomposed, register_butler

    await pool.execute("DELETE FROM butler_registry")
    await pool.execute("DELETE FROM routing_log")
    await register_butler(pool, "known", "http://localhost:8300/sse")

    async def mock_call(endpoint_url, tool_name, args):
        return {"ok": True}

    results = await dispatch_decomposed(
        pool,
        targets=[
            {"butler": "ghost", "prompt": "No butler here"},
            {"butler": "known", "prompt": "This works"},
        ],
        call_fn=mock_call,
    )

    assert len(results) == 2

    # Unknown butler gets an error
    assert results[0]["butler"] == "ghost"
    assert results[0]["result"] is None
    assert "not found" in results[0]["error"]

    # Known butler succeeds
    assert results[1]["butler"] == "known"
    assert results[1]["result"] == {"ok": True}
    assert results[1]["error"] is None


async def test_dispatch_decomposed_empty_targets(pool):
    """dispatch_decomposed returns empty list for empty targets."""
    from butlers.tools.switchboard import dispatch_decomposed

    results = await dispatch_decomposed(pool, targets=[])
    assert results == []


async def test_dispatch_decomposed_each_route_independently_logged(pool):
    """Each route() call in dispatch_decomposed creates its own routing_log entry."""
    from butlers.tools.switchboard import dispatch_decomposed, register_butler

    await pool.execute("DELETE FROM butler_registry")
    await pool.execute("DELETE FROM routing_log")
    await register_butler(pool, "a", "http://localhost:8401/sse")
    await register_butler(pool, "b", "http://localhost:8402/sse")
    await register_butler(pool, "c", "http://localhost:8403/sse")

    async def mock_call(endpoint_url, tool_name, args):
        if "8402" in endpoint_url:
            raise ValueError("b exploded")
        return {"ok": True}

    await dispatch_decomposed(
        pool,
        targets=[
            {"butler": "a", "prompt": "msg a"},
            {"butler": "b", "prompt": "msg b"},
            {"butler": "c", "prompt": "msg c"},
        ],
        source_channel="api",
        call_fn=mock_call,
    )

    rows = await pool.fetch("SELECT * FROM routing_log ORDER BY created_at")
    assert len(rows) == 3

    # Verify each log entry
    assert rows[0]["target_butler"] == "a"
    assert rows[0]["success"] is True
    assert rows[0]["source_butler"] == "api"

    assert rows[1]["target_butler"] == "b"
    assert rows[1]["success"] is False
    assert "b exploded" in rows[1]["error"]
    assert rows[1]["source_butler"] == "api"

    assert rows[2]["target_butler"] == "c"
    assert rows[2]["success"] is True
    assert rows[2]["source_butler"] == "api"


async def test_dispatch_decomposed_passes_source_id(pool):
    """dispatch_decomposed passes source_id through to route() args."""
    from butlers.tools.switchboard import dispatch_decomposed, register_butler

    await pool.execute("DELETE FROM butler_registry")
    await pool.execute("DELETE FROM routing_log")
    await register_butler(pool, "target", "http://localhost:8500/sse")

    captured_args: list[dict] = []

    async def mock_call(endpoint_url, tool_name, args):
        captured_args.append(args)
        return {"ok": True}

    await dispatch_decomposed(
        pool,
        targets=[{"butler": "target", "prompt": "hello"}],
        source_channel="telegram",
        source_id="msg-12345",
        call_fn=mock_call,
    )

    assert len(captured_args) == 1
    assert captured_args[0]["prompt"] == "hello"
    assert captured_args[0]["source_id"] == "msg-12345"
