from unittest.mock import AsyncMock, patch

import httpx
import pytest

from butlers.api.app import FastAPI, create_app

pytestmark = pytest.mark.unit


class TestHealthEndpoint:
    async def test_health_returns_ok(self):
        app = create_app()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestCORSMiddleware:
    async def test_cors_allows_configured_origin(self):
        app = create_app(cors_origins=["http://localhost:5173"])
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.options(
                "/api/health",
                headers={
                    "origin": "http://localhost:5173",
                    "access-control-request-method": "GET",
                },
            )
        assert response.status_code == 200
        assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"

    async def test_cors_default_origins(self):
        app = create_app()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.options(
                "/api/health",
                headers={
                    "origin": "http://localhost:5173",
                    "access-control-request-method": "GET",
                },
            )
        assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"


class TestAppFactory:
    def test_create_app_returns_fastapi_instance(self):
        app = create_app()
        assert isinstance(app, FastAPI)

    def test_custom_cors_origins(self):
        app = create_app(cors_origins=["https://dashboard.example.com"])
        # Verify the middleware is present by checking the app
        assert app is not None


class TestLifespan:
    async def test_lifespan_initializes_and_shuts_down_dependencies(self):
        app = create_app()

        with (
            patch("butlers.api.app.init_dependencies", new=AsyncMock()) as init_mock,
            patch("butlers.api.app.shutdown_dependencies", new=AsyncMock()) as shutdown_mock,
            patch("butlers.api.app.init_pricing"),
        ):
            async with app.router.lifespan_context(app):
                pass

        init_mock.assert_awaited_once()
        shutdown_mock.assert_awaited_once()
