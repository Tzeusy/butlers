"""Tests for RuntimeAdapter ABC and adapter registry."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from butlers.core.runtimes import RuntimeAdapter, get_adapter, register_adapter
from butlers.core.runtimes.base import (
    ClaudeCodeAdapter,
    CodexAdapter,
)
from butlers.core.runtimes.gemini import GeminiAdapter

# ---------------------------------------------------------------------------
# Test fixtures — concrete and partial subclasses
# ---------------------------------------------------------------------------


class FullAdapter(RuntimeAdapter):
    """Fully concrete adapter implementation for testing."""

    async def invoke(
        self,
        prompt: str,
        system_prompt: str,
        mcp_servers: dict[str, Any],
        env: dict[str, str],
        cwd: Path | None = None,
        timeout: int | None = None,
    ) -> tuple[str | None, list[dict[str, Any]]]:
        return ("ok", [])

    def build_config_file(
        self,
        mcp_servers: dict[str, Any],
        tmp_dir: Path,
    ) -> Path:
        return tmp_dir / "config.json"

    def parse_system_prompt_file(self, config_dir: Path) -> str:
        return "system prompt"


class MissingInvokeAdapter(RuntimeAdapter):
    """Missing the invoke() method."""

    def build_config_file(
        self,
        mcp_servers: dict[str, Any],
        tmp_dir: Path,
    ) -> Path:
        return tmp_dir / "config.json"

    def parse_system_prompt_file(self, config_dir: Path) -> str:
        return ""


class MissingBuildConfigAdapter(RuntimeAdapter):
    """Missing the build_config_file() method."""

    async def invoke(
        self,
        prompt: str,
        system_prompt: str,
        mcp_servers: dict[str, Any],
        env: dict[str, str],
        cwd: Path | None = None,
        timeout: int | None = None,
    ) -> tuple[str | None, list[dict[str, Any]]]:
        return (None, [])

    def parse_system_prompt_file(self, config_dir: Path) -> str:
        return ""


class MissingParsePromptAdapter(RuntimeAdapter):
    """Missing the parse_system_prompt_file() method."""

    async def invoke(
        self,
        prompt: str,
        system_prompt: str,
        mcp_servers: dict[str, Any],
        env: dict[str, str],
        cwd: Path | None = None,
        timeout: int | None = None,
    ) -> tuple[str | None, list[dict[str, Any]]]:
        return (None, [])

    def build_config_file(
        self,
        mcp_servers: dict[str, Any],
        tmp_dir: Path,
    ) -> Path:
        return tmp_dir / "config.json"


# ---------------------------------------------------------------------------
# ABC enforcement tests
# ---------------------------------------------------------------------------


def test_cannot_instantiate_runtime_adapter_abc():
    """RuntimeAdapter is abstract and cannot be instantiated directly."""
    with pytest.raises(TypeError):
        RuntimeAdapter()  # type: ignore[abstract]


def test_missing_invoke_raises():
    """A subclass missing invoke() cannot be instantiated."""
    with pytest.raises(TypeError):
        MissingInvokeAdapter()  # type: ignore[abstract]


def test_missing_build_config_file_raises():
    """A subclass missing build_config_file() cannot be instantiated."""
    with pytest.raises(TypeError):
        MissingBuildConfigAdapter()  # type: ignore[abstract]


def test_missing_parse_system_prompt_file_raises():
    """A subclass missing parse_system_prompt_file() cannot be instantiated."""
    with pytest.raises(TypeError):
        MissingParsePromptAdapter()  # type: ignore[abstract]


def test_full_adapter_instantiates():
    """A fully concrete subclass can be instantiated."""
    adapter = FullAdapter()
    assert isinstance(adapter, RuntimeAdapter)


async def test_full_adapter_invoke():
    """invoke() returns a (result_text, tool_calls) tuple."""
    adapter = FullAdapter()
    result_text, tool_calls = await adapter.invoke(
        prompt="hello",
        system_prompt="you are helpful",
        mcp_servers={},
        env={},
    )
    assert result_text == "ok"
    assert tool_calls == []


def test_full_adapter_build_config_file(tmp_path: Path):
    """build_config_file() returns a Path."""
    adapter = FullAdapter()
    config_path = adapter.build_config_file(mcp_servers={}, tmp_dir=tmp_path)
    assert isinstance(config_path, Path)
    assert config_path == tmp_path / "config.json"


def test_full_adapter_parse_system_prompt_file(tmp_path: Path):
    """parse_system_prompt_file() returns a string."""
    adapter = FullAdapter()
    prompt = adapter.parse_system_prompt_file(config_dir=tmp_path)
    assert prompt == "system prompt"


# ---------------------------------------------------------------------------
# Registry / get_adapter tests
# ---------------------------------------------------------------------------


def test_get_adapter_claude_code():
    """get_adapter('claude-code') returns ClaudeCodeAdapter."""
    cls = get_adapter("claude-code")
    assert cls is ClaudeCodeAdapter


def test_get_adapter_codex():
    """get_adapter('codex') returns CodexAdapter."""
    cls = get_adapter("codex")
    assert cls is CodexAdapter


def test_get_adapter_gemini():
    """get_adapter('gemini') returns GeminiAdapter."""
    cls = get_adapter("gemini")
    assert cls is GeminiAdapter


def test_get_adapter_unknown_raises():
    """get_adapter() raises ValueError for unregistered type strings."""
    with pytest.raises(ValueError, match="Unknown runtime type 'unknown-runtime'"):
        get_adapter("unknown-runtime")


def test_get_adapter_error_lists_available():
    """The ValueError message includes the available adapter types."""
    with pytest.raises(ValueError, match="claude-code") as exc_info:
        get_adapter("nope")
    msg = str(exc_info.value)
    assert "codex" in msg
    assert "gemini" in msg


def test_register_custom_adapter():
    """register_adapter() allows adding new runtime types at runtime."""
    register_adapter("custom", FullAdapter)
    assert get_adapter("custom") is FullAdapter


# ---------------------------------------------------------------------------
# Stub adapter tests — verify they are proper subclasses but not yet usable
# ---------------------------------------------------------------------------


def test_stub_adapters_are_runtime_adapters():
    """All stub adapters are subclasses of RuntimeAdapter."""
    assert issubclass(ClaudeCodeAdapter, RuntimeAdapter)
    assert issubclass(CodexAdapter, RuntimeAdapter)
    assert issubclass(GeminiAdapter, RuntimeAdapter)


def test_stub_adapters_instantiate():
    """Stub adapters can be instantiated (they are concrete)."""
    assert ClaudeCodeAdapter()
    assert CodexAdapter()
    assert GeminiAdapter()


async def test_stub_invoke_raises_not_implemented():
    """Stub adapters raise NotImplementedError on invoke()."""
    for adapter_cls in (ClaudeCodeAdapter, CodexAdapter):
        adapter = adapter_cls()
        with pytest.raises(NotImplementedError):
            await adapter.invoke(
                prompt="test",
                system_prompt="test",
                mcp_servers={},
                env={},
            )


def test_stub_build_config_raises_not_implemented(tmp_path: Path):
    """Stub adapters raise NotImplementedError on build_config_file()."""
    for adapter_cls in (ClaudeCodeAdapter, CodexAdapter):
        adapter = adapter_cls()
        with pytest.raises(NotImplementedError):
            adapter.build_config_file(mcp_servers={}, tmp_dir=tmp_path)


def test_stub_parse_prompt_raises_not_implemented(tmp_path: Path):
    """Stub adapters raise NotImplementedError on parse_system_prompt_file()."""
    for adapter_cls in (ClaudeCodeAdapter, CodexAdapter):
        adapter = adapter_cls()
        with pytest.raises(NotImplementedError):
            adapter.parse_system_prompt_file(config_dir=tmp_path)


# ---------------------------------------------------------------------------
# Import path tests
# ---------------------------------------------------------------------------


def test_importable_from_butlers_core_runtimes():
    """RuntimeAdapter and get_adapter are importable from butlers.core.runtimes."""
    from butlers.core.runtimes import RuntimeAdapter as RA
    from butlers.core.runtimes import get_adapter as ga

    assert RA is RuntimeAdapter
    assert ga is get_adapter
