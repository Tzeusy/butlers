"""Tests for the Spawner orchestration layer (butlers-0qp.8, butlers-f3t.7).

Covers:
- MCP config generation (correct JSON structure, single endpoint)
- Temp dir cleanup (success and failure paths)
- Serial dispatch (lock prevents concurrent execution)
- Credential passthrough (only declared vars included)
- System prompt handling (present, missing, empty)
- Session logging wired correctly
- SpawnerResult construction on success and error
- Parametrized orchestration tests across all runtime adapters

Orchestration tests use a MockAdapter (runtime-agnostic). Adapter-specific
unit tests live in test_runtime_adapter.py, test_codex_adapter.py, and
test_gemini_adapter.py.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from butlers.config import ButlerConfig
from butlers.core.runtimes.base import RuntimeAdapter
from butlers.core.spawner import (
    Spawner,
    SpawnerResult,
    _build_env,
    _build_mcp_config,
    _cleanup_temp_dir,
    _read_system_prompt,
    _write_mcp_config,
)

# ---------------------------------------------------------------------------
# MockAdapter — runtime-agnostic adapter for orchestration tests
# ---------------------------------------------------------------------------


class MockAdapter(RuntimeAdapter):
    """A fully in-process mock adapter for testing Spawner orchestration.

    Does not depend on any CLI binary or SDK. Invoke behavior is controlled
    via constructor parameters:
    - result_text / tool_calls: returned on success
    - error: if set, invoke() raises RuntimeError with this message
    - delay: if > 0, invoke() sleeps for this many seconds before returning
    - capture: if True, records all invoke() calls in .calls list
    """

    def __init__(
        self,
        *,
        result_text: str | None = "",
        tool_calls: list[dict[str, Any]] | None = None,
        error: str | None = None,
        delay: float = 0,
        capture: bool = False,
    ) -> None:
        self._result_text = result_text
        self._tool_calls = tool_calls or []
        self._error = error
        self._delay = delay
        self._capture = capture
        self.calls: list[dict[str, Any]] = []
        self._call_count = 0

    @property
    def binary_name(self) -> str:
        return "mock"

    async def invoke(
        self,
        prompt: str,
        system_prompt: str,
        mcp_servers: dict[str, Any],
        env: dict[str, str],
        cwd: Path | None = None,
        timeout: int | None = None,
    ) -> tuple[str | None, list[dict[str, Any]]]:
        self._call_count += 1
        if self._capture:
            self.calls.append(
                {
                    "prompt": prompt,
                    "system_prompt": system_prompt,
                    "mcp_servers": mcp_servers,
                    "env": env,
                    "cwd": cwd,
                    "timeout": timeout,
                }
            )
        if self._delay > 0:
            await asyncio.sleep(self._delay)
        if self._error:
            raise RuntimeError(self._error)
        return self._result_text, list(self._tool_calls)

    def build_config_file(
        self,
        mcp_servers: dict[str, Any],
        tmp_dir: Path,
    ) -> Path:
        config_path = tmp_dir / "mock_config.json"
        config_path.write_text(json.dumps({"mcpServers": mcp_servers}))
        return config_path

    def parse_system_prompt_file(self, config_dir: Path) -> str:
        return ""


class SequenceMockAdapter(MockAdapter):
    """Mock adapter that returns different results on successive calls.

    Used for tests like lock-released-on-error where the first call
    fails and the second succeeds.
    """

    def __init__(
        self,
        sequence: list[dict[str, Any]],
    ) -> None:
        super().__init__()
        self._sequence = sequence
        self._call_index = 0

    async def invoke(
        self,
        prompt: str,
        system_prompt: str,
        mcp_servers: dict[str, Any],
        env: dict[str, str],
        cwd: Path | None = None,
        timeout: int | None = None,
    ) -> tuple[str | None, list[dict[str, Any]]]:
        idx = self._call_index
        self._call_index += 1
        entry = self._sequence[idx] if idx < len(self._sequence) else self._sequence[-1]
        if entry.get("delay"):
            await asyncio.sleep(entry["delay"])
        if entry.get("error"):
            raise RuntimeError(entry["error"])
        return entry.get("result_text", ""), entry.get("tool_calls", [])


class TrackingMockAdapter(MockAdapter):
    """Mock adapter that tracks start/end of each invoke for serialization tests."""

    def __init__(self) -> None:
        super().__init__()
        self.execution_log: list[tuple[str, str]] = []

    async def invoke(
        self,
        prompt: str,
        system_prompt: str,
        mcp_servers: dict[str, Any],
        env: dict[str, str],
        cwd: Path | None = None,
        timeout: int | None = None,
    ) -> tuple[str | None, list[dict[str, Any]]]:
        self.execution_log.append(("start", prompt))
        await asyncio.sleep(0.03)
        self.execution_log.append(("end", prompt))
        return f"result-{prompt}", []


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(
    name: str = "test-butler",
    port: int = 9100,
    env_required: list[str] | None = None,
    env_optional: list[str] | None = None,
) -> ButlerConfig:
    return ButlerConfig(
        name=name,
        port=port,
        env_required=env_required or [],
        env_optional=env_optional or [],
    )


# ---------------------------------------------------------------------------
# 8.1: MCP config generation
# ---------------------------------------------------------------------------


class TestMcpConfigGeneration:
    """Tests for MCP config JSON structure and temp dir management."""

    def test_build_mcp_config_structure(self):
        config = _build_mcp_config("my-butler", 9100)
        assert "mcpServers" in config
        assert len(config["mcpServers"]) == 1
        assert "my-butler" in config["mcpServers"]
        assert config["mcpServers"]["my-butler"]["url"] == "http://localhost:9100/sse"

    def test_build_mcp_config_different_port(self):
        config = _build_mcp_config("other-butler", 8888)
        assert config["mcpServers"]["other-butler"]["url"] == "http://localhost:8888/sse"

    def test_write_mcp_config_creates_temp_dir(self):
        temp_dir = _write_mcp_config("test-butler", 9100)
        try:
            assert temp_dir.exists()
            assert temp_dir.is_dir()
            assert "butler_test-butler_" in temp_dir.name

            mcp_json = temp_dir / "mcp.json"
            assert mcp_json.exists()

            data = json.loads(mcp_json.read_text())
            assert data["mcpServers"]["test-butler"]["url"] == "http://localhost:9100/sse"
        finally:
            _cleanup_temp_dir(temp_dir)

    def test_write_mcp_config_unique_dirs(self):
        """Each invocation creates a unique temp dir."""
        dirs = [_write_mcp_config("test-butler", 9100) for _ in range(3)]
        try:
            paths = {str(d) for d in dirs}
            assert len(paths) == 3, "Expected 3 unique temp directories"
        finally:
            for d in dirs:
                _cleanup_temp_dir(d)


# ---------------------------------------------------------------------------
# 8.1 continued: Temp dir cleanup
# ---------------------------------------------------------------------------


class TestTempDirCleanup:
    """Temp dir is cleaned up after session on both success and failure."""

    async def test_cleanup_on_success(self, tmp_path: Path):
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config = _make_config()

        adapter = MockAdapter(result_text="")
        spawner = Spawner(
            config=config,
            config_dir=config_dir,
            runtime=adapter,
        )

        with patch("butlers.core.spawner._write_mcp_config") as mock_write:
            real_dir = _write_mcp_config("test-butler", 9100)
            mock_write.return_value = real_dir

            with patch("butlers.core.spawner._cleanup_temp_dir") as mock_cleanup:
                await spawner.trigger("test", "tick")
                mock_cleanup.assert_called_once_with(real_dir)

        # Manual cleanup if still exists
        if real_dir.exists():
            _cleanup_temp_dir(real_dir)

    async def test_cleanup_on_error(self, tmp_path: Path):
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config = _make_config()

        adapter = MockAdapter(error="adapter invocation failed")
        spawner = Spawner(
            config=config,
            config_dir=config_dir,
            runtime=adapter,
        )

        with patch("butlers.core.spawner._write_mcp_config") as mock_write:
            real_dir = _write_mcp_config("test-butler", 9100)
            mock_write.return_value = real_dir

            with patch("butlers.core.spawner._cleanup_temp_dir") as mock_cleanup:
                result = await spawner.trigger("test", "tick")
                assert result.error is not None
                mock_cleanup.assert_called_once_with(real_dir)

        if real_dir.exists():
            _cleanup_temp_dir(real_dir)

    async def test_actual_cleanup_removes_dir(self):
        temp_dir = _write_mcp_config("cleanup-test", 9100)
        assert temp_dir.exists()
        _cleanup_temp_dir(temp_dir)
        assert not temp_dir.exists()


# ---------------------------------------------------------------------------
# 8.2: Spawner result and invocation (runtime-agnostic)
# ---------------------------------------------------------------------------


class TestSpawnerResult:
    """SpawnerResult dataclass behavior."""

    def test_default_values(self):
        r = SpawnerResult()
        assert r.result is None
        assert r.tool_calls == []
        assert r.error is None
        assert r.duration_ms == 0

    def test_success_result(self):
        r = SpawnerResult(result="output", tool_calls=[{"name": "t"}], duration_ms=42)
        assert r.result == "output"
        assert len(r.tool_calls) == 1
        assert r.error is None

    def test_error_result(self):
        r = SpawnerResult(error="something broke", duration_ms=10)
        assert r.result is None
        assert r.error == "something broke"


class TestSpawnerInvocation:
    """Tests for runtime invocation via Spawner.trigger() with MockAdapter."""

    async def test_success_with_result(self, tmp_path: Path):
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config = _make_config()

        adapter = MockAdapter(result_text="Hello from mock!")
        spawner = Spawner(
            config=config,
            config_dir=config_dir,
            runtime=adapter,
        )

        result = await spawner.trigger("hello", "tick")
        assert result.result == "Hello from mock!"
        assert result.error is None
        assert result.duration_ms >= 0

    async def test_tool_calls_captured(self, tmp_path: Path):
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config = _make_config()

        adapter = MockAdapter(
            result_text="Done with tools",
            tool_calls=[{"id": "tool_1", "name": "state_get", "input": {"key": "foo"}}],
        )
        spawner = Spawner(
            config=config,
            config_dir=config_dir,
            runtime=adapter,
        )

        result = await spawner.trigger("use tools", "trigger_tool")
        assert result.result == "Done with tools"
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0]["name"] == "state_get"
        assert result.tool_calls[0]["input"] == {"key": "foo"}

    async def test_error_wrapped_in_result(self, tmp_path: Path):
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config = _make_config()

        adapter = MockAdapter(error="adapter connection failed")
        spawner = Spawner(
            config=config,
            config_dir=config_dir,
            runtime=adapter,
        )

        result = await spawner.trigger("fail", "tick")
        assert result.error is not None
        assert "RuntimeError" in result.error
        assert "adapter connection failed" in result.error
        assert result.result is None
        assert result.duration_ms >= 0

    async def test_duration_measured(self, tmp_path: Path):
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config = _make_config()

        adapter = MockAdapter(result_text="slow result", delay=0.05)
        spawner = Spawner(
            config=config,
            config_dir=config_dir,
            runtime=adapter,
        )

        result = await spawner.trigger("slow", "tick")
        assert result.duration_ms >= 40  # at least ~50ms sleep


# ---------------------------------------------------------------------------
# 8.3: Credential passthrough
# ---------------------------------------------------------------------------


class TestCredentialPassthrough:
    """Only declared env vars are passed to the runtime instance."""

    def test_anthropic_key_always_included(self):
        config = _make_config()
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-test-123"}, clear=False):
            env = _build_env(config)
            assert env["ANTHROPIC_API_KEY"] == "sk-test-123"

    def test_required_env_vars_included(self):
        config = _make_config(env_required=["MY_SECRET"])
        with patch.dict(
            os.environ,
            {"ANTHROPIC_API_KEY": "sk-key", "MY_SECRET": "s3cret"},
            clear=False,
        ):
            env = _build_env(config)
            assert env["MY_SECRET"] == "s3cret"

    def test_optional_env_vars_included_when_present(self):
        config = _make_config(env_optional=["OPT_VAR"])
        with patch.dict(
            os.environ,
            {"ANTHROPIC_API_KEY": "sk-key", "OPT_VAR": "opt-val"},
            clear=False,
        ):
            env = _build_env(config)
            assert env["OPT_VAR"] == "opt-val"

    def test_optional_env_vars_excluded_when_absent(self):
        config = _make_config(env_optional=["MISSING_OPT"])
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-key"}, clear=False):
            # Ensure the var is not set
            os.environ.pop("MISSING_OPT", None)
            env = _build_env(config)
            assert "MISSING_OPT" not in env

    def test_module_credentials_included(self):
        config = _make_config()
        module_creds = {"email": ["SMTP_PASSWORD", "IMAP_TOKEN"]}
        with patch.dict(
            os.environ,
            {
                "ANTHROPIC_API_KEY": "sk-key",
                "SMTP_PASSWORD": "pw123",
                "IMAP_TOKEN": "tok456",
            },
            clear=False,
        ):
            env = _build_env(config, module_credentials_env=module_creds)
            assert env["SMTP_PASSWORD"] == "pw123"
            assert env["IMAP_TOKEN"] == "tok456"

    def test_undeclared_vars_not_leaked(self):
        config = _make_config(env_required=["DECLARED"])
        with patch.dict(
            os.environ,
            {
                "ANTHROPIC_API_KEY": "sk-key",
                "DECLARED": "yes",
                "UNDECLARED_SECRET": "should-not-leak",
            },
            clear=False,
        ):
            env = _build_env(config)
            assert "UNDECLARED_SECRET" not in env
            assert "DECLARED" in env

    def test_anthropic_key_missing_not_included(self):
        config = _make_config()
        env_copy = os.environ.copy()
        env_copy.pop("ANTHROPIC_API_KEY", None)
        with patch.dict(os.environ, env_copy, clear=True):
            env = _build_env(config)
            assert "ANTHROPIC_API_KEY" not in env

    async def test_env_passed_to_adapter(self, tmp_path: Path):
        """Verify the env dict is passed through to the adapter."""
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config = _make_config(env_required=["BUTLER_SECRET"])

        adapter = MockAdapter(result_text="", capture=True)
        spawner = Spawner(
            config=config,
            config_dir=config_dir,
            runtime=adapter,
        )

        with patch.dict(
            os.environ,
            {"ANTHROPIC_API_KEY": "sk-key", "BUTLER_SECRET": "s3cret"},
            clear=False,
        ):
            await spawner.trigger("test env", "tick")

        assert len(adapter.calls) == 1
        passed_env = adapter.calls[0]["env"]
        assert passed_env["ANTHROPIC_API_KEY"] == "sk-key"
        assert passed_env["BUTLER_SECRET"] == "s3cret"


# ---------------------------------------------------------------------------
# 8.4: System prompt reading
# ---------------------------------------------------------------------------


class TestSystemPrompt:
    """System prompt reading for spawner."""

    def test_reads_claude_md(self, tmp_path: Path):
        claude_md = tmp_path / "CLAUDE.md"
        claude_md.write_text("You are a specialized butler for email management.")
        prompt = _read_system_prompt(tmp_path, "email-butler")
        assert prompt == "You are a specialized butler for email management."

    def test_missing_claude_md_uses_default(self, tmp_path: Path):
        prompt = _read_system_prompt(tmp_path, "my-butler")
        assert prompt == "You are my-butler, a butler AI assistant."

    def test_empty_claude_md_uses_default(self, tmp_path: Path):
        claude_md = tmp_path / "CLAUDE.md"
        claude_md.write_text("")
        prompt = _read_system_prompt(tmp_path, "my-butler")
        assert prompt == "You are my-butler, a butler AI assistant."

    def test_whitespace_only_claude_md_uses_default(self, tmp_path: Path):
        claude_md = tmp_path / "CLAUDE.md"
        claude_md.write_text("   \n  \n  ")
        prompt = _read_system_prompt(tmp_path, "my-butler")
        assert prompt == "You are my-butler, a butler AI assistant."

    async def test_system_prompt_passed_to_adapter(self, tmp_path: Path):
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        claude_md = config_dir / "CLAUDE.md"
        claude_md.write_text("Custom system prompt for testing.")
        config = _make_config()

        adapter = MockAdapter(result_text="", capture=True)
        spawner = Spawner(
            config=config,
            config_dir=config_dir,
            runtime=adapter,
        )

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-key"}, clear=False):
            await spawner.trigger("test", "tick")

        assert adapter.calls[0]["system_prompt"] == "Custom system prompt for testing."


# ---------------------------------------------------------------------------
# 8.5: Serial dispatch with asyncio lock
# ---------------------------------------------------------------------------


class TestSerialDispatch:
    """asyncio.Lock ensures only one runtime instance runs at a time."""

    async def test_concurrent_triggers_are_serialized(self, tmp_path: Path):
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config = _make_config()

        adapter = TrackingMockAdapter()
        spawner = Spawner(
            config=config,
            config_dir=config_dir,
            runtime=adapter,
        )

        # Launch 3 concurrent triggers
        results = await asyncio.gather(
            spawner.trigger("A", "tick"),
            spawner.trigger("B", "tick"),
            spawner.trigger("C", "tick"),
        )

        # All should succeed
        assert all(r.error is None for r in results)

        # Verify serial execution: each "start" must be followed by its "end"
        # before the next "start"
        execution_log = adapter.execution_log
        for i in range(0, len(execution_log), 2):
            assert execution_log[i][0] == "start"
            assert execution_log[i + 1][0] == "end"
            assert execution_log[i][1] == execution_log[i + 1][1]

    async def test_lock_released_on_error(self, tmp_path: Path):
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config = _make_config()

        adapter = SequenceMockAdapter(
            sequence=[
                {"error": "First call fails"},
                {"result_text": "second call works", "tool_calls": []},
            ]
        )
        spawner = Spawner(
            config=config,
            config_dir=config_dir,
            runtime=adapter,
        )

        result1 = await spawner.trigger("first", "tick")
        assert result1.error is not None

        # Lock should be released — second call should work
        result2 = await spawner.trigger("second", "tick")
        assert result2.error is None
        assert result2.result == "second call works"


# ---------------------------------------------------------------------------
# 8.6: Session logging
# ---------------------------------------------------------------------------


class TestSessionLogging:
    """Session logging is wired to session_create and session_complete."""

    async def test_session_created_and_completed_on_success(self, tmp_path: Path):
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config = _make_config()

        mock_pool = AsyncMock()
        mock_pool.fetchval = AsyncMock(return_value="00000000-0000-0000-0000-000000000001")

        with (
            patch("butlers.core.spawner.session_create", new_callable=AsyncMock) as mock_create,
            patch("butlers.core.spawner.session_complete", new_callable=AsyncMock) as mock_complete,
        ):
            import uuid

            fake_session_id = uuid.UUID("00000000-0000-0000-0000-000000000001")
            mock_create.return_value = fake_session_id

            adapter = MockAdapter(result_text="Hello from mock!")
            spawner = Spawner(
                config=config,
                config_dir=config_dir,
                pool=mock_pool,
                runtime=adapter,
            )

            await spawner.trigger("log me", "schedule")

            # session_create called with correct args
            mock_create.assert_called_once_with(mock_pool, "log me", "schedule")

            # session_complete called with result data
            mock_complete.assert_called_once()
            call_args = mock_complete.call_args
            assert call_args[0][0] is mock_pool
            assert call_args[0][1] == fake_session_id
            assert call_args[0][2] == "Hello from mock!"  # result text
            assert isinstance(call_args[0][3], list)  # tool_calls
            assert call_args[0][4] >= 0  # duration_ms

    async def test_session_completed_on_error(self, tmp_path: Path):
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config = _make_config()

        mock_pool = AsyncMock()

        with (
            patch("butlers.core.spawner.session_create", new_callable=AsyncMock) as mock_create,
            patch("butlers.core.spawner.session_complete", new_callable=AsyncMock) as mock_complete,
        ):
            import uuid

            fake_session_id = uuid.UUID("00000000-0000-0000-0000-000000000002")
            mock_create.return_value = fake_session_id

            adapter = MockAdapter(error="adapter connection failed")
            spawner = Spawner(
                config=config,
                config_dir=config_dir,
                pool=mock_pool,
                runtime=adapter,
            )

            result = await spawner.trigger("fail", "tick")
            assert result.error is not None

            # session_complete called with error info
            mock_complete.assert_called_once()
            call_args = mock_complete.call_args
            assert call_args[0][0] is mock_pool
            assert call_args[0][1] == fake_session_id
            assert "RuntimeError" in call_args[0][2]  # error message as result
            assert call_args[0][3] == []  # empty tool_calls on error

    async def test_no_session_logging_without_pool(self, tmp_path: Path):
        """When pool is None, no session logging occurs (no errors either)."""
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config = _make_config()

        adapter = MockAdapter(result_text="Hello from mock!")
        spawner = Spawner(
            config=config,
            config_dir=config_dir,
            pool=None,
            runtime=adapter,
        )

        # Should not raise even without a pool
        result = await spawner.trigger("no pool", "tick")
        assert result.result == "Hello from mock!"


# ---------------------------------------------------------------------------
# Integration-style test: full flow with MockAdapter
# ---------------------------------------------------------------------------


class TestFullFlow:
    """End-to-end spawner flow with MockAdapter."""

    async def test_full_trigger_flow(self, tmp_path: Path):
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        claude_md = config_dir / "CLAUDE.md"
        claude_md.write_text("You are the test butler.")

        config = _make_config(
            name="flow-butler",
            port=9200,
            env_required=["CUSTOM_VAR"],
        )

        adapter = MockAdapter(
            result_text="All done!",
            tool_calls=[{"id": "t1", "name": "state_set", "input": {"k": "v"}}],
            capture=True,
        )
        spawner = Spawner(
            config=config,
            config_dir=config_dir,
            runtime=adapter,
        )

        with patch.dict(
            os.environ,
            {"ANTHROPIC_API_KEY": "sk-flow", "CUSTOM_VAR": "cv"},
            clear=False,
        ):
            result = await spawner.trigger("do the thing", "schedule")

        assert result.result == "All done!"
        assert result.error is None
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0]["name"] == "state_set"
        assert result.duration_ms >= 0

        # Verify adapter received correct args
        assert len(adapter.calls) == 1
        call = adapter.calls[0]
        assert call["system_prompt"] == "You are the test butler."
        assert "flow-butler" in call["mcp_servers"]
        assert call["env"]["ANTHROPIC_API_KEY"] == "sk-flow"
        assert call["env"]["CUSTOM_VAR"] == "cv"


# ---------------------------------------------------------------------------
# Parametrized tests: orchestration behavior across adapters
# ---------------------------------------------------------------------------


def _make_noop_adapter() -> MockAdapter:
    """Adapter that returns empty result (no error)."""
    return MockAdapter(result_text="")


def _make_result_adapter() -> MockAdapter:
    """Adapter that returns a text result."""
    return MockAdapter(result_text="Hello from adapter!")


def _make_tool_use_adapter() -> MockAdapter:
    """Adapter that returns result with tool calls."""
    return MockAdapter(
        result_text="Done with tools",
        tool_calls=[{"id": "tool_1", "name": "state_get", "input": {"key": "foo"}}],
    )


def _make_error_adapter() -> MockAdapter:
    """Adapter that raises an error."""
    return MockAdapter(error="adapter connection failed")


def _make_slow_adapter() -> MockAdapter:
    """Adapter that sleeps to simulate duration."""
    return MockAdapter(result_text="slow result", delay=0.05)


@pytest.mark.parametrize(
    "adapter_factory,expected_result,expected_error",
    [
        pytest.param(_make_noop_adapter, "", None, id="noop-adapter"),
        pytest.param(_make_result_adapter, "Hello from adapter!", None, id="result-adapter"),
        pytest.param(_make_error_adapter, None, "adapter connection failed", id="error-adapter"),
    ],
)
class TestParametrizedOrchestration:
    """Orchestration tests parametrized across different adapter behaviors."""

    async def test_trigger_returns_spawner_result(
        self, tmp_path: Path, adapter_factory, expected_result, expected_error
    ):
        """Spawner.trigger() wraps adapter output in SpawnerResult."""
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config = _make_config()

        adapter = adapter_factory()
        spawner = Spawner(config=config, config_dir=config_dir, runtime=adapter)
        result = await spawner.trigger("test", "tick")

        if expected_error:
            assert result.error is not None
            assert expected_error in result.error
            assert result.result is None
        else:
            assert result.error is None
            assert result.result == expected_result
        assert result.duration_ms >= 0

    async def test_temp_dir_cleaned_up(
        self, tmp_path: Path, adapter_factory, expected_result, expected_error
    ):
        """Temp dir is cleaned up regardless of adapter outcome."""
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config = _make_config()

        adapter = adapter_factory()
        spawner = Spawner(config=config, config_dir=config_dir, runtime=adapter)

        with patch("butlers.core.spawner._write_mcp_config") as mock_write:
            real_dir = _write_mcp_config("test-butler", 9100)
            mock_write.return_value = real_dir

            with patch("butlers.core.spawner._cleanup_temp_dir") as mock_cleanup:
                await spawner.trigger("test", "tick")
                mock_cleanup.assert_called_once_with(real_dir)

        if real_dir.exists():
            _cleanup_temp_dir(real_dir)


@pytest.mark.parametrize(
    "adapter_factory,expect_error",
    [
        pytest.param(_make_result_adapter, False, id="success"),
        pytest.param(_make_error_adapter, True, id="error"),
    ],
)
class TestParametrizedSessionLogging:
    """Session logging parametrized across success and error adapters."""

    async def test_session_logged(self, tmp_path: Path, adapter_factory, expect_error):
        """Session is created and completed regardless of outcome."""
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config = _make_config()

        mock_pool = AsyncMock()

        with (
            patch("butlers.core.spawner.session_create", new_callable=AsyncMock) as mock_create,
            patch("butlers.core.spawner.session_complete", new_callable=AsyncMock) as mock_complete,
        ):
            import uuid

            fake_session_id = uuid.UUID("00000000-0000-0000-0000-000000000099")
            mock_create.return_value = fake_session_id

            adapter = adapter_factory()
            spawner = Spawner(
                config=config,
                config_dir=config_dir,
                pool=mock_pool,
                runtime=adapter,
            )

            result = await spawner.trigger("test", "tick")

            mock_create.assert_called_once_with(mock_pool, "test", "tick")
            mock_complete.assert_called_once()

            call_args = mock_complete.call_args
            assert call_args[0][0] is mock_pool
            assert call_args[0][1] == fake_session_id

            if expect_error:
                assert result.error is not None
                assert "RuntimeError" in call_args[0][2]
                assert call_args[0][3] == []
            else:
                assert result.error is None
                assert call_args[0][4] >= 0


# ---------------------------------------------------------------------------
# Legacy sdk_query compat test
# ---------------------------------------------------------------------------


class TestLegacySdkQueryCompat:
    """Verify backward compatibility with sdk_query parameter."""

    async def test_sdk_query_still_works(self, tmp_path: Path):
        """Spawner(sdk_query=...) wraps the callable in a ClaudeCodeAdapter."""
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config = _make_config()

        from claude_code_sdk import ResultMessage

        async def mock_sdk(*, prompt: str, options: Any):
            yield ResultMessage(
                subtype="result",
                duration_ms=10,
                duration_api_ms=8,
                is_error=False,
                num_turns=1,
                session_id="compat-test",
                total_cost_usd=0.0,
                usage={},
                result="Hello from legacy!",
            )

        spawner = Spawner(
            config=config,
            config_dir=config_dir,
            sdk_query=mock_sdk,
        )

        result = await spawner.trigger("hello", "tick")
        assert result.result == "Hello from legacy!"
        assert result.error is None
