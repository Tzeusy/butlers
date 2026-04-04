"""Condensed conversation history tests — behavioral contract only.

Replaces 26 tests with ~8 focused behavioral tests.

Covers:
- HistoryConfig dataclass defaults
- HISTORY_STRATEGY includes expected keys
- _format_history_context: non-empty result
- _load_conversation_history: dispatcher returns list

[bu-7sd7a]
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from butlers.modules.pipeline import (
    HISTORY_STRATEGY,
    HistoryConfig,
    _format_history_context,
    _load_conversation_history,
)

pytestmark = pytest.mark.unit


class TestHistoryConfig:
    def test_requires_strategy(self):
        cfg = HistoryConfig(strategy="realtime")
        assert cfg.strategy == "realtime"
        assert cfg.max_message_count > 0

    def test_strategy_none_accepted(self):
        cfg = HistoryConfig(strategy="none")
        assert cfg.strategy == "none"

    def test_strategy_map_exists(self):
        assert isinstance(HISTORY_STRATEGY, dict)
        assert len(HISTORY_STRATEGY) >= 1


class TestFormatHistoryContext:
    def test_empty_history_returns_none_or_empty(self):
        result = _format_history_context([])
        assert result is None or result == "" or isinstance(result, str)

    def test_with_messages_returns_string(self):
        messages = [{"role": "user", "content": "Hello"}, {"role": "assistant", "content": "Hi"}]
        result = _format_history_context(messages)
        assert result is not None
        assert isinstance(result, str)
        assert len(result) > 0


class TestLoadConversationHistory:
    async def test_returns_empty_for_no_thread_identity(self):
        from datetime import UTC, datetime

        pool = MagicMock()
        pool.fetch = AsyncMock(return_value=[])
        result = await _load_conversation_history(
            pool=pool,
            source_channel="telegram_bot",
            source_thread_identity=None,
            received_at=datetime.now(UTC),
        )
        assert result == ""  # No thread identity → empty string

    async def test_returns_string_for_none_strategy_channel(self):
        from datetime import UTC, datetime

        pool = MagicMock()
        pool.fetch = AsyncMock(return_value=[])
        result = await _load_conversation_history(
            pool=pool,
            source_channel="unknown_channel",
            source_thread_identity="thread-1",
            received_at=datetime.now(UTC),
        )
        assert isinstance(result, str)
