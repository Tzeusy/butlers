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

Graceful shutdown reverses module shutdown in reverse topological order,
then closes DB pool.
"""

from __future__ import annotations

import logging
import time
import uuid
from pathlib import Path
from typing import Any

from fastmcp import FastMCP
from pydantic import ConfigDict, ValidationError

from butlers.config import ButlerConfig, load_config
from butlers.core.scheduler import (
    schedule_create,
    schedule_delete,
    schedule_list,
    schedule_update,
    sync_schedules,
    tick,
)
from butlers.core.sessions import sessions_get, sessions_list
from butlers.core.spawner import CCSpawner
from butlers.core.state import state_delete, state_get, state_list, state_set
from butlers.core.telemetry import init_telemetry
from butlers.credentials import validate_credentials
from butlers.db import Database
from butlers.migrations import run_migrations
from butlers.modules.base import Module
from butlers.modules.registry import ModuleRegistry

logger = logging.getLogger(__name__)


class ModuleConfigError(Exception):
    """Raised when a module's configuration fails Pydantic validation."""


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
        self._module_configs: dict[str, Any] = {}
        self._started_at: float | None = None

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

        # 8. Validate module configs and call on_startup (topological order)
        self._module_configs = self._validate_module_configs()
        for mod in self._modules:
            validated_config = self._module_configs.get(mod.name)
            await mod.on_startup(validated_config, self.db)

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

        # Record startup time
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
        async def trigger(prompt: str) -> dict:
            """Trigger the CC spawner with a prompt."""
            result = await spawner.trigger(prompt=prompt, trigger_source="trigger_tool")
            return {
                "result": result.result,
                "error": result.error,
                "duration_ms": result.duration_ms,
            }

        @mcp.tool()
        async def tick_now() -> dict:
            """Evaluate due scheduled tasks and dispatch them now."""
            count = await tick(pool, spawner.trigger)
            return {"dispatched": count}

        # State tools
        @mcp.tool()
        async def get_state(key: str) -> dict:
            """Get a value from the state store."""
            value = await state_get(pool, key)
            return {"key": key, "value": value}

        @mcp.tool()
        async def set_state(key: str, value: Any) -> dict:
            """Set a value in the state store."""
            await state_set(pool, key, value)
            return {"key": key, "status": "ok"}

        @mcp.tool()
        async def delete_state(key: str) -> dict:
            """Delete a key from the state store."""
            await state_delete(pool, key)
            return {"key": key, "status": "deleted"}

        @mcp.tool()
        async def list_state(prefix: str | None = None) -> list[dict]:
            """List all entries in the state store, optionally filtered by prefix."""
            return await state_list(pool, prefix)

        # Schedule tools
        @mcp.tool()
        async def list_schedules() -> list[dict]:
            """List all scheduled tasks."""
            tasks = await schedule_list(pool)
            for t in tasks:
                t["id"] = str(t["id"])
            return tasks

        @mcp.tool()
        async def create_schedule(name: str, cron: str, prompt: str) -> dict:
            """Create a new runtime scheduled task."""
            task_id = await schedule_create(pool, name, cron, prompt)
            return {"id": str(task_id), "status": "created"}

        @mcp.tool()
        async def update_schedule(task_id: str, **fields) -> dict:
            """Update a scheduled task."""
            await schedule_update(pool, uuid.UUID(task_id), **fields)
            return {"id": task_id, "status": "updated"}

        @mcp.tool()
        async def delete_schedule(task_id: str) -> dict:
            """Delete a runtime scheduled task."""
            await schedule_delete(pool, uuid.UUID(task_id))
            return {"id": task_id, "status": "deleted"}

        # Session tools
        @mcp.tool()
        async def list_sessions(limit: int = 20, offset: int = 0) -> list[dict]:
            """List sessions ordered by most recent first."""
            sessions = await sessions_list(pool, limit, offset)
            for s in sessions:
                s["id"] = str(s["id"])
            return sessions

        @mcp.tool()
        async def get_session(session_id: str) -> dict | None:
            """Get a session by ID."""
            session = await sessions_get(pool, uuid.UUID(session_id))
            if session:
                session["id"] = str(session["id"])
            return session

    def _validate_module_configs(self) -> dict[str, Any]:
        """Validate each module's raw config dict against its config_schema.

        Returns a mapping of module name to validated Pydantic model instance.
        If a module has no config_schema (returns None), the raw dict is passed
        through for backward compatibility.

        Extra fields not declared in the schema are rejected. Missing required
        fields and type mismatches produce clear error messages.

        Raises
        ------
        ModuleConfigError
            If validation fails (missing required fields, extra unknown fields,
            or type mismatches).
        """
        validated: dict[str, Any] = {}
        for mod in self._modules:
            raw_config = self.config.modules.get(mod.name, {})
            schema = mod.config_schema
            if schema is None:
                validated[mod.name] = raw_config
                continue
            # Create a strict variant that forbids extra fields, unless the
            # schema already configures its own extra handling.
            effective_schema = schema
            current_extra = schema.model_config.get("extra")
            if current_extra is None:
                effective_schema = type(
                    f"{schema.__name__}Strict",
                    (schema,),
                    {"model_config": ConfigDict(extra="forbid")},
                )
            try:
                validated[mod.name] = effective_schema.model_validate(raw_config)
            except ValidationError as exc:
                raise ModuleConfigError(
                    f"Configuration validation failed for module '{mod.name}': {exc}"
                ) from exc
        return validated

    async def _register_module_tools(self) -> None:
        """Register MCP tools from all loaded modules."""
        for mod in self._modules:
            validated_config = self._module_configs.get(mod.name)
            await mod.register_tools(self.mcp, validated_config, self.db)

    async def shutdown(self) -> None:
        """Graceful shutdown.

        1. Module on_shutdown in reverse topological order
        2. Close DB pool
        """
        logger.info(
            "Shutting down butler: %s",
            self.config.name if self.config else "unknown",
        )

        # Module shutdown in reverse topological order
        for mod in reversed(self._modules):
            try:
                await mod.on_shutdown()
            except Exception:
                logger.exception("Error during shutdown of module: %s", mod.name)

        # Close DB pool
        if self.db:
            await self.db.close()

        logger.info("Butler shutdown complete")
