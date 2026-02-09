"""Tests for butlers.tools.heartbeat — tick cycle for all registered butlers."""

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
    """Provision a fresh database and return a pool."""
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

    yield p
    await db.close()


# ------------------------------------------------------------------
# tick_all_butlers — core functionality
# ------------------------------------------------------------------


async def test_tick_all_butlers_ticks_all_except_heartbeat(pool):
    """tick_all_butlers calls tick_fn for each butler except heartbeat."""
    from butlers.tools.heartbeat import tick_all_butlers

    # Mock butler registry
    butlers = [
        {"name": "general", "endpoint_url": "http://localhost:8101/sse"},
        {"name": "health", "endpoint_url": "http://localhost:8102/sse"},
        {"name": "heartbeat", "endpoint_url": "http://localhost:8199/sse"},
        {"name": "relationship", "endpoint_url": "http://localhost:8103/sse"},
    ]

    async def mock_list_butlers():
        return butlers

    ticked_names = []

    async def mock_tick_fn(name: str):
        ticked_names.append(name)

    result = await tick_all_butlers(pool, mock_list_butlers, mock_tick_fn)

    # Should tick all except heartbeat
    assert set(ticked_names) == {"general", "health", "relationship"}
    assert result["total"] == 3
    assert set(result["successful"]) == {"general", "health", "relationship"}
    assert result["failed"] == []


async def test_tick_all_butlers_self_exclusion(pool):
    """tick_all_butlers excludes heartbeat from the tick targets."""
    from butlers.tools.heartbeat import tick_all_butlers

    butlers = [
        {"name": "heartbeat", "endpoint_url": "http://localhost:8199/sse"},
        {"name": "general", "endpoint_url": "http://localhost:8101/sse"},
    ]

    async def mock_list_butlers():
        return butlers

    ticked_names = []

    async def mock_tick_fn(name: str):
        ticked_names.append(name)

    result = await tick_all_butlers(pool, mock_list_butlers, mock_tick_fn)

    # heartbeat should NOT be in the ticked list
    assert "heartbeat" not in ticked_names
    assert ticked_names == ["general"]
    assert result["total"] == 1
    assert result["successful"] == ["general"]


async def test_tick_all_butlers_error_resilience(pool):
    """tick_all_butlers continues ticking even if one butler fails."""
    from butlers.tools.heartbeat import tick_all_butlers

    butlers = [
        {"name": "alpha", "endpoint_url": "http://localhost:8101/sse"},
        {"name": "beta", "endpoint_url": "http://localhost:8102/sse"},
        {"name": "gamma", "endpoint_url": "http://localhost:8103/sse"},
    ]

    async def mock_list_butlers():
        return butlers

    async def failing_tick_fn(name: str):
        if name == "beta":
            raise ConnectionError("beta is down")
        # alpha and gamma succeed

    result = await tick_all_butlers(pool, mock_list_butlers, failing_tick_fn)

    assert result["total"] == 3
    assert set(result["successful"]) == {"alpha", "gamma"}
    assert len(result["failed"]) == 1
    assert result["failed"][0]["name"] == "beta"
    assert "ConnectionError" in result["failed"][0]["error"]
    assert "beta is down" in result["failed"][0]["error"]


async def test_tick_all_butlers_multiple_failures(pool):
    """tick_all_butlers handles multiple butler failures gracefully."""
    from butlers.tools.heartbeat import tick_all_butlers

    butlers = [
        {"name": "a", "endpoint_url": "http://localhost:8101/sse"},
        {"name": "b", "endpoint_url": "http://localhost:8102/sse"},
        {"name": "c", "endpoint_url": "http://localhost:8103/sse"},
        {"name": "d", "endpoint_url": "http://localhost:8104/sse"},
    ]

    async def mock_list_butlers():
        return butlers

    async def multi_fail_tick_fn(name: str):
        if name in {"a", "c"}:
            raise RuntimeError(f"{name} failed")

    result = await tick_all_butlers(pool, mock_list_butlers, multi_fail_tick_fn)

    assert result["total"] == 4
    assert set(result["successful"]) == {"b", "d"}
    assert len(result["failed"]) == 2
    failed_names = {f["name"] for f in result["failed"]}
    assert failed_names == {"a", "c"}


async def test_tick_all_butlers_list_butlers_fails(pool):
    """tick_all_butlers returns error summary when list_butlers_fn fails."""
    from butlers.tools.heartbeat import tick_all_butlers

    async def broken_list_butlers():
        raise RuntimeError("Registry unavailable")

    async def mock_tick_fn(name: str):
        pass

    result = await tick_all_butlers(pool, broken_list_butlers, mock_tick_fn)

    assert result["total"] == 0
    assert result["successful"] == []
    assert len(result["failed"]) == 1
    assert result["failed"][0]["name"] == "list_butlers"
    assert "RuntimeError" in result["failed"][0]["error"]
    assert "Registry unavailable" in result["failed"][0]["error"]


async def test_tick_all_butlers_empty_registry(pool):
    """tick_all_butlers handles an empty butler registry."""
    from butlers.tools.heartbeat import tick_all_butlers

    async def empty_list_butlers():
        return []

    tick_called = False

    async def mock_tick_fn(name: str):
        nonlocal tick_called
        tick_called = True

    result = await tick_all_butlers(pool, empty_list_butlers, mock_tick_fn)

    assert result["total"] == 0
    assert result["successful"] == []
    assert result["failed"] == []
    assert not tick_called


async def test_tick_all_butlers_only_heartbeat_in_registry(pool):
    """tick_all_butlers does nothing when only heartbeat is registered."""
    from butlers.tools.heartbeat import tick_all_butlers

    butlers = [{"name": "heartbeat", "endpoint_url": "http://localhost:8199/sse"}]

    async def mock_list_butlers():
        return butlers

    tick_called = False

    async def mock_tick_fn(name: str):
        nonlocal tick_called
        tick_called = True

    result = await tick_all_butlers(pool, mock_list_butlers, mock_tick_fn)

    assert result["total"] == 0
    assert result["successful"] == []
    assert result["failed"] == []
    assert not tick_called


# ------------------------------------------------------------------
# Integration with switchboard tools
# ------------------------------------------------------------------


async def test_tick_all_with_real_switchboard_list_butlers(pool):
    """tick_all_butlers integrates with switchboard.list_butlers."""
    from butlers.tools.heartbeat import tick_all_butlers
    from butlers.tools.switchboard import list_butlers, register_butler

    # Create switchboard tables
    await pool.execute("""
        CREATE TABLE IF NOT EXISTS butler_registry (
            name TEXT PRIMARY KEY,
            endpoint_url TEXT NOT NULL,
            description TEXT,
            modules JSONB NOT NULL DEFAULT '[]',
            last_seen_at TIMESTAMPTZ,
            registered_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

    # Register some butlers
    await pool.execute("DELETE FROM butler_registry")
    await register_butler(pool, "general", "http://localhost:8101/sse")
    await register_butler(pool, "health", "http://localhost:8102/sse")
    await register_butler(pool, "heartbeat", "http://localhost:8199/sse")

    ticked_names = []

    async def mock_tick_fn(name: str):
        ticked_names.append(name)

    async def wrapped_list_butlers():
        return await list_butlers(pool)

    result = await tick_all_butlers(pool, wrapped_list_butlers, mock_tick_fn)

    # Should tick all except heartbeat
    assert set(ticked_names) == {"general", "health"}
    assert result["total"] == 2
    assert set(result["successful"]) == {"general", "health"}
    assert result["failed"] == []


async def test_tick_all_with_switchboard_route_simulation(pool):
    """tick_all_butlers can use switchboard.route as the tick_fn."""
    from butlers.tools.heartbeat import tick_all_butlers
    from butlers.tools.switchboard import register_butler, route

    # Create switchboard tables
    await pool.execute("""
        CREATE TABLE IF NOT EXISTS butler_registry (
            name TEXT PRIMARY KEY,
            endpoint_url TEXT NOT NULL,
            description TEXT,
            modules JSONB NOT NULL DEFAULT '[]',
            last_seen_at TIMESTAMPTZ,
            registered_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    await pool.execute("""
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

    await pool.execute("DELETE FROM butler_registry")
    await pool.execute("DELETE FROM routing_log")
    await register_butler(pool, "general", "http://localhost:8101/sse")
    await register_butler(pool, "heartbeat", "http://localhost:8199/sse")

    # Mock the route call with a custom call_fn
    async def mock_call_fn(endpoint_url, tool_name, args):
        return {"status": "ok", "ticked": True}

    async def wrapped_list_butlers():
        butlers = await pool.fetch("SELECT * FROM butler_registry ORDER BY name")
        return [dict(row) for row in butlers]

    async def tick_via_route(name: str):
        await route(pool, name, "tick", {}, source_butler="heartbeat", call_fn=mock_call_fn)

    result = await tick_all_butlers(pool, wrapped_list_butlers, tick_via_route)

    # Should have ticked general (not heartbeat)
    assert result["total"] == 1
    assert result["successful"] == ["general"]
    assert result["failed"] == []

    # Verify routing was logged
    logs = await pool.fetch(
        "SELECT * FROM routing_log WHERE source_butler = 'heartbeat' ORDER BY created_at"
    )
    assert len(logs) == 1
    assert logs[0]["target_butler"] == "general"
    assert logs[0]["tool_name"] == "tick"
    assert logs[0]["success"] is True
