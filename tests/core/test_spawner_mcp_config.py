"""Tests for Memory MCP server inclusion in ephemeral CC configs (butlers-cfw.7.5).

Covers:
- Memory MCP server included in mcp_servers when memory.enabled=True
- Memory MCP server NOT included when memory.enabled=False
- Memory MCP server NOT included for memory butler itself (name="memory")
- Custom memory port used in MCP server URL
- Memory context fetch skipped when memory.enabled=False
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from butlers.config import ButlerConfig, MemoryConfig, RuntimeConfig
from butlers.core.runtimes.base import RuntimeAdapter
from butlers.core.spawner import Spawner

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# MockAdapter — minimal adapter for MCP config capture
# ---------------------------------------------------------------------------


class MockAdapter(RuntimeAdapter):
    """Minimal mock adapter that captures invoke() calls."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    @property
    def binary_name(self) -> str:
        return "mock"

    async def invoke(
        self,
        prompt: str,
        system_prompt: str,
        mcp_servers: dict[str, Any],
        env: dict[str, str],
        max_turns: int = 20,
        model: str | None = None,
        cwd: Path | None = None,
        timeout: int | None = None,
    ) -> tuple[str | None, list[dict[str, Any]], dict[str, Any] | None]:
        self.calls.append({
            "prompt": prompt,
            "system_prompt": system_prompt,
            "mcp_servers": mcp_servers,
            "env": env,
        })
        return ("ok", [], None)

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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(
    name: str = "test-butler",
    port: int = 9100,
    memory: MemoryConfig | None = None,
) -> ButlerConfig:
    return ButlerConfig(
        name=name,
        port=port,
        runtime=RuntimeConfig(),
        env_required=[],
        env_optional=[],
        memory=memory or MemoryConfig(),
    )


# ---------------------------------------------------------------------------
# Tests: Memory MCP server in ephemeral CC configs
# ---------------------------------------------------------------------------


class TestMemoryMcpServerConfig:
    """Tests for Memory MCP server inclusion in mcp_servers dict."""

    async def test_memory_server_included_when_enabled(self, tmp_path: Path):
        """Memory MCP server is included when memory.enabled=True."""
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config = _make_config(memory=MemoryConfig(enabled=True))
        adapter = MockAdapter()

        spawner = Spawner(config=config, config_dir=config_dir, runtime=adapter)

        with patch(
            "butlers.core.spawner.fetch_memory_context",
            new_callable=AsyncMock,
            return_value=None,
        ):
            await spawner.trigger(prompt="test", trigger_source="trigger_tool")

        assert len(adapter.calls) == 1
        mcp_servers = adapter.calls[0]["mcp_servers"]
        assert "memory" in mcp_servers
        assert mcp_servers["memory"]["url"] == "http://localhost:8150/sse"

    async def test_memory_server_not_included_when_disabled(self, tmp_path: Path):
        """Memory MCP server is NOT included when memory.enabled=False."""
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config = _make_config(memory=MemoryConfig(enabled=False))
        adapter = MockAdapter()

        spawner = Spawner(config=config, config_dir=config_dir, runtime=adapter)

        # fetch_memory_context should not be called at all when disabled
        with patch(
            "butlers.core.spawner.fetch_memory_context",
            new_callable=AsyncMock,
            return_value=None,
        ) as mock_fetch:
            await spawner.trigger(prompt="test", trigger_source="trigger_tool")
            mock_fetch.assert_not_called()

        assert len(adapter.calls) == 1
        mcp_servers = adapter.calls[0]["mcp_servers"]
        assert "memory" not in mcp_servers

    async def test_memory_server_not_included_for_memory_butler(self, tmp_path: Path):
        """Memory MCP server is NOT included when butler name is 'memory'."""
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config = _make_config(name="memory", memory=MemoryConfig(enabled=True))
        adapter = MockAdapter()

        spawner = Spawner(config=config, config_dir=config_dir, runtime=adapter)

        with patch(
            "butlers.core.spawner.fetch_memory_context",
            new_callable=AsyncMock,
            return_value=None,
        ):
            await spawner.trigger(prompt="test", trigger_source="trigger_tool")

        assert len(adapter.calls) == 1
        mcp_servers = adapter.calls[0]["mcp_servers"]
        # The memory butler's own MCP server should be there (as "memory")
        # but NOT a separate "memory" key for the Memory MCP server
        assert "memory" in mcp_servers  # this is the butler's own server
        # Verify it's the butler's own server URL, not the memory MCP server
        assert mcp_servers["memory"]["url"] == f"http://localhost:{config.port}/sse"

    async def test_custom_memory_port_used(self, tmp_path: Path):
        """Custom memory port is reflected in the MCP server URL."""
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config = _make_config(memory=MemoryConfig(enabled=True, port=9999))
        adapter = MockAdapter()

        spawner = Spawner(config=config, config_dir=config_dir, runtime=adapter)

        with patch(
            "butlers.core.spawner.fetch_memory_context",
            new_callable=AsyncMock,
            return_value=None,
        ):
            await spawner.trigger(prompt="test", trigger_source="trigger_tool")

        assert len(adapter.calls) == 1
        mcp_servers = adapter.calls[0]["mcp_servers"]
        assert "memory" in mcp_servers
        assert mcp_servers["memory"]["url"] == "http://localhost:9999/sse"

    async def test_butler_own_server_always_present(self, tmp_path: Path):
        """The butler's own MCP server is always present regardless of memory config."""
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config = _make_config(name="jarvis", port=8200, memory=MemoryConfig(enabled=True))
        adapter = MockAdapter()

        spawner = Spawner(config=config, config_dir=config_dir, runtime=adapter)

        with patch(
            "butlers.core.spawner.fetch_memory_context",
            new_callable=AsyncMock,
            return_value=None,
        ):
            await spawner.trigger(prompt="test", trigger_source="trigger_tool")

        assert len(adapter.calls) == 1
        mcp_servers = adapter.calls[0]["mcp_servers"]
        assert "jarvis" in mcp_servers
        assert mcp_servers["jarvis"]["url"] == "http://localhost:8200/sse"
        assert "memory" in mcp_servers


# ---------------------------------------------------------------------------
# Tests: Memory context fetch gated by config
# ---------------------------------------------------------------------------


class TestMemoryContextFetchGating:
    """Tests for memory context fetch being gated by memory.enabled."""

    async def test_memory_context_fetched_when_enabled(self, tmp_path: Path):
        """fetch_memory_context is called when memory.enabled=True."""
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config = _make_config(memory=MemoryConfig(enabled=True, port=8150))
        adapter = MockAdapter()

        spawner = Spawner(config=config, config_dir=config_dir, runtime=adapter)

        with patch(
            "butlers.core.spawner.fetch_memory_context",
            new_callable=AsyncMock,
            return_value="some context",
        ) as mock_fetch:
            await spawner.trigger(prompt="do task", trigger_source="trigger_tool")

        mock_fetch.assert_called_once()
        # Verify port is passed through
        _, kwargs = mock_fetch.call_args
        assert kwargs["memory_butler_port"] == 8150

    async def test_memory_context_not_fetched_when_disabled(self, tmp_path: Path):
        """fetch_memory_context is NOT called when memory.enabled=False."""
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config = _make_config(memory=MemoryConfig(enabled=False))
        adapter = MockAdapter()

        spawner = Spawner(config=config, config_dir=config_dir, runtime=adapter)

        with patch(
            "butlers.core.spawner.fetch_memory_context",
            new_callable=AsyncMock,
            return_value=None,
        ) as mock_fetch:
            await spawner.trigger(prompt="do task", trigger_source="trigger_tool")

        mock_fetch.assert_not_called()

    async def test_custom_port_passed_to_fetch(self, tmp_path: Path):
        """Custom memory port is passed to fetch_memory_context."""
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config = _make_config(memory=MemoryConfig(enabled=True, port=7777))
        adapter = MockAdapter()

        spawner = Spawner(config=config, config_dir=config_dir, runtime=adapter)

        with patch(
            "butlers.core.spawner.fetch_memory_context",
            new_callable=AsyncMock,
            return_value=None,
        ) as mock_fetch:
            await spawner.trigger(prompt="do task", trigger_source="trigger_tool")

        mock_fetch.assert_called_once()
        _, kwargs = mock_fetch.call_args
        assert kwargs["memory_butler_port"] == 7777

    async def test_memory_context_injected_into_system_prompt(self, tmp_path: Path):
        """When memory context is available, it is injected into system prompt."""
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config = _make_config(memory=MemoryConfig(enabled=True))
        adapter = MockAdapter()

        spawner = Spawner(config=config, config_dir=config_dir, runtime=adapter)

        with patch(
            "butlers.core.spawner.fetch_memory_context",
            new_callable=AsyncMock,
            return_value="Remembered: user likes TDD.",
        ):
            await spawner.trigger(prompt="do task", trigger_source="trigger_tool")

        assert len(adapter.calls) == 1
        system_prompt = adapter.calls[0]["system_prompt"]
        assert "Remembered: user likes TDD." in system_prompt

    async def test_no_memory_context_when_disabled(self, tmp_path: Path):
        """System prompt has no memory context when memory.enabled=False."""
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        (config_dir / "CLAUDE.md").write_text("Base prompt only.")
        config = _make_config(memory=MemoryConfig(enabled=False))
        adapter = MockAdapter()

        spawner = Spawner(config=config, config_dir=config_dir, runtime=adapter)

        with patch(
            "butlers.core.spawner.fetch_memory_context",
            new_callable=AsyncMock,
            return_value="Should not appear",
        ) as mock_fetch:
            await spawner.trigger(prompt="do task", trigger_source="trigger_tool")

        mock_fetch.assert_not_called()
        assert len(adapter.calls) == 1
        system_prompt = adapter.calls[0]["system_prompt"]
        assert "Should not appear" not in system_prompt
