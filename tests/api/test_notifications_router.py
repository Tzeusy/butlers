"""Tests for the notifications API router."""

from __future__ import annotations

import httpx
import pytest

from butlers.api.app import create_app

pytestmark = pytest.mark.unit


class TestListNotifications:
    async def test_returns_empty_list(self):
        app = create_app()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/notifications/")
        assert response.status_code == 200
        body = response.json()
        assert body["data"] == []
        assert body["meta"]["total"] == 0
        assert body["meta"]["offset"] == 0
        assert body["meta"]["limit"] == 20

    async def test_custom_pagination_params(self):
        app = create_app()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/notifications/?offset=10&limit=5")
        assert response.status_code == 200
        body = response.json()
        assert body["data"] == []
        assert body["meta"]["offset"] == 10
        assert body["meta"]["limit"] == 5

    async def test_response_structure(self):
        app = create_app()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/notifications/")
        body = response.json()
        assert "data" in body
        assert "meta" in body
        assert isinstance(body["data"], list)
        assert isinstance(body["meta"], dict)
        assert "total" in body["meta"]
        assert "offset" in body["meta"]
        assert "limit" in body["meta"]


class TestNotificationStats:
    async def test_returns_zero_stats(self):
        app = create_app()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/notifications/stats")
        assert response.status_code == 200
        body = response.json()
        assert body["data"]["total"] == 0
        assert body["data"]["sent"] == 0
        assert body["data"]["failed"] == 0
        assert body["data"]["by_channel"] == {}
        assert body["data"]["by_butler"] == {}

    async def test_response_structure(self):
        app = create_app()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/notifications/stats")
        body = response.json()
        assert "data" in body
        assert "meta" in body
        stats = body["data"]
        assert set(stats.keys()) == {"total", "sent", "failed", "by_channel", "by_butler"}


class TestRouterRegistration:
    async def test_notifications_routes_registered(self):
        app = create_app()
        routes = [r.path for r in app.routes]
        assert "/api/notifications/" in routes
        assert "/api/notifications/stats" in routes
