"""Tests for cost and usage tracking endpoints.

Verifies that the placeholder cost endpoints return correct empty/zero
responses and that the Pydantic models validate correctly.
"""

from __future__ import annotations

import httpx
import pytest

from butlers.api.app import create_app
from butlers.api.models import CostSummary, DailyCost, TopSession

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _app():
    """Create a fresh app instance for testing."""
    return create_app()


# ---------------------------------------------------------------------------
# GET /api/costs/summary
# ---------------------------------------------------------------------------


class TestCostSummary:
    async def test_summary_returns_zero_placeholder(self):
        """Summary endpoint returns zeroed-out placeholder data."""
        app = _app()
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

    async def test_summary_response_validates_as_model(self):
        """Summary response data can be parsed as CostSummary model."""
        app = _app()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/costs/summary")

        body = response.json()
        summary = CostSummary.model_validate(body["data"])
        assert summary.total_cost_usd == 0.0
        assert summary.total_sessions == 0


# ---------------------------------------------------------------------------
# GET /api/costs/daily
# ---------------------------------------------------------------------------


class TestDailyCosts:
    async def test_daily_returns_empty_list(self):
        """Daily endpoint returns empty list placeholder."""
        app = _app()
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
        app = _app()
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
        app = _app()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/costs/summary")

        body = response.json()
        assert "meta" in body

    async def test_daily_has_meta(self):
        """Daily response includes the meta field."""
        app = _app()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/costs/daily")

        body = response.json()
        assert "meta" in body

    async def test_top_sessions_has_meta(self):
        """Top-sessions response includes the meta field."""
        app = _app()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/costs/top-sessions")

        body = response.json()
        assert "meta" in body
