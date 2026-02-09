"""CC Spawner — invokes ephemeral Claude Code instances for a butler.

The spawner is responsible for:
1. Generating a locked-down MCP config pointing exclusively at this butler
2. Invoking Claude Code via the SDK with that config
3. Passing only declared credentials to the CC environment
4. Reading the butler's CLAUDE.md as system prompt
5. Enforcing serial dispatch (one CC instance at a time per butler)
6. Logging sessions before and after invocation
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import asyncpg
from claude_code_sdk import ClaudeCodeOptions, ResultMessage, ToolUseBlock, query
from claude_code_sdk.types import McpSSEServerConfig

from butlers.config import ButlerConfig
from butlers.core.sessions import session_complete, session_create
from butlers.core.telemetry import get_traceparent_env

logger = logging.getLogger(__name__)


@dataclass
class SpawnerResult:
    """Result of a Claude Code spawner invocation."""

    result: str | None = None
    tool_calls: list[dict] = field(default_factory=list)
    error: str | None = None
    duration_ms: int = 0


def _build_mcp_config(butler_name: str, port: int) -> dict[str, Any]:
    """Build a locked-down MCP config dict with a single SSE endpoint.

    The config restricts the CC instance to communicate exclusively with
    the butler's own MCP server.
    """
    return {
        "mcpServers": {
            butler_name: {
                "url": f"http://localhost:{port}/sse",
            }
        }
    }


def _write_mcp_config(butler_name: str, port: int) -> Path:
    """Create a unique temp dir and write the MCP config JSON to it.

    Returns the path to the temp directory (caller is responsible for cleanup).
    """
    temp_dir = Path(tempfile.mkdtemp(prefix=f"butler_{butler_name}_{uuid.uuid4().hex[:8]}_"))
    config = _build_mcp_config(butler_name, port)
    mcp_json_path = temp_dir / "mcp.json"
    mcp_json_path.write_text(json.dumps(config, indent=2))
    return temp_dir


def _cleanup_temp_dir(temp_dir: Path) -> None:
    """Remove the temp directory and all its contents."""
    try:
        shutil.rmtree(temp_dir)
    except OSError:
        logger.warning("Failed to clean up temp dir: %s", temp_dir, exc_info=True)


def _read_system_prompt(config_dir: Path, butler_name: str) -> str:
    """Read CLAUDE.md from the butler's config dir.

    Returns the file contents, or a default prompt if the file is missing or empty.
    """
    default_prompt = f"You are {butler_name}, a butler AI assistant."
    claude_md = config_dir / "CLAUDE.md"

    if not claude_md.exists():
        return default_prompt

    content = claude_md.read_text().strip()
    if not content:
        return default_prompt

    return content


def _build_env(
    config: ButlerConfig,
    module_credentials_env: dict[str, list[str]] | None = None,
) -> dict[str, str]:
    """Build an explicit env dict for the CC instance.

    Only declared variables are included — no undeclared env vars leak through.
    Always includes ANTHROPIC_API_KEY, plus butler-level required/optional
    vars and module credential vars.
    """
    env: dict[str, str] = {}

    # Always include ANTHROPIC_API_KEY
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if api_key:
        env["ANTHROPIC_API_KEY"] = api_key

    # Butler-level required + optional env vars
    for var in config.env_required + config.env_optional:
        value = os.environ.get(var)
        if value is not None:
            env[var] = value

    # Module credentials
    if module_credentials_env:
        for _module_name, cred_vars in module_credentials_env.items():
            for var in cred_vars:
                value = os.environ.get(var)
                if value is not None:
                    env[var] = value

    # Include traceparent for distributed tracing
    env.update(get_traceparent_env())

    return env


class CCSpawner:
    """Core component that invokes ephemeral Claude Code instances for a butler.

    Each butler has exactly one CCSpawner. An asyncio.Lock ensures serial
    dispatch — only one CC instance runs at a time per butler.

    Parameters
    ----------
    config:
        The butler's parsed ButlerConfig.
    config_dir:
        Path to the butler's config directory (containing CLAUDE.md, etc.).
    pool:
        asyncpg connection pool for session logging.
    module_credentials_env:
        Dict mapping module name to list of env var names needed by that module.
    sdk_query:
        Callable to use for the actual SDK invocation. Defaults to
        ``claude_code_sdk.query``. Override in tests to inject a mock.
    """

    def __init__(
        self,
        config: ButlerConfig,
        config_dir: Path,
        pool: asyncpg.Pool | None = None,
        module_credentials_env: dict[str, list[str]] | None = None,
        sdk_query: Any = None,
    ) -> None:
        self._config = config
        self._config_dir = config_dir
        self._pool = pool
        self._module_credentials_env = module_credentials_env
        self._sdk_query = sdk_query or query
        self._lock = asyncio.Lock()

    async def trigger(
        self,
        prompt: str,
        trigger_source: str,
    ) -> SpawnerResult:
        """Spawn an ephemeral Claude Code instance.

        Acquires a per-butler lock to ensure serial dispatch, generates the
        MCP config, invokes CC via the SDK, and logs the session.

        Parameters
        ----------
        prompt:
            The prompt to send to the CC instance.
        trigger_source:
            What caused this invocation (schedule:<task-name>, trigger, tick, external).

        Returns
        -------
        SpawnerResult
            The result of the CC invocation.
        """
        async with self._lock:
            return await self._run(prompt, trigger_source)

    async def _run(
        self,
        prompt: str,
        trigger_source: str,
    ) -> SpawnerResult:
        """Internal: run the CC invocation (called under lock)."""
        temp_dir: Path | None = None
        session_id: uuid.UUID | None = None

        # Create session record
        if self._pool is not None:
            session_id = await session_create(self._pool, prompt, trigger_source)

        t0 = time.monotonic()

        try:
            # Generate MCP config in temp dir
            temp_dir = _write_mcp_config(self._config.name, self._config.port)

            # Read system prompt
            system_prompt = _read_system_prompt(self._config_dir, self._config.name)

            # Build credential env
            env = _build_env(self._config, self._module_credentials_env)

            # Build MCP server config for SDK
            mcp_servers: dict[str, McpSSEServerConfig] = {
                self._config.name: McpSSEServerConfig(
                    type="sse",
                    url=f"http://localhost:{self._config.port}/sse",
                ),
            }

            # Configure SDK options
            options = ClaudeCodeOptions(
                system_prompt=system_prompt,
                mcp_servers=mcp_servers,
                permission_mode="bypassPermissions",
                env=env,
            )

            # Invoke CC SDK
            result_text = ""
            tool_calls: list[dict] = []

            async for message in self._sdk_query(prompt=prompt, options=options):
                if isinstance(message, ResultMessage):
                    result_text = message.result or ""
                elif hasattr(message, "content"):
                    for block in getattr(message, "content", []):
                        if isinstance(block, ToolUseBlock):
                            tool_calls.append(
                                {
                                    "id": block.id,
                                    "name": block.name,
                                    "input": block.input,
                                }
                            )

            duration_ms = int((time.monotonic() - t0) * 1000)

            spawner_result = SpawnerResult(
                result=result_text,
                tool_calls=tool_calls,
                duration_ms=duration_ms,
            )

            # Log session completion
            if self._pool is not None and session_id is not None:
                await session_complete(
                    self._pool,
                    session_id,
                    result_text,
                    tool_calls,
                    duration_ms,
                )

            return spawner_result

        except Exception as exc:
            duration_ms = int((time.monotonic() - t0) * 1000)
            error_msg = f"{type(exc).__name__}: {exc}"
            logger.error("CC invocation failed: %s", error_msg, exc_info=True)

            spawner_result = SpawnerResult(
                error=error_msg,
                duration_ms=duration_ms,
            )

            # Log failed session
            if self._pool is not None and session_id is not None:
                await session_complete(
                    self._pool,
                    session_id,
                    error_msg,
                    [],
                    duration_ms,
                )

            return spawner_result

        finally:
            # Always clean up temp dir
            if temp_dir is not None:
                _cleanup_temp_dir(temp_dir)
