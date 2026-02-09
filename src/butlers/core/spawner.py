"""CC Spawner — invokes ephemeral Claude Code instances for a butler.

The spawner is responsible for:
1. Generating a locked-down MCP config pointing exclusively at this butler
2. Invoking a runtime adapter (e.g. Claude Code) with that config
3. Passing only declared credentials to the runtime environment
4. Reading the butler's system prompt via the adapter
5. Enforcing serial dispatch (one instance at a time per butler)
6. Logging sessions before and after invocation
"""

from __future__ import annotations

import asyncio
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
from opentelemetry import trace

from butlers.config import ButlerConfig
from butlers.core.runtimes.base import RuntimeAdapter
from butlers.core.sessions import session_complete, session_create
from butlers.core.telemetry import get_traceparent_env

logger = logging.getLogger(__name__)


@dataclass
class SpawnerResult:
    """Result of a Claude Code spawner invocation."""

    output: str | None = None
    success: bool = False
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
    import json

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
    runtime:
        A RuntimeAdapter instance to use for invocation. If provided, sdk_query
        is ignored.
    sdk_query:
        DEPRECATED — Callable to use for the actual SDK invocation. Prefer
        passing a RuntimeAdapter via ``runtime``. When neither ``runtime``
        nor ``sdk_query`` is provided, a default ClaudeCodeAdapter is created.
    """

    def __init__(
        self,
        config: ButlerConfig,
        config_dir: Path,
        pool: asyncpg.Pool | None = None,
        module_credentials_env: dict[str, list[str]] | None = None,
        runtime: RuntimeAdapter | None = None,
        sdk_query: Any = None,
    ) -> None:
        self._config = config
        self._config_dir = config_dir
        self._pool = pool
        self._module_credentials_env = module_credentials_env
        self._lock = asyncio.Lock()
        self._accepting = True
        self._in_flight: set[asyncio.Task] = set()
        self._in_flight_event = asyncio.Event()
        self._in_flight_event.set()  # Initially no in-flight sessions

        if runtime is not None:
            self._runtime = runtime
        elif sdk_query is not None:
            # Legacy path: wrap sdk_query in a ClaudeCodeAdapter
            from butlers.core.runtimes.claude_code import ClaudeCodeAdapter

            self._runtime = ClaudeCodeAdapter(sdk_query=sdk_query)
        else:
            # Default: create a ClaudeCodeAdapter with the real SDK query
            from butlers.core.runtimes.claude_code import ClaudeCodeAdapter

            self._runtime = ClaudeCodeAdapter()

    async def trigger(
        self,
        prompt: str,
        trigger_source: str,
context: str | None = None,
        max_turns: int = 20,
    ) -> SpawnerResult:
        """Spawn an ephemeral Claude Code instance.

        Acquires a per-butler lock to ensure serial dispatch, generates the
        MCP config, invokes CC via the runtime adapter, and logs the session.

        Parameters
        ----------
        prompt:
            The prompt to send to the CC instance.
        trigger_source:
What caused this invocation (schedule, trigger_tool, tick, heartbeat).
        context:
            Optional text to prepend to the prompt. If provided and non-empty,
            this will be prepended to the prompt with two newlines separating them.
        max_turns:
            Maximum number of turns for the CC session. Defaults to 20.

        Returns
        -------
        SpawnerResult
            The result of the CC invocation.

        Raises
        ------
        RuntimeError
            If the spawner has been stopped and is no longer accepting triggers.
        """
        if not self._accepting:
            raise RuntimeError("Spawner is shutting down; not accepting new triggers")

        self._in_flight_event.clear()
        task = asyncio.current_task()
        if task is not None:
            self._in_flight.add(task)
        try:
            async with self._lock:
                return await self._run(prompt, trigger_source, context, max_turns)
        finally:
            if task is not None:
                self._in_flight.discard(task)
            if not self._in_flight:
                self._in_flight_event.set()

    def stop_accepting(self) -> None:
        """Stop accepting new trigger requests.

        Existing in-flight sessions continue until they complete or are
        cancelled via :meth:`drain`.
        """
        self._accepting = False
        logger.info("Spawner stopped accepting new triggers")

    async def drain(self, timeout: float = 30.0) -> None:
        """Wait for in-flight CC sessions to complete, up to *timeout* seconds.

        If sessions are still running after the timeout, they are cancelled.

        Parameters
        ----------
        timeout:
            Maximum seconds to wait for in-flight sessions to finish.
        """
        if not self._in_flight:
            logger.info("No in-flight sessions to drain")
            return

        logger.info(
            "Draining %d in-flight session(s) (timeout=%.1fs)",
            len(self._in_flight),
            timeout,
        )
        try:
            await asyncio.wait_for(self._in_flight_event.wait(), timeout=timeout)
            logger.info("All in-flight sessions drained successfully")
        except TimeoutError:
            remaining = len(self._in_flight)
            logger.warning(
                "Drain timeout after %.1fs; cancelling %d in-flight session(s)",
                timeout,
                remaining,
            )
            for task in list(self._in_flight):
                task.cancel()
            # Give cancelled tasks a moment to clean up
            if self._in_flight:
                await asyncio.sleep(0.1)
            self._in_flight.clear()
            self._in_flight_event.set()

    @property
    def in_flight_count(self) -> int:
        """Return the number of currently in-flight CC sessions."""
        return len(self._in_flight)

    async def _run(
        self,
        prompt: str,
        trigger_source: str,
context: str | None = None,
        max_turns: int = 20,
    ) -> SpawnerResult:
        """Internal: run the CC invocation (called under lock)."""
        temp_dir: Path | None = None
        session_id: uuid.UUID | None = None

        # Prepend context to prompt if provided
        final_prompt = prompt
        if context:
            final_prompt = f"{context}\n\n{prompt}"

        # Get tracer and start butler.cc_session span
        tracer = trace.get_tracer("butlers")
        span = tracer.start_span("butler.cc_session")
        span.set_attribute("butler.name", self._config.name)
        span.set_attribute("prompt_length", len(final_prompt))

        # Attach span to context
        token = trace.context_api.attach(trace.set_span_in_context(span))

        try:
            # Extract trace_id from active span
            trace_id: str | None = None
            if span.is_recording():
                trace_id = format(span.get_span_context().trace_id, "032x")

            # Create session record with trace_id
            if self._pool is not None:
                session_id = await session_create(self._pool, final_prompt, trigger_source, trace_id)
                # Set session_id on span
                span.set_attribute("session_id", str(session_id))

            t0 = time.monotonic()

            # Generate MCP config in temp dir
            temp_dir = _write_mcp_config(self._config.name, self._config.port)

            # Read system prompt
            system_prompt = _read_system_prompt(self._config_dir, self._config.name)

            # Build credential env
            env = _build_env(self._config, self._module_credentials_env)

            # Build MCP server config for the adapter
            mcp_servers: dict[str, Any] = {
                self._config.name: {
                    "url": f"http://localhost:{self._config.port}/sse",
                },
            }

            # Invoke via runtime adapter
            result_text, tool_calls = await self._runtime.invoke(
                prompt=prompt,
                system_prompt=system_prompt,
                mcp_servers=mcp_servers,
                env=env,
                max_turns=max_turns,
                cwd=str(self._config_dir),
            )


            duration_ms = int((time.monotonic() - t0) * 1000)

            spawner_result = SpawnerResult(
                output=result_text,
                success=True,
                tool_calls=tool_calls,
                duration_ms=duration_ms,
            )

            # Log session completion
            if self._pool is not None and session_id is not None:
                await session_complete(
                    self._pool,
                    session_id,
                    output=result_text,
                    tool_calls=tool_calls,
                    duration_ms=duration_ms,
                    success=True,
                )

            return spawner_result

        except Exception as exc:
            duration_ms = int((time.monotonic() - t0) * 1000)
            error_msg = f"{type(exc).__name__}: {exc}"
            logger.error("CC invocation failed: %s", error_msg, exc_info=True)

            # Record exception on span
            span.set_status(trace.StatusCode.ERROR, str(exc))
            span.record_exception(exc)

            spawner_result = SpawnerResult(
                error=error_msg,
                success=False,
                duration_ms=duration_ms,
            )

            # Log failed session
            if self._pool is not None and session_id is not None:
                await session_complete(
                    self._pool,
                    session_id,
                    output=None,
                    tool_calls=[],
                    duration_ms=duration_ms,
                    success=False,
                    error=error_msg,
                )

            return spawner_result

        finally:
            # Always clean up temp dir
            if temp_dir is not None:
                _cleanup_temp_dir(temp_dir)

            # End span and detach context
            span.end()
            trace.context_api.detach(token)
