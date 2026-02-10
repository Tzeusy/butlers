"""Dashboard API — FastAPI application factory.

Provides a single-page-of-glass REST API over the butler infrastructure.
The app factory creates a FastAPI instance with:
- CORS middleware (configurable origins)
- Lifespan handler for startup/shutdown of DB pools and MCP clients
- Health endpoint at GET /api/health
- Router registration for future endpoint modules
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from butlers.api.middleware import register_error_handlers


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle for DB pools and MCP clients.

    On startup: initialize resources (will be implemented in future tasks)
    On shutdown: close all connections cleanly
    """
    # Startup
    yield
    # Shutdown


def create_app(
    cors_origins: list[str] | None = None,
) -> FastAPI:
    """Create and configure the FastAPI application.

    Parameters
    ----------
    cors_origins:
        Allowed CORS origins. Defaults to ["http://localhost:5173"] for
        local Vite dev server.
    """
    if cors_origins is None:
        cors_origins = ["http://localhost:5173"]

    app = FastAPI(
        title="Butlers Dashboard API",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_error_handlers(app)

    @app.get("/api/health")
    async def health():
        return {"status": "ok"}

    return app
