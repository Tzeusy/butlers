"""Butler daemon — the central orchestrator for a single butler instance.

The ButlerDaemon manages the lifecycle of a butler:
1. Load config from butler.toml
2. Initialize telemetry
3. Validate credentials (env vars)
4. Provision database
5. Run core Alembic migrations
6. Initialize modules (topological order)
7. Run module Alembic migrations
8. Module on_startup (topological order)
9. Create CCSpawner
10. Sync TOML schedules to DB
11. Create FastMCP server and register core tools
12. Register module MCP tools

On startup failure, already-initialized modules get on_shutdown() called.

Graceful shutdown: (a) stops accepting new MCP connections,
(b) drains in-flight CC sessions up to a configurable timeout,
(c) shuts down modules in reverse topological order, (d) closes DB pool.
"""

from __future__ import annotations

import logging
import time
import uuid
from pathlib import Path
from typing import Any

from fastmcp import FastMCP

from butlers.config import ButlerConfig, load_config
from butlers.core.scheduler import schedule_create as _schedule_create
from butlers.core.scheduler import schedule_delete as _schedule_delete
from butlers.core.scheduler import schedule_list as _schedule_list
from butlers.core.scheduler import schedule_update as _schedule_update
from butlers.core.scheduler import sync_schedules
from butlers.core.scheduler import tick as _tick
from butlers.core.sessions import sessions_get as _sessions_get
from butlers.core.sessions import sessions_list as _sessions_list
from butlers.core.spawner import CCSpawner
from butlers.core.state import state_delete as _state_delete
from butlers.core.state import state_get as _state_get
from butlers.core.state import state_list as _state_list
from butlers.core.state import state_set as _state_set
from butlers.core.telemetry import init_telemetry
from butlers.credentials import validate_credentials
from butlers.db import Database
from butlers.migrations import run_migrations
from butlers.modules.base import Module
from butlers.modules.registry import ModuleRegistry

logger = logging.getLogger(__name__)


class ButlerDaemon:
    """Central orchestrator for a single butler instance."""

    def __init__(
        self,
        config_dir: Path,
        registry: ModuleRegistry | None = None,
    ) -> None:
        self.config_dir = config_dir
        self._registry = registry or ModuleRegistry()
        self.config: ButlerConfig | None = None
        self.db: Database | None = None
        self.mcp: FastMCP | None = None
        self.spawner: CCSpawner | None = None
        self._modules: list[Module] = []
        self._started_at: float | None = None
        self._accepting_connections = False

    async def start(self) -> None:
        """Execute the full startup sequence.

        Steps execute in order. A failure at any step prevents subsequent steps.
        """
        # 1. Load config
        self.config = load_config(self.config_dir)
        logger.info("Loaded config for butler: %s", self.config.name)

        # 2. Initialize telemetry
        init_telemetry(f"butler.{self.config.name}")

        # 3. Validate credentials
        module_creds = self._collect_module_credentials()
        validate_credentials(
            self.config.env_required,
            self.config.env_optional,
            module_credentials=module_creds,
        )

        # 4. Provision database
        self.db = Database.from_env(self.config.db_name)
        await self.db.provision()
        pool = await self.db.connect()

        # 5. Run core Alembic migrations
        db_url = self._build_db_url()
        await run_migrations(db_url, chain="core")

        # 6. Initialize modules (topological order)
        self._modules = self._registry.load_from_config(self.config.modules)

        # 7. Run module Alembic migrations
        for mod in self._modules:
            rev = mod.migration_revisions()
            if rev:
                await run_migrations(db_url, chain=rev)

        # 8. Module on_startup (topological order)
        started_modules: list[Module] = []
        try:
            for mod in self._modules:
                mod_config = self.config.modules.get(mod.name, {})
                await mod.on_startup(mod_config, self.db)
                started_modules.append(mod)
        except Exception:
            # Clean up already-started modules in reverse order
            logger.error(
                "Startup failure; cleaning up %d already-started module(s)",
                len(started_modules),
            )
            for mod in reversed(started_modules):
                try:
                    await mod.on_shutdown()
                except Exception:
                    logger.exception("Error during cleanup shutdown of module: %s", mod.name)
            raise

        # 9. Create CCSpawner
        self.spawner = CCSpawner(
            config=self.config,
            config_dir=self.config_dir,
            pool=pool,
            module_credentials_env=module_creds,
        )

        # 10. Sync TOML schedules to DB
        schedules = [
            {"name": s.name, "cron": s.cron, "prompt": s.prompt} for s in self.config.schedules
        ]
        await sync_schedules(pool, schedules)

        # 11. Create FastMCP and register core tools
        self.mcp = FastMCP(self.config.name)
        self._register_core_tools()

        # 12. Register module MCP tools
        await self._register_module_tools()

        # Mark as accepting connections and record startup time
        self._accepting_connections = True
        self._started_at = time.monotonic()
        logger.info("Butler %s started on port %d", self.config.name, self.config.port)

    def _collect_module_credentials(self) -> dict[str, list[str]]:
        """Collect credentials_env from enabled modules."""
        creds: dict[str, list[str]] = {}
        for mod_name in self.config.modules:
            try:
                temp_modules = self._registry.load_from_config({mod_name: {}})
                if temp_modules:
                    mod = temp_modules[0]
                    env_list = getattr(mod, "credentials_env", [])
                    if env_list:
                        creds[mod_name] = list(env_list)
            except Exception:
                pass  # Module may have deps not met; skip credential collection
        return creds

    def _build_db_url(self) -> str:
        """Build SQLAlchemy-compatible DB URL from Database config."""
        db = self.db
        return f"postgresql://{db.user}:{db.password}@{db.host}:{db.port}/{db.db_name}"

    def _register_core_tools(self) -> None:
        """Register all core MCP tools on the FastMCP server."""
        mcp = self.mcp
        pool = self.db.pool
        spawner = self.spawner
        daemon = self

        @mcp.tool()
        async def status() -> dict:
            """Return butler identity, health, loaded modules, and uptime."""
            uptime_seconds = time.monotonic() - daemon._started_at if daemon._started_at else 0
            return {
                "name": daemon.config.name,
                "description": daemon.config.description,
                "port": daemon.config.port,
                "modules": [mod.name for mod in daemon._modules],
                "health": "ok",
                "uptime_seconds": round(uptime_seconds, 1),
            }

        @mcp.tool()
        async def trigger(prompt: str, context: str | None = None) -> dict:
            """Trigger the CC spawner with a prompt.

            Parameters
            ----------
            prompt:
                The prompt to send to the CC instance.
            context:
                Optional text to prepend to the prompt.
            """
            result = await spawner.trigger(
                prompt=prompt, context=context, trigger_source="trigger_tool"
            )
            return {
                "output": result.output,
                "success": result.success,
                "error": result.error,
                "duration_ms": result.duration_ms,
            }

        @mcp.tool()
        async def tick() -> dict:
            """Evaluate due scheduled tasks and dispatch them now."""
            count = await _tick(pool, spawner.trigger)
            return {"dispatched": count}

        # State tools
        @mcp.tool()
        async def state_get(key: str) -> dict:
            """Get a value from the state store."""
            value = await _state_get(pool, key)
            return {"key": key, "value": value}

        @mcp.tool()
        async def state_set(key: str, value: Any) -> dict:
            """Set a value in the state store."""
            await _state_set(pool, key, value)
            return {"key": key, "status": "ok"}

        @mcp.tool()
        async def state_delete(key: str) -> dict:
            """Delete a key from the state store."""
            await _state_delete(pool, key)
            return {"key": key, "status": "deleted"}

        @mcp.tool()
        async def state_list(
            prefix: str | None = None, keys_only: bool = True
        ) -> list[str] | list[dict]:
            """List keys in the state store, optionally filtered by prefix.

            Args:
                prefix: If given, only keys starting with this string are returned.
                keys_only: If True (default), return list of key strings.
                    If False, return list of {"key": ..., "value": ...} dicts.
            """
            return await _state_list(pool, prefix, keys_only)

        # Schedule tools
        @mcp.tool()
        async def schedule_list() -> list[dict]:
            """List all scheduled tasks."""
            tasks = await _schedule_list(pool)
            for t in tasks:
                t["id"] = str(t["id"])
            return tasks

        @mcp.tool()
        async def schedule_create(name: str, cron: str, prompt: str) -> dict:
            """Create a new runtime scheduled task."""
            task_id = await _schedule_create(pool, name, cron, prompt)
            return {"id": str(task_id), "status": "created"}

        @mcp.tool()
        async def schedule_update(task_id: str, **fields) -> dict:
            """Update a scheduled task."""
            await _schedule_update(pool, uuid.UUID(task_id), **fields)
            return {"id": task_id, "status": "updated"}

        @mcp.tool()
        async def schedule_delete(task_id: str) -> dict:
            """Delete a runtime scheduled task."""
            await _schedule_delete(pool, uuid.UUID(task_id))
            return {"id": task_id, "status": "deleted"}

        # Session tools
        @mcp.tool()
        async def sessions_list(limit: int = 20, offset: int = 0) -> list[dict]:
            """List sessions ordered by most recent first."""
            sessions = await _sessions_list(pool, limit, offset)
            for s in sessions:
                s["id"] = str(s["id"])
            return sessions

        @mcp.tool()
        async def sessions_get(session_id: str) -> dict | None:
            """Get a session by ID."""
            session = await _sessions_get(pool, uuid.UUID(session_id))
            if session:
                session["id"] = str(session["id"])
            return session

    async def _register_module_tools(self) -> None:
        """Register MCP tools from all loaded modules."""
        for mod in self._modules:
            mod_config = self.config.modules.get(mod.name, {})
            await mod.register_tools(self.mcp, mod_config, self.db)

    async def shutdown(self) -> None:
        """Graceful shutdown.

        1. Stop accepting new MCP connections
        2. Drain in-flight CC sessions (up to configurable timeout)
        3. Module on_shutdown in reverse topological order
        4. Close DB pool
        """
        logger.info(
            "Shutting down butler: %s",
            self.config.name if self.config else "unknown",
        )

        # 1. Stop accepting new MCP connections
        self._accepting_connections = False

        # 2. Drain in-flight CC sessions
        if self.spawner is not None:
            self.spawner.stop_accepting()
            timeout = self.config.shutdown_timeout_s if self.config else 30.0
            await self.spawner.drain(timeout=timeout)

        # 3. Module shutdown in reverse topological order
        for mod in reversed(self._modules):
            try:
                await mod.on_shutdown()
            except Exception:
                logger.exception("Error during shutdown of module: %s", mod.name)

        # 4. Close DB pool
        if self.db:
            await self.db.close()

        logger.info("Butler shutdown complete")
