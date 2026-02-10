"""Tests for cost and usage tracking endpoints.

Verifies the cost summary endpoint with MCP fan-out, pricing estimation,
period filtering, graceful fallback on unreachable butlers, and that
placeholder endpoints return correct empty/zero responses.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from butlers.api.app import create_app
from butlers.api.deps import (
    ButlerConnectionInfo,
    ButlerUnreachableError,
    MCPClientManager,
    get_butler_configs,
    get_mcp_manager,
    get_pricing,
)
from butlers.api.models import CostSummary, DailyCost, TopSession
from butlers.api.pricing import ModelPricing, PricingConfig

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_configs() -> list[ButlerConnectionInfo]:
    """Return a small set of butler configs for testing."""
    return [
        ButlerConnectionInfo(name="switchboard", port=8100, description="Routes messages"),
        ButlerConnectionInfo(name="general", port=8101, description="Catch-all assistant"),
    ]


def _make_pricing() -> PricingConfig:
    """Create a PricingConfig with known per-token prices."""
    return PricingConfig(
        models={
            "claude-sonnet-4-20250514": ModelPricing(
                input_price_per_token=0.000003,
                output_price_per_token=0.000015,
            ),
            "claude-haiku-35-20241022": ModelPricing(
                input_price_per_token=0.0000008,
                output_price_per_token=0.000004,
            ),
        }
    )


def _make_tool_result(data: dict) -> MagicMock:
    """Create a mock MCP tool result with JSON text content."""
    content_item = MagicMock()
    content_item.text = json.dumps(data)
    result = MagicMock()
    result.content = [content_item]
    return result


def _make_empty_tool_result() -> MagicMock:
    """Create a mock MCP tool result with no content."""
    result = MagicMock()
    result.content = []
    return result


def _make_manager_with_responses(
    configs: list[ButlerConnectionInfo],
    responses: dict[str, MagicMock | Exception],
) -> MCPClientManager:
    """Create an MCPClientManager mock where each butler returns a specific response."""
    mgr = MagicMock(spec=MCPClientManager)

    async def fake_get_client(name: str) -> MagicMock:
        resp = responses.get(name)
        if isinstance(resp, Exception):
            raise resp
        client = MagicMock()
        client.call_tool = AsyncMock(return_value=resp)
        return client

    mgr.get_client = AsyncMock(side_effect=fake_get_client)
    return mgr


def _app_with_overrides(
    mgr: MCPClientManager,
    configs: list[ButlerConnectionInfo],
    pricing: PricingConfig,
):
    """Create an app with dependency overrides for costs testing."""
    app = create_app()
    app.dependency_overrides[get_mcp_manager] = lambda: mgr
    app.dependency_overrides[get_butler_configs] = lambda: configs
    app.dependency_overrides[get_pricing] = lambda: pricing
    return app


# ---------------------------------------------------------------------------
# GET /api/costs/summary
# ---------------------------------------------------------------------------


class TestCostSummary:
    async def test_summary_returns_zero_when_no_butlers(self):
        """Summary endpoint returns zeroed-out data when no butlers configured."""
        mgr = MagicMock(spec=MCPClientManager)
        app = _app_with_overrides(mgr, [], _make_pricing())
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/costs/summary")

        assert response.status_code == 200
        body = response.json()
        assert "data" in body
        data = body["data"]
        assert data["total_cost_usd"] == 0.0
        assert data["total_sessions"] == 0
        assert data["total_input_tokens"] == 0
        assert data["total_output_tokens"] == 0
        assert data["by_butler"] == {}
        assert data["by_model"] == {}
        assert data["period"] == "today"

    async def test_summary_default_period_is_today(self):
        """Default period parameter is 'today'."""
        mgr = MagicMock(spec=MCPClientManager)
        app = _app_with_overrides(mgr, [], _make_pricing())
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/costs/summary")

        data = response.json()["data"]
        assert data["period"] == "today"

    async def test_summary_accepts_7d_period(self):
        """Period '7d' is accepted."""
        mgr = MagicMock(spec=MCPClientManager)
        app = _app_with_overrides(mgr, [], _make_pricing())
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/costs/summary?period=7d")

        assert response.status_code == 200
        assert response.json()["data"]["period"] == "7d"

    async def test_summary_accepts_30d_period(self):
        """Period '30d' is accepted."""
        mgr = MagicMock(spec=MCPClientManager)
        app = _app_with_overrides(mgr, [], _make_pricing())
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/costs/summary?period=30d")

        assert response.status_code == 200
        assert response.json()["data"]["period"] == "30d"

    async def test_summary_rejects_invalid_period(self):
        """Invalid period parameter returns 422."""
        mgr = MagicMock(spec=MCPClientManager)
        app = _app_with_overrides(mgr, [], _make_pricing())
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/costs/summary?period=90d")

        assert response.status_code == 422

    async def test_summary_aggregates_butler_costs(self):
        """Summary aggregates cost data from multiple butlers."""
        configs = _make_configs()
        pricing = _make_pricing()

        switchboard_data = {
            "total_sessions": 5,
            "total_input_tokens": 10000,
            "total_output_tokens": 5000,
            "by_model": {
                "claude-sonnet-4-20250514": {
                    "input_tokens": 10000,
                    "output_tokens": 5000,
                },
            },
        }
        general_data = {
            "total_sessions": 3,
            "total_input_tokens": 8000,
            "total_output_tokens": 4000,
            "by_model": {
                "claude-haiku-35-20241022": {
                    "input_tokens": 8000,
                    "output_tokens": 4000,
                },
            },
        }

        mgr = _make_manager_with_responses(
            configs,
            {
                "switchboard": _make_tool_result(switchboard_data),
                "general": _make_tool_result(general_data),
            },
        )
        app = _app_with_overrides(mgr, configs, pricing)

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/costs/summary")

        assert response.status_code == 200
        data = response.json()["data"]

        assert data["total_sessions"] == 8
        assert data["total_input_tokens"] == 18000
        assert data["total_output_tokens"] == 9000

        # Verify costs are calculated:
        # switchboard: 10000 * 0.000003 + 5000 * 0.000015 = 0.03 + 0.075 = 0.105
        # general: 8000 * 0.0000008 + 4000 * 0.000004 = 0.0064 + 0.016 = 0.0224
        assert data["total_cost_usd"] == pytest.approx(0.1274, abs=1e-4)
        assert "switchboard" in data["by_butler"]
        assert "general" in data["by_butler"]
        assert data["by_butler"]["switchboard"] == pytest.approx(0.105, abs=1e-4)
        assert data["by_butler"]["general"] == pytest.approx(0.0224, abs=1e-4)

        assert "claude-sonnet-4-20250514" in data["by_model"]
        assert "claude-haiku-35-20241022" in data["by_model"]

    async def test_summary_handles_unreachable_butler(self):
        """Unreachable butlers contribute zero to the aggregate."""
        configs = _make_configs()
        pricing = _make_pricing()

        switchboard_data = {
            "total_sessions": 2,
            "total_input_tokens": 1000,
            "total_output_tokens": 500,
            "by_model": {
                "claude-sonnet-4-20250514": {
                    "input_tokens": 1000,
                    "output_tokens": 500,
                },
            },
        }

        mgr = _make_manager_with_responses(
            configs,
            {
                "switchboard": _make_tool_result(switchboard_data),
                "general": ButlerUnreachableError("general"),
            },
        )
        app = _app_with_overrides(mgr, configs, pricing)

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/costs/summary")

        assert response.status_code == 200
        data = response.json()["data"]

        assert data["total_sessions"] == 2
        assert data["total_input_tokens"] == 1000
        assert data["total_output_tokens"] == 500
        assert "general" not in data["by_butler"]

    async def test_summary_handles_empty_tool_result(self):
        """Butler returning empty tool result contributes zero."""
        configs = [ButlerConnectionInfo(name="empty", port=8100)]
        pricing = _make_pricing()

        mgr = _make_manager_with_responses(
            configs,
            {"empty": _make_empty_tool_result()},
        )
        app = _app_with_overrides(mgr, configs, pricing)

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/costs/summary")

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["total_cost_usd"] == 0.0
        assert data["total_sessions"] == 0

    async def test_summary_response_validates_as_model(self):
        """Summary response data can be parsed as CostSummary model."""
        mgr = MagicMock(spec=MCPClientManager)
        app = _app_with_overrides(mgr, [], _make_pricing())
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/costs/summary")

        body = response.json()
        summary = CostSummary.model_validate(body["data"])
        assert summary.total_cost_usd == 0.0
        assert summary.total_sessions == 0
        assert summary.period == "today"

    async def test_summary_unknown_model_contributes_zero_cost(self):
        """A model not in pricing.toml contributes zero cost."""
        configs = [ButlerConnectionInfo(name="test", port=8100)]
        pricing = _make_pricing()

        data = {
            "total_sessions": 1,
            "total_input_tokens": 5000,
            "total_output_tokens": 2000,
            "by_model": {
                "unknown-model-v9": {
                    "input_tokens": 5000,
                    "output_tokens": 2000,
                },
            },
        }

        mgr = _make_manager_with_responses(
            configs,
            {"test": _make_tool_result(data)},
        )
        app = _app_with_overrides(mgr, configs, pricing)

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/costs/summary")

        assert response.status_code == 200
        resp_data = response.json()["data"]
        assert resp_data["total_cost_usd"] == 0.0
        assert resp_data["total_sessions"] == 1
        assert resp_data["total_input_tokens"] == 5000
        assert "test" not in resp_data["by_butler"]


# ---------------------------------------------------------------------------
# GET /api/costs/daily
# ---------------------------------------------------------------------------


class TestDailyCosts:
    async def test_daily_returns_empty_list(self):
        """Daily endpoint returns empty list placeholder."""
        app = create_app()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/costs/daily")

        assert response.status_code == 200
        body = response.json()
        assert "data" in body
        assert body["data"] == []

    async def test_daily_cost_model_validates(self):
        """DailyCost model validates a well-formed record."""
        record = DailyCost(
            date="2026-02-10",
            cost_usd=1.23,
            sessions=5,
            input_tokens=10000,
            output_tokens=5000,
        )
        assert record.date == "2026-02-10"
        assert record.cost_usd == 1.23
        assert record.sessions == 5


# ---------------------------------------------------------------------------
# GET /api/costs/top-sessions
# ---------------------------------------------------------------------------


class TestTopSessions:
    async def test_top_sessions_returns_empty_list(self):
        """Top-sessions endpoint returns empty list placeholder."""
        app = create_app()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/costs/top-sessions")

        assert response.status_code == 200
        body = response.json()
        assert "data" in body
        assert body["data"] == []

    async def test_top_session_model_validates(self):
        """TopSession model validates a well-formed record."""
        session = TopSession(
            session_id="abc-123",
            butler="general",
            cost_usd=0.45,
            input_tokens=8000,
            output_tokens=3000,
            model="claude-sonnet-4-20250514",
            started_at="2026-02-10T12:00:00Z",
        )
        assert session.session_id == "abc-123"
        assert session.butler == "general"
        assert session.model == "claude-sonnet-4-20250514"


# ---------------------------------------------------------------------------
# Response shape / meta
# ---------------------------------------------------------------------------


class TestResponseShape:
    async def test_summary_has_meta(self):
        """All responses include the meta field."""
        mgr = MagicMock(spec=MCPClientManager)
        app = _app_with_overrides(mgr, [], _make_pricing())
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/costs/summary")

        body = response.json()
        assert "meta" in body

    async def test_daily_has_meta(self):
        """Daily response includes the meta field."""
        app = create_app()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/costs/daily")

        body = response.json()
        assert "meta" in body

    async def test_top_sessions_has_meta(self):
        """Top-sessions response includes the meta field."""
        app = create_app()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/costs/top-sessions")

        body = response.json()
        assert "meta" in body
