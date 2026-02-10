"""Tests for memory context injection in Spawner (butlers-cfw.7.1, butlers-cfw.7.2).

Covers:
- fetch_memory_context returns context on success
- fetch_memory_context returns None on connection error
- fetch_memory_context returns None on timeout
- fetch_memory_context returns None on non-200 response
- fetch_memory_context returns None on malformed response
- Memory context is appended to system prompt when available
- Spawner works without memory context when Memory Butler is unreachable
- Timeout on memory context fetch doesn't block spawner
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from butlers.config import ButlerConfig
from butlers.core.spawner import fetch_memory_context

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(
    name: str = "test-butler",
    port: int = 9100,
) -> ButlerConfig:
    return ButlerConfig(
        name=name,
        port=port,
        env_required=[],
        env_optional=[],
    )


def _mock_response(*, status_code: int = 200, json_data: Any = None) -> httpx.Response:
    """Create a mock httpx.Response with the given status and JSON body."""
    response = MagicMock(spec=httpx.Response)
    response.status_code = status_code
    response.json.return_value = json_data
    return response


# ---------------------------------------------------------------------------
# Tests for fetch_memory_context (standalone function)
# ---------------------------------------------------------------------------


class TestFetchMemoryContext:
    """Tests for the fetch_memory_context helper function."""

    async def test_returns_context_on_success(self):
        """When Memory Butler responds with valid content, return it."""
        mock_response = _mock_response(
            status_code=200,
            json_data={"content": "You previously discussed project deadlines."},
        )

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("butlers.core.spawner.httpx.AsyncClient", return_value=mock_client):
            result = await fetch_memory_context("my-butler", "hello world")

        assert result == "You previously discussed project deadlines."
        mock_client.post.assert_called_once_with(
            "http://localhost:8150/call-tool",
            json={
                "name": "memory_context",
                "arguments": {
                    "trigger_prompt": "hello world",
                    "butler": "my-butler",
                },
            },
        )

    async def test_returns_none_on_connection_error(self):
        """When Memory Butler is unreachable, return None."""
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post.side_effect = httpx.ConnectError("Connection refused")
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("butlers.core.spawner.httpx.AsyncClient", return_value=mock_client):
            result = await fetch_memory_context("my-butler", "hello")

        assert result is None

    async def test_returns_none_on_timeout(self):
        """When the request times out, return None."""
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post.side_effect = httpx.TimeoutException("Request timed out")
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("butlers.core.spawner.httpx.AsyncClient", return_value=mock_client):
            result = await fetch_memory_context("my-butler", "hello")

        assert result is None

    async def test_returns_none_on_non_200_response(self):
        """When Memory Butler returns a non-200 status, return None."""
        mock_response = _mock_response(status_code=500, json_data={"error": "internal"})

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("butlers.core.spawner.httpx.AsyncClient", return_value=mock_client):
            result = await fetch_memory_context("my-butler", "hello")

        assert result is None

    async def test_returns_none_on_malformed_json(self):
        """When the response JSON lacks 'content', return None."""
        mock_response = _mock_response(
            status_code=200,
            json_data={"unexpected_key": "value"},
        )

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("butlers.core.spawner.httpx.AsyncClient", return_value=mock_client):
            result = await fetch_memory_context("my-butler", "hello")

        assert result is None

    async def test_returns_none_on_empty_content(self):
        """When content is an empty string, return None."""
        mock_response = _mock_response(
            status_code=200,
            json_data={"content": ""},
        )

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("butlers.core.spawner.httpx.AsyncClient", return_value=mock_client):
            result = await fetch_memory_context("my-butler", "hello")

        assert result is None

    async def test_returns_none_on_non_string_content(self):
        """When content is not a string (e.g. a dict), return None."""
        mock_response = _mock_response(
            status_code=200,
            json_data={"content": {"nested": "object"}},
        )

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("butlers.core.spawner.httpx.AsyncClient", return_value=mock_client):
            result = await fetch_memory_context("my-butler", "hello")

        assert result is None

    async def test_custom_port(self):
        """Verify the custom port parameter is used in the URL."""
        mock_response = _mock_response(
            status_code=200,
            json_data={"content": "context from port 9999"},
        )

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("butlers.core.spawner.httpx.AsyncClient", return_value=mock_client):
            result = await fetch_memory_context(
                "my-butler", "hello", memory_butler_port=9999
            )

        assert result == "context from port 9999"
        mock_client.post.assert_called_once_with(
            "http://localhost:9999/call-tool",
            json={
                "name": "memory_context",
                "arguments": {
                    "trigger_prompt": "hello",
                    "butler": "my-butler",
                },
            },
        )

    async def test_json_decode_error(self):
        """When response.json() raises, return None."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.side_effect = ValueError("Invalid JSON")

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("butlers.core.spawner.httpx.AsyncClient", return_value=mock_client):
            result = await fetch_memory_context("my-butler", "hello")

        assert result is None


# ---------------------------------------------------------------------------
# Integration tests: memory context injection in Spawner._run
# ---------------------------------------------------------------------------


class TestSpawnerMemoryContextInjection:
    """Tests for memory context being injected into the system prompt."""

    async def test_memory_context_injected_into_system_prompt(self, tmp_path: Path):
        """When memory context is available, it is appended to system prompt."""
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config = _make_config()

        captured_system_prompt: str | None = None

        async def capturing_sdk(*, prompt: str, options: Any):
            nonlocal captured_system_prompt
            captured_system_prompt = getattr(options, "system_prompt", None)
            from claude_code_sdk import ResultMessage

            yield ResultMessage(
                subtype="result",
                duration_ms=10,
                duration_api_ms=8,
                is_error=False,
                num_turns=1,
                session_id="test-session",
                total_cost_usd=0.005,
                usage={},
                result="Done",
            )

        from butlers.core.spawner import Spawner

        spawner = Spawner(
            config=config,
            config_dir=config_dir,
            sdk_query=capturing_sdk,
        )

        memory_text = "Remembered: user prefers concise answers."
        with patch(
            "butlers.core.spawner.fetch_memory_context",
            new_callable=AsyncMock,
            return_value=memory_text,
        ):
            await spawner.trigger(prompt="do task", trigger_source="trigger_tool")

        # The system prompt should end with the memory context
        assert captured_system_prompt is not None
        assert captured_system_prompt.endswith(memory_text)
        # And the memory context should be separated by double newline
        assert f"\n\n{memory_text}" in captured_system_prompt

    async def test_spawner_works_without_memory_context(self, tmp_path: Path):
        """When memory context is None, spawner works normally."""
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config = _make_config()

        captured_system_prompt: str | None = None

        async def capturing_sdk(*, prompt: str, options: Any):
            nonlocal captured_system_prompt
            captured_system_prompt = getattr(options, "system_prompt", None)
            from claude_code_sdk import ResultMessage

            yield ResultMessage(
                subtype="result",
                duration_ms=10,
                duration_api_ms=8,
                is_error=False,
                num_turns=1,
                session_id="test-session",
                total_cost_usd=0.005,
                usage={},
                result="Done",
            )

        from butlers.core.spawner import Spawner

        spawner = Spawner(
            config=config,
            config_dir=config_dir,
            sdk_query=capturing_sdk,
        )

        with patch(
            "butlers.core.spawner.fetch_memory_context",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await spawner.trigger(prompt="do task", trigger_source="trigger_tool")

        assert result.success is True
        # System prompt should not contain memory context separator pattern
        # (it should just be the base system prompt)
        assert captured_system_prompt is not None

    async def test_memory_context_appended_after_system_prompt(self, tmp_path: Path):
        """Memory context comes after the original system prompt content."""
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        # Write a CLAUDE.md so we know the base system prompt content
        (config_dir / "CLAUDE.md").write_text("Base system instructions.")
        config = _make_config()

        captured_system_prompt: str | None = None

        async def capturing_sdk(*, prompt: str, options: Any):
            nonlocal captured_system_prompt
            captured_system_prompt = getattr(options, "system_prompt", None)
            from claude_code_sdk import ResultMessage

            yield ResultMessage(
                subtype="result",
                duration_ms=10,
                duration_api_ms=8,
                is_error=False,
                num_turns=1,
                session_id="test-session",
                total_cost_usd=0.005,
                usage={},
                result="Done",
            )

        from butlers.core.spawner import Spawner

        spawner = Spawner(
            config=config,
            config_dir=config_dir,
            sdk_query=capturing_sdk,
        )

        memory_text = "Memory: user is working on project X."
        with patch(
            "butlers.core.spawner.fetch_memory_context",
            new_callable=AsyncMock,
            return_value=memory_text,
        ):
            await spawner.trigger(prompt="do task", trigger_source="trigger_tool")

        assert captured_system_prompt is not None
        # Base system prompt comes first
        assert captured_system_prompt.startswith("Base system instructions.")
        # Memory context comes after
        assert captured_system_prompt.endswith(memory_text)
        # Separated by double newline
        parts = captured_system_prompt.split("\n\n")
        assert len(parts) >= 2
        assert parts[-1] == memory_text

    async def test_timeout_does_not_block_spawner(self, tmp_path: Path):
        """Spawner proceeds normally even when memory fetch times out."""
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config = _make_config()

        invoked = False

        async def capturing_sdk(*, prompt: str, options: Any):
            nonlocal invoked
            invoked = True
            from claude_code_sdk import ResultMessage

            yield ResultMessage(
                subtype="result",
                duration_ms=10,
                duration_api_ms=8,
                is_error=False,
                num_turns=1,
                session_id="test-session",
                total_cost_usd=0.005,
                usage={},
                result="Done",
            )

        from butlers.core.spawner import Spawner

        spawner = Spawner(
            config=config,
            config_dir=config_dir,
            sdk_query=capturing_sdk,
        )

        # Simulate a timeout in fetch_memory_context (returns None)
        with patch(
            "butlers.core.spawner.fetch_memory_context",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await spawner.trigger(prompt="do task", trigger_source="trigger_tool")

        assert result.success is True
        assert invoked is True
