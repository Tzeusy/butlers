"""Tests for the CC Spawner (butlers-0qp.8).

Covers:
- MCP config generation (correct JSON structure, single endpoint)
- Temp dir cleanup (success and failure paths)
- Serial dispatch (lock prevents concurrent execution)
- Credential passthrough (only declared vars included)
- CLAUDE.md handling (present, missing, empty)
- Session logging wired correctly
- SpawnerResult construction on success and error
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

from butlers.config import ButlerConfig
from butlers.core.spawner import (
    CCSpawner,
    SpawnerResult,
    _build_env,
    _build_mcp_config,
    _cleanup_temp_dir,
    _read_system_prompt,
    _write_mcp_config,
)

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


async def _noop_sdk_query(*, prompt: str, options: Any):
    """A mock SDK query that yields nothing (empty async generator)."""
    return
    yield  # noqa: E501 — makes this an async generator


async def _result_sdk_query(*, prompt: str, options: Any):
    """A mock SDK query that yields a ResultMessage."""
    from claude_code_sdk import ResultMessage

    yield ResultMessage(
        subtype="result",
        duration_ms=42,
        duration_api_ms=30,
        is_error=False,
        num_turns=1,
        session_id="fake-session",
        total_cost_usd=0.01,
        usage={"input_tokens": 100, "output_tokens": 50},
        result="Hello from CC!",
    )


async def _tool_use_sdk_query(*, prompt: str, options: Any):
    """A mock SDK query that yields an AssistantMessage with a ToolUseBlock, then a result."""
    from claude_code_sdk import AssistantMessage, ResultMessage, ToolUseBlock

    yield AssistantMessage(
        content=[
            ToolUseBlock(id="tool_1", name="state_get", input={"key": "foo"}),
        ],
        model="claude-test",
    )
    yield ResultMessage(
        subtype="result",
        duration_ms=100,
        duration_api_ms=80,
        is_error=False,
        num_turns=2,
        session_id="fake-session-2",
        total_cost_usd=0.02,
        usage={"input_tokens": 200, "output_tokens": 100},
        result="Done with tools",
    )


async def _error_sdk_query(*, prompt: str, options: Any):
    """A mock SDK query that raises an exception."""
    raise RuntimeError("SDK connection failed")
    yield  # noqa: E501 — makes this an async generator


async def _slow_sdk_query(*, prompt: str, options: Any):
    """A mock SDK query that sleeps to simulate duration."""
    await asyncio.sleep(0.05)
    from claude_code_sdk import ResultMessage

    yield ResultMessage(
        subtype="result",
        duration_ms=50,
        duration_api_ms=40,
        is_error=False,
        num_turns=1,
        session_id="slow-session",
        total_cost_usd=0.0,
        usage={},
        result="slow result",
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
    """Temp dir is cleaned up after CC session on both success and failure."""

    async def test_cleanup_on_success(self, tmp_path: Path):
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config = _make_config()

        spawner = CCSpawner(
            config=config,
            config_dir=config_dir,
            sdk_query=_noop_sdk_query,
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

    async def test_cleanup_on_sdk_error(self, tmp_path: Path):
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config = _make_config()

        spawner = CCSpawner(
            config=config,
            config_dir=config_dir,
            sdk_query=_error_sdk_query,
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
# 8.2: CC SDK invocation and SpawnerResult
# ---------------------------------------------------------------------------


class TestSpawnerResult:
    """SpawnerResult dataclass behavior."""

    def test_default_values(self):
        r = SpawnerResult()
        assert r.output is None
        assert r.success is False
        assert r.tool_calls == []
        assert r.error is None
        assert r.duration_ms == 0

    def test_success_result(self):
        r = SpawnerResult(
            output="output text", success=True, tool_calls=[{"name": "t"}], duration_ms=42
        )
        assert r.output == "output text"
        assert r.success is True
        assert len(r.tool_calls) == 1
        assert r.error is None

    def test_error_result(self):
        r = SpawnerResult(error="something broke", success=False, duration_ms=10)
        assert r.output is None
        assert r.success is False
        assert r.error == "something broke"


class TestCCSdkInvocation:
    """Tests for SDK invocation via CCSpawner.trigger()."""

    async def test_success_with_result_message(self, tmp_path: Path):
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config = _make_config()

        spawner = CCSpawner(
            config=config,
            config_dir=config_dir,
            sdk_query=_result_sdk_query,
        )

        result = await spawner.trigger("hello", "tick")
        assert result.output == "Hello from CC!"
        assert result.success is True
        assert result.error is None
        assert result.duration_ms >= 0

    async def test_tool_calls_captured(self, tmp_path: Path):
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config = _make_config()

        spawner = CCSpawner(
            config=config,
            config_dir=config_dir,
            sdk_query=_tool_use_sdk_query,
        )

        result = await spawner.trigger("use tools", "trigger_tool")
        assert result.output == "Done with tools"
        assert result.success is True
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0]["name"] == "state_get"
        assert result.tool_calls[0]["input"] == {"key": "foo"}

    async def test_sdk_error_wrapped_in_result(self, tmp_path: Path):
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config = _make_config()

        spawner = CCSpawner(
            config=config,
            config_dir=config_dir,
            sdk_query=_error_sdk_query,
        )

        result = await spawner.trigger("fail", "tick")
        assert result.error is not None
        assert "RuntimeError" in result.error
        assert "SDK connection failed" in result.error
        assert result.output is None
        assert result.success is False
        assert result.duration_ms >= 0

    async def test_duration_measured(self, tmp_path: Path):
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config = _make_config()

        spawner = CCSpawner(
            config=config,
            config_dir=config_dir,
            sdk_query=_slow_sdk_query,
        )

        result = await spawner.trigger("slow", "tick")
        assert result.duration_ms >= 40  # at least ~50ms sleep


# ---------------------------------------------------------------------------
# 8.3: Credential passthrough
# ---------------------------------------------------------------------------


class TestCredentialPassthrough:
    """Only declared env vars are passed to the CC instance."""

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

    async def test_env_passed_to_sdk_options(self, tmp_path: Path):
        """Verify the env dict is passed through to ClaudeCodeOptions."""
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config = _make_config(env_required=["BUTLER_SECRET"])

        captured_options: list[Any] = []

        async def capturing_sdk(*, prompt: str, options: Any):
            captured_options.append(options)
            return
            yield

        spawner = CCSpawner(
            config=config,
            config_dir=config_dir,
            sdk_query=capturing_sdk,
        )

        with patch.dict(
            os.environ,
            {"ANTHROPIC_API_KEY": "sk-key", "BUTLER_SECRET": "s3cret"},
            clear=False,
        ):
            await spawner.trigger("test env", "tick")

        assert len(captured_options) == 1
        opts = captured_options[0]
        assert opts.env["ANTHROPIC_API_KEY"] == "sk-key"
        assert opts.env["BUTLER_SECRET"] == "s3cret"


# ---------------------------------------------------------------------------
# 8.4: CLAUDE.md system prompt reading
# ---------------------------------------------------------------------------


class TestSystemPrompt:
    """CLAUDE.md reading for system prompt."""

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

    async def test_system_prompt_passed_to_sdk(self, tmp_path: Path):
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        claude_md = config_dir / "CLAUDE.md"
        claude_md.write_text("Custom system prompt for testing.")
        config = _make_config()

        captured_options: list[Any] = []

        async def capturing_sdk(*, prompt: str, options: Any):
            captured_options.append(options)
            return
            yield

        spawner = CCSpawner(
            config=config,
            config_dir=config_dir,
            sdk_query=capturing_sdk,
        )

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-key"}, clear=False):
            await spawner.trigger("test", "tick")

        assert captured_options[0].system_prompt == "Custom system prompt for testing."


# ---------------------------------------------------------------------------
# 8.5: Serial dispatch with asyncio lock
# ---------------------------------------------------------------------------


class TestSerialDispatch:
    """asyncio.Lock ensures only one CC instance runs at a time."""

    async def test_concurrent_triggers_are_serialized(self, tmp_path: Path):
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config = _make_config()

        execution_log: list[tuple[str, str]] = []

        async def tracking_sdk(*, prompt: str, options: Any):
            execution_log.append(("start", prompt))
            await asyncio.sleep(0.03)
            execution_log.append(("end", prompt))
            from claude_code_sdk import ResultMessage

            yield ResultMessage(
                subtype="result",
                duration_ms=30,
                duration_api_ms=20,
                is_error=False,
                num_turns=1,
                session_id="s",
                total_cost_usd=0.0,
                usage={},
                result=f"result-{prompt}",
            )

        spawner = CCSpawner(
            config=config,
            config_dir=config_dir,
            sdk_query=tracking_sdk,
        )

        # Launch 3 concurrent triggers
        results = await asyncio.gather(
            spawner.trigger("A", "tick"),
            spawner.trigger("B", "tick"),
            spawner.trigger("C", "tick"),
        )

        # All should succeed
        assert all(r.error is None for r in results)
        assert all(r.success is True for r in results)

        # Verify serial execution: each "start" must be followed by its "end"
        # before the next "start"
        for i in range(0, len(execution_log), 2):
            assert execution_log[i][0] == "start"
            assert execution_log[i + 1][0] == "end"
            assert execution_log[i][1] == execution_log[i + 1][1]

    async def test_lock_released_on_error(self, tmp_path: Path):
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config = _make_config()

        call_count = 0

        async def failing_then_succeeding_sdk(*, prompt: str, options: Any):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("First call fails")
            from claude_code_sdk import ResultMessage

            yield ResultMessage(
                subtype="result",
                duration_ms=1,
                duration_api_ms=1,
                is_error=False,
                num_turns=1,
                session_id="s",
                total_cost_usd=0.0,
                usage={},
                result="second call works",
            )

        spawner = CCSpawner(
            config=config,
            config_dir=config_dir,
            sdk_query=failing_then_succeeding_sdk,
        )

        result1 = await spawner.trigger("first", "tick")
        assert result1.error is not None
        assert result1.success is False

        # Lock should be released — second call should work
        result2 = await spawner.trigger("second", "tick")
        assert result2.error is None
        assert result2.output == "second call works"
        assert result2.success is True


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

            spawner = CCSpawner(
                config=config,
                config_dir=config_dir,
                pool=mock_pool,
                sdk_query=_result_sdk_query,
            )

            await spawner.trigger("log me", "schedule")

            # session_create called with correct args
            # session_create now takes trace_id as 4th arg (None without telemetry setup)
            call_args = mock_create.call_args
            assert call_args[0][0] is mock_pool
            assert call_args[0][1] == "log me"
            assert call_args[0][2] == "schedule"
            # trace_id may be None if no telemetry is set up
            assert len(call_args[0]) == 4

            # session_complete called with result data
            mock_complete.assert_called_once()
            call_kwargs = mock_complete.call_args.kwargs
            call_args = mock_complete.call_args.args
            assert call_args[0] is mock_pool
            assert call_args[1] == fake_session_id
            # Check keyword arguments for the new signature
            assert call_kwargs["output"] == "Hello from CC!"
            assert isinstance(call_kwargs["tool_calls"], list)
            assert call_kwargs["duration_ms"] >= 0
            assert call_kwargs["success"] is True
            assert call_kwargs.get("error") is None

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

            spawner = CCSpawner(
                config=config,
                config_dir=config_dir,
                pool=mock_pool,
                sdk_query=_error_sdk_query,
            )

            result = await spawner.trigger("fail", "tick")
            assert result.error is not None
            assert result.success is False

            # session_complete called with error info
            mock_complete.assert_called_once()
            call_kwargs = mock_complete.call_args.kwargs
            call_args = mock_complete.call_args.args
            assert call_args[0] is mock_pool
            assert call_args[1] == fake_session_id
            assert call_kwargs["output"] is None
            assert call_kwargs["tool_calls"] == []
            assert call_kwargs["success"] is False
            assert "RuntimeError" in call_kwargs["error"]

    async def test_no_session_logging_without_pool(self, tmp_path: Path):
        """When pool is None, no session logging occurs (no errors either)."""
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config = _make_config()

        spawner = CCSpawner(
            config=config,
            config_dir=config_dir,
            pool=None,
            sdk_query=_result_sdk_query,
        )

        # Should not raise even without a pool
        result = await spawner.trigger("no pool", "tick")
        assert result.output == "Hello from CC!"
        assert result.success is True


# ---------------------------------------------------------------------------
# Integration-style test: full flow without real SDK
# ---------------------------------------------------------------------------


class TestFullFlow:
    """End-to-end spawner flow with mocked SDK."""

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

        captured: dict[str, Any] = {}

        async def capturing_sdk(*, prompt: str, options: Any):
            captured["prompt"] = prompt
            captured["options"] = options
            from claude_code_sdk import AssistantMessage, ResultMessage, ToolUseBlock

            yield AssistantMessage(
                content=[ToolUseBlock(id="t1", name="state_set", input={"k": "v"})],
                model="claude-test",
            )
            yield ResultMessage(
                subtype="result",
                duration_ms=10,
                duration_api_ms=8,
                is_error=False,
                num_turns=1,
                session_id="full-flow",
                total_cost_usd=0.005,
                usage={},
                result="All done!",
            )

        spawner = CCSpawner(
            config=config,
            config_dir=config_dir,
            sdk_query=capturing_sdk,
        )

        with patch.dict(
            os.environ,
            {"ANTHROPIC_API_KEY": "sk-flow", "CUSTOM_VAR": "cv"},
            clear=False,
        ):
            result = await spawner.trigger("do the thing", "schedule")

        assert result.output == "All done!"
        assert result.success is True
        assert result.error is None
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0]["name"] == "state_set"
        assert result.duration_ms >= 0

        # Verify options
        opts = captured["options"]
        assert opts.system_prompt == "You are the test butler."
        assert opts.permission_mode == "bypassPermissions"
        assert "flow-butler" in opts.mcp_servers
        assert opts.env["ANTHROPIC_API_KEY"] == "sk-flow"
        assert opts.env["CUSTOM_VAR"] == "cv"


# ---------------------------------------------------------------------------
# butlers-06j.13: max_turns and cwd configuration
# ---------------------------------------------------------------------------


class TestMaxTurnsAndCwd:
    """Tests for max_turns and cwd configuration in CC spawner."""

    async def test_max_turns_default_20(self, tmp_path: Path):
        """Default max_turns should be 20."""
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config = _make_config()

        captured_options: list[Any] = []

        async def capturing_sdk(*, prompt: str, options: Any):
            captured_options.append(options)
            return
            yield

        spawner = CCSpawner(
            config=config,
            config_dir=config_dir,
            sdk_query=capturing_sdk,
        )

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-key"}, clear=False):
            await spawner.trigger("test", "tick")

        assert len(captured_options) == 1
        assert captured_options[0].max_turns == 20

    async def test_max_turns_custom(self, tmp_path: Path):
        """Custom max_turns should be passed through."""
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config = _make_config()

        captured_options: list[Any] = []

        async def capturing_sdk(*, prompt: str, options: Any):
            captured_options.append(options)
            return
            yield

        spawner = CCSpawner(
            config=config,
            config_dir=config_dir,
            sdk_query=capturing_sdk,
        )

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-key"}, clear=False):
            await spawner.trigger("test", "tick", max_turns=5)

        assert len(captured_options) == 1
        assert captured_options[0].max_turns == 5

    async def test_cwd_set_to_config_dir(self, tmp_path: Path):
        """cwd should be set to the butler's config directory."""
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config = _make_config()

        captured_options: list[Any] = []

        async def capturing_sdk(*, prompt: str, options: Any):
            captured_options.append(options)
            return
            yield

        spawner = CCSpawner(
            config=config,
            config_dir=config_dir,
            sdk_query=capturing_sdk,
        )

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-key"}, clear=False):
            await spawner.trigger("test", "tick")

        assert len(captured_options) == 1
        assert captured_options[0].cwd == str(config_dir)
# 8.7: Butler.cc_session span (butlers-06j.24)
# ---------------------------------------------------------------------------


class TestCCSessionSpan:
    """Tests for butler.cc_session span creation and attributes."""

    async def test_cc_session_span_created(self, tmp_path: Path):
        """Verify that a butler.cc_session span is created during CC invocation."""
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor
        from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

        # Reset OTel state
        trace._TRACER_PROVIDER_SET_ONCE = trace.Once()
        trace._TRACER_PROVIDER = None

        # Set up in-memory exporter
        exporter = InMemorySpanExporter()
        resource = Resource.create({"service.name": "butler-test"})
        provider = TracerProvider(resource=resource)
        provider.add_span_processor(SimpleSpanProcessor(exporter))
        trace.set_tracer_provider(provider)

        try:
            config_dir = tmp_path / "config"
            config_dir.mkdir()
            config = _make_config(name="test-butler")

            spawner = CCSpawner(
                config=config,
                config_dir=config_dir,
                sdk_query=_result_sdk_query,
            )

            await spawner.trigger("test prompt", "tick")

            spans = exporter.get_finished_spans()
            cc_session_spans = [s for s in spans if s.name == "butler.cc_session"]
            assert len(cc_session_spans) == 1
            span = cc_session_spans[0]
            assert span.attributes["butler.name"] == "test-butler"
            assert span.attributes["prompt_length"] == len("test prompt")
        finally:
            provider.shutdown()
            trace._TRACER_PROVIDER_SET_ONCE = trace.Once()
            trace._TRACER_PROVIDER = None

    async def test_cc_session_span_has_session_id(self, tmp_path: Path):
        """Verify that session_id attribute is set on the span."""
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor
        from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

        trace._TRACER_PROVIDER_SET_ONCE = trace.Once()
        trace._TRACER_PROVIDER = None

        exporter = InMemorySpanExporter()
        resource = Resource.create({"service.name": "butler-test"})
        provider = TracerProvider(resource=resource)
        provider.add_span_processor(SimpleSpanProcessor(exporter))
        trace.set_tracer_provider(provider)

        try:
            config_dir = tmp_path / "config"
            config_dir.mkdir()
            config = _make_config()

            mock_pool = AsyncMock()
            fake_session_id = "00000000-0000-0000-0000-000000000001"

            with patch(
                "butlers.core.spawner.session_create", new_callable=AsyncMock
            ) as mock_create:
                import uuid

                mock_create.return_value = uuid.UUID(fake_session_id)

                spawner = CCSpawner(
                    config=config,
                    config_dir=config_dir,
                    pool=mock_pool,
                    sdk_query=_result_sdk_query,
                )

                await spawner.trigger("test", "tick")

                spans = exporter.get_finished_spans()
                cc_session_spans = [s for s in spans if s.name == "butler.cc_session"]
                assert len(cc_session_spans) == 1
                span = cc_session_spans[0]
                assert "session_id" in span.attributes
                assert span.attributes["session_id"] == fake_session_id
        finally:
            provider.shutdown()
            trace._TRACER_PROVIDER_SET_ONCE = trace.Once()
            trace._TRACER_PROVIDER = None

    async def test_trace_id_passed_to_session_create(self, tmp_path: Path):
        """Verify that trace_id is extracted from span and passed to session_create."""
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor
        from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

        trace._TRACER_PROVIDER_SET_ONCE = trace.Once()
        trace._TRACER_PROVIDER = None

        exporter = InMemorySpanExporter()
        resource = Resource.create({"service.name": "butler-test"})
        provider = TracerProvider(resource=resource)
        provider.add_span_processor(SimpleSpanProcessor(exporter))
        trace.set_tracer_provider(provider)

        try:
            config_dir = tmp_path / "config"
            config_dir.mkdir()
            config = _make_config()

            mock_pool = AsyncMock()

            with patch(
                "butlers.core.spawner.session_create", new_callable=AsyncMock
            ) as mock_create:
                import uuid

                mock_create.return_value = uuid.UUID("00000000-0000-0000-0000-000000000001")

                spawner = CCSpawner(
                    config=config,
                    config_dir=config_dir,
                    pool=mock_pool,
                    sdk_query=_result_sdk_query,
                )

                await spawner.trigger("test", "tick")

                # Verify session_create was called with a trace_id
                mock_create.assert_called_once()
                call_args = mock_create.call_args
                assert call_args[0][0] is mock_pool
                assert call_args[0][1] == "test"
                assert call_args[0][2] == "tick"
                trace_id_arg = call_args[0][3]
                assert trace_id_arg is not None
                assert isinstance(trace_id_arg, str)
                assert len(trace_id_arg) == 32  # trace_id is 128-bit hex string

                # Verify the trace_id matches the span's trace_id
                spans = exporter.get_finished_spans()
                cc_session_spans = [s for s in spans if s.name == "butler.cc_session"]
                assert len(cc_session_spans) == 1
                span = cc_session_spans[0]
                span_trace_id = format(span.context.trace_id, "032x")
                assert trace_id_arg == span_trace_id
        finally:
            provider.shutdown()
            trace._TRACER_PROVIDER_SET_ONCE = trace.Once()
            trace._TRACER_PROVIDER = None

    async def test_span_records_exception_on_error(self, tmp_path: Path):
        """Verify that exceptions are recorded on the span."""
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor
        from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

        trace._TRACER_PROVIDER_SET_ONCE = trace.Once()
        trace._TRACER_PROVIDER = None

        exporter = InMemorySpanExporter()
        resource = Resource.create({"service.name": "butler-test"})
        provider = TracerProvider(resource=resource)
        provider.add_span_processor(SimpleSpanProcessor(exporter))
        trace.set_tracer_provider(provider)

        try:
            config_dir = tmp_path / "config"
            config_dir.mkdir()
            config = _make_config()

            spawner = CCSpawner(
                config=config,
                config_dir=config_dir,
                sdk_query=_error_sdk_query,
            )

            result = await spawner.trigger("fail", "tick")
            assert result.error is not None

            spans = exporter.get_finished_spans()
            cc_session_spans = [s for s in spans if s.name == "butler.cc_session"]
            assert len(cc_session_spans) == 1
            span = cc_session_spans[0]

            # Verify span status is ERROR
            assert span.status.status_code == trace.StatusCode.ERROR

            # Verify exception was recorded
            events = span.events
            exception_events = [e for e in events if e.name == "exception"]
            assert len(exception_events) == 1
            exc_event = exception_events[0]
            assert "RuntimeError" in exc_event.attributes["exception.type"]
            assert "SDK connection failed" in exc_event.attributes["exception.message"]
        finally:
            provider.shutdown()
            trace._TRACER_PROVIDER_SET_ONCE = trace.Once()
            trace._TRACER_PROVIDER = None

    async def test_no_span_error_without_pool(self, tmp_path: Path):
        """Verify span is still created even without a pool (no session_id attribute)."""
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor
        from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

        trace._TRACER_PROVIDER_SET_ONCE = trace.Once()
        trace._TRACER_PROVIDER = None

        exporter = InMemorySpanExporter()
        resource = Resource.create({"service.name": "butler-test"})
        provider = TracerProvider(resource=resource)
        provider.add_span_processor(SimpleSpanProcessor(exporter))
        trace.set_tracer_provider(provider)

        try:
            config_dir = tmp_path / "config"
            config_dir.mkdir()
            config = _make_config()

            spawner = CCSpawner(
                config=config,
                config_dir=config_dir,
                pool=None,
                sdk_query=_result_sdk_query,
            )

            result = await spawner.trigger("no pool", "tick")
            assert result.error is None

            spans = exporter.get_finished_spans()
            cc_session_spans = [s for s in spans if s.name == "butler.cc_session"]
            assert len(cc_session_spans) == 1
            span = cc_session_spans[0]
            assert span.attributes["butler.name"] == "test-butler"
            assert span.attributes["prompt_length"] == len("no pool")
            # session_id should not be set when there's no pool
            assert "session_id" not in span.attributes
        finally:
            provider.shutdown()
            trace._TRACER_PROVIDER_SET_ONCE = trace.Once()
            trace._TRACER_PROVIDER = None

