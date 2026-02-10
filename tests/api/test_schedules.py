"""Tests for schedules API endpoints.

Verifies the API contract (status codes, response shapes) for schedule
endpoints.  Uses mocked DatabaseManager and MCPClientManager so no real
database or MCP server is required.

Issues: butlers-26h.5.1, 5.2, 5.3
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import httpx
import pytest

from butlers.api.app import create_app
from butlers.api.db import DatabaseManager
from butlers.api.deps import ButlerUnreachableError, MCPClientManager, get_mcp_manager
from butlers.api.routers.schedules import _get_db_manager

pytestmark = pytest.mark.unit

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime.now(tz=UTC)
_SCHEDULE_ID = uuid4()


def _make_schedule_record(
    *,
    schedule_id=None,
    name="daily-digest",
    cron="0 9 * * *",
    prompt="Send a daily digest",
    source="db",
    enabled=True,
    next_run_at=None,
    last_run_at=None,
    created_at=_NOW,
    updated_at=_NOW,
) -> dict:
    """Create a dict mimicking an asyncpg Record for scheduled_tasks columns."""
    return {
        "id": schedule_id or _SCHEDULE_ID,
        "name": name,
        "cron": cron,
        "prompt": prompt,
        "source": source,
        "enabled": enabled,
        "next_run_at": next_run_at,
        "last_run_at": last_run_at,
        "created_at": created_at,
        "updated_at": updated_at,
    }


def _mock_mcp_result(payload: dict | str = "ok") -> list:
    """Create a mock MCP call_tool result (list of content blocks)."""
    import json

    block = MagicMock()
    if isinstance(payload, dict):
        block.text = json.dumps(payload)
    else:
        block.text = payload
    return [block]


def _app_with_mock_db(
    *,
    fetch_rows: list | None = None,
):
    """Create a FastAPI app with a mocked DatabaseManager."""
    mock_pool = AsyncMock()
    mock_pool.fetch = AsyncMock(return_value=fetch_rows or [])

    mock_db = MagicMock(spec=DatabaseManager)
    mock_db.pool.return_value = mock_pool
    mock_db.butler_names = ["atlas", "switchboard"]

    app = create_app()
    app.dependency_overrides[_get_db_manager] = lambda: mock_db
    return app


def _app_with_mock_mcp(
    *,
    call_tool_result=None,
    call_tool_side_effect=None,
):
    """Create a FastAPI app with a mocked MCPClientManager for write ops."""
    mock_client = AsyncMock()
    if call_tool_side_effect is not None:
        mock_client.call_tool = AsyncMock(side_effect=call_tool_side_effect)
    else:
        mock_client.call_tool = AsyncMock(
            return_value=call_tool_result or _mock_mcp_result({"success": True})
        )

    mock_mgr = AsyncMock(spec=MCPClientManager)
    mock_mgr.get_client = AsyncMock(return_value=mock_client)

    # Also need a DB mock for the app to not fail on other routes
    mock_pool = AsyncMock()
    mock_pool.fetch = AsyncMock(return_value=[])
    mock_db = MagicMock(spec=DatabaseManager)
    mock_db.pool.return_value = mock_pool
    mock_db.butler_names = ["atlas"]

    app = create_app()
    app.dependency_overrides[_get_db_manager] = lambda: mock_db
    app.dependency_overrides[get_mcp_manager] = lambda: mock_mgr
    return app, mock_client


def _app_with_unreachable_butler():
    """Create a FastAPI app where MCP connections fail with 503."""
    mock_mgr = AsyncMock(spec=MCPClientManager)
    mock_mgr.get_client = AsyncMock(
        side_effect=ButlerUnreachableError("atlas", cause=ConnectionRefusedError())
    )

    mock_pool = AsyncMock()
    mock_pool.fetch = AsyncMock(return_value=[])
    mock_db = MagicMock(spec=DatabaseManager)
    mock_db.pool.return_value = mock_pool
    mock_db.butler_names = ["atlas"]

    app = create_app()
    app.dependency_overrides[_get_db_manager] = lambda: mock_db
    app.dependency_overrides[get_mcp_manager] = lambda: mock_mgr
    return app


# ---------------------------------------------------------------------------
# GET /api/butlers/{name}/schedules — list schedules
# ---------------------------------------------------------------------------


class TestListSchedules:
    async def test_returns_array_of_schedules(self):
        """GET should return an ApiResponse wrapping a list of schedules."""
        rows = [
            _make_schedule_record(schedule_id=uuid4(), name="task-a"),
            _make_schedule_record(schedule_id=uuid4(), name="task-b"),
        ]
        app = _app_with_mock_db(fetch_rows=rows)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/butlers/atlas/schedules")

        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body
        assert isinstance(body["data"], list)
        assert len(body["data"]) == 2
        assert body["data"][0]["name"] == "task-a"
        assert body["data"][1]["name"] == "task-b"

    async def test_empty_schedules(self):
        """When no schedules exist, return empty list."""
        app = _app_with_mock_db(fetch_rows=[])
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/butlers/atlas/schedules")

        assert resp.status_code == 200
        body = resp.json()
        assert body["data"] == []

    async def test_schedule_fields(self):
        """Each schedule should include all expected fields."""
        row = _make_schedule_record()
        app = _app_with_mock_db(fetch_rows=[row])
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/butlers/atlas/schedules")

        assert resp.status_code == 200
        schedule = resp.json()["data"][0]
        assert schedule["id"] == str(_SCHEDULE_ID)
        assert schedule["name"] == "daily-digest"
        assert schedule["cron"] == "0 9 * * *"
        assert schedule["prompt"] == "Send a daily digest"
        assert schedule["source"] == "db"
        assert schedule["enabled"] is True
        assert "created_at" in schedule
        assert "updated_at" in schedule

    async def test_butler_db_unavailable_returns_503(self):
        """When the butler's DB pool doesn't exist, return 503."""
        app = _app_with_mock_db()
        mock_db = MagicMock(spec=DatabaseManager)
        mock_db.pool.side_effect = KeyError("no pool")
        app.dependency_overrides[_get_db_manager] = lambda: mock_db

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/butlers/nonexistent/schedules")

        assert resp.status_code == 503


# ---------------------------------------------------------------------------
# POST /api/butlers/{name}/schedules — create schedule via MCP
# ---------------------------------------------------------------------------


class TestCreateSchedule:
    async def test_creates_schedule_via_mcp(self):
        """POST should proxy create through MCP and return 201."""
        app, mock_client = _app_with_mock_mcp(
            call_tool_result=_mock_mcp_result({"id": str(uuid4()), "name": "new-task"})
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/butlers/atlas/schedules",
                json={"name": "new-task", "cron": "*/5 * * * *", "prompt": "do stuff"},
            )

        assert resp.status_code == 201
        body = resp.json()
        assert "data" in body
        assert body["data"]["name"] == "new-task"

        # Verify MCP tool was called correctly
        mock_client.call_tool.assert_called_once_with(
            "schedule_create",
            {"name": "new-task", "cron": "*/5 * * * *", "prompt": "do stuff"},
        )

    async def test_butler_unreachable_returns_503(self):
        """When butler is unreachable, POST returns 503."""
        app = _app_with_unreachable_butler()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/butlers/atlas/schedules",
                json={"name": "new-task", "cron": "0 * * * *", "prompt": "test"},
            )

        assert resp.status_code == 503


# ---------------------------------------------------------------------------
# PUT /api/butlers/{name}/schedules/{id} — update schedule via MCP
# ---------------------------------------------------------------------------


class TestUpdateSchedule:
    async def test_updates_schedule_via_mcp(self):
        """PUT should proxy update through MCP."""
        sid = uuid4()
        app, mock_client = _app_with_mock_mcp(
            call_tool_result=_mock_mcp_result({"id": str(sid), "updated": True})
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.put(
                f"/api/butlers/atlas/schedules/{sid}",
                json={"cron": "0 12 * * *", "prompt": "updated prompt"},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body
        assert body["data"]["updated"] is True

        # Verify the MCP tool received the schedule id and update fields
        mock_client.call_tool.assert_called_once_with(
            "schedule_update",
            {"id": str(sid), "cron": "0 12 * * *", "prompt": "updated prompt"},
        )

    async def test_butler_unreachable_returns_503(self):
        """When butler is unreachable, PUT returns 503."""
        app = _app_with_unreachable_butler()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.put(
                f"/api/butlers/atlas/schedules/{uuid4()}",
                json={"cron": "0 12 * * *"},
            )

        assert resp.status_code == 503


# ---------------------------------------------------------------------------
# DELETE /api/butlers/{name}/schedules/{id} — delete schedule via MCP
# ---------------------------------------------------------------------------


class TestDeleteSchedule:
    async def test_deletes_schedule_via_mcp(self):
        """DELETE should proxy delete through MCP."""
        sid = uuid4()
        app, mock_client = _app_with_mock_mcp(call_tool_result=_mock_mcp_result({"deleted": True}))
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.delete(f"/api/butlers/atlas/schedules/{sid}")

        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body
        assert body["data"]["deleted"] is True

        mock_client.call_tool.assert_called_once_with(
            "schedule_delete",
            {"id": str(sid)},
        )

    async def test_butler_unreachable_returns_503(self):
        """When butler is unreachable, DELETE returns 503."""
        app = _app_with_unreachable_butler()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.delete(f"/api/butlers/atlas/schedules/{uuid4()}")

        assert resp.status_code == 503


# ---------------------------------------------------------------------------
# PATCH /api/butlers/{name}/schedules/{id}/toggle — toggle via MCP
# ---------------------------------------------------------------------------


class TestToggleSchedule:
    async def test_toggles_schedule_via_mcp(self):
        """PATCH toggle should proxy through MCP."""
        sid = uuid4()
        app, mock_client = _app_with_mock_mcp(call_tool_result=_mock_mcp_result({"enabled": False}))
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.patch(f"/api/butlers/atlas/schedules/{sid}/toggle")

        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body
        assert body["data"]["enabled"] is False

        mock_client.call_tool.assert_called_once_with(
            "schedule_toggle",
            {"id": str(sid)},
        )

    async def test_butler_unreachable_returns_503(self):
        """When butler is unreachable, PATCH toggle returns 503."""
        app = _app_with_unreachable_butler()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.patch(f"/api/butlers/atlas/schedules/{uuid4()}/toggle")

        assert resp.status_code == 503
