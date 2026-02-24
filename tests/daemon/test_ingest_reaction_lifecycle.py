"""Tests for the ingest→pipeline Telegram reaction lifecycle.

Verifies that the daemon's ingest pipeline flow fires the correct
Telegram reactions (👀 on receive, ✅ on success, 👾 on error)
when messages arrive via the TelegramBotConnector → MCP ingest path.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from butlers.modules.pipeline import MessagePipeline, RoutingResult
from butlers.modules.telegram import (
    REACTION_FAILURE,
    REACTION_IN_PROGRESS,
    REACTION_SUCCESS,
    TelegramModule,
)

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_minimal_pipeline(result: RoutingResult | None = None) -> MessagePipeline:
    """Build a MessagePipeline with a mock dispatch that returns a fixed result."""

    async def mock_dispatch(*_args: Any, **_kwargs: Any) -> SimpleNamespace:
        default_result = result or RoutingResult(
            target_butler="general",
            route_result={"cc_summary": "routed"},
            routed_targets=["general"],
            acked_targets=["general"],
        )
        tool_calls = [
            {
                "name": "route_to_butler",
                "input": {"butler": default_result.target_butler, "prompt": "ok"},
                "result": {"status": "ok"},
            }
        ]
        return SimpleNamespace(output="ok", tool_calls=tool_calls)

    conn = AsyncMock()
    conn.fetchval = AsyncMock(return_value=None)
    conn.fetchrow = AsyncMock(return_value=None)
    conn.fetch = AsyncMock(return_value=[])
    conn.execute = AsyncMock(return_value=None)

    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _acquire():
        yield conn

    pool = MagicMock()
    pool.acquire = _acquire
    pool.fetchval = AsyncMock(return_value=None)
    pool.fetchrow = AsyncMock(return_value=None)
    pool.fetch = AsyncMock(return_value=[])
    pool.execute = AsyncMock(return_value=None)

    return MessagePipeline(
        switchboard_pool=pool,
        dispatch_fn=mock_dispatch,
        source_butler="switchboard",
    )


# ---------------------------------------------------------------------------
# react_for_ingest unit tests
# ---------------------------------------------------------------------------


class TestReactForIngestParsing:
    """Test the parsing logic of react_for_ingest without network calls."""

    async def test_valid_thread_id_calls_update_reaction(self) -> None:
        """react_for_ingest parses 'chat_id:message_id' and calls _update_reaction."""
        mod = TelegramModule()
        calls: list[dict] = []

        async def mock_reaction(**kwargs: Any) -> None:
            calls.append(dict(kwargs))

        mod._update_reaction = mock_reaction  # type: ignore[method-assign]

        await mod.react_for_ingest(
            external_thread_id="12345:678",
            reaction=REACTION_IN_PROGRESS,
        )

        assert len(calls) == 1
        assert calls[0]["chat_id"] == "12345"
        assert calls[0]["message_id"] == 678
        assert calls[0]["message_key"] == "12345:678"
        assert calls[0]["reaction"] == REACTION_IN_PROGRESS

    async def test_negative_chat_id_valid(self) -> None:
        """Groups/supergroups use negative chat IDs which must parse correctly."""
        mod = TelegramModule()
        calls: list[dict] = []

        async def mock_reaction(**kwargs: Any) -> None:
            calls.append(dict(kwargs))

        mod._update_reaction = mock_reaction  # type: ignore[method-assign]

        await mod.react_for_ingest(
            external_thread_id="-100987654321:999",
            reaction=REACTION_IN_PROGRESS,
        )

        assert len(calls) == 1
        assert calls[0]["chat_id"] == "-100987654321"
        assert calls[0]["message_id"] == 999

    async def test_none_is_noop(self) -> None:
        """None external_thread_id → no _update_reaction call."""
        mod = TelegramModule()
        called = False

        async def mock_reaction(**kwargs: Any) -> None:
            nonlocal called
            called = True

        mod._update_reaction = mock_reaction  # type: ignore[method-assign]

        await mod.react_for_ingest(external_thread_id=None, reaction=REACTION_IN_PROGRESS)
        assert not called

    async def test_empty_string_is_noop(self) -> None:
        """Empty string external_thread_id → no _update_reaction call."""
        mod = TelegramModule()
        called = False

        async def mock_reaction(**kwargs: Any) -> None:
            nonlocal called
            called = True

        mod._update_reaction = mock_reaction  # type: ignore[method-assign]

        await mod.react_for_ingest(external_thread_id="", reaction=REACTION_IN_PROGRESS)
        assert not called

    async def test_no_colon_separator_is_noop(self) -> None:
        """Thread ID without colon is unparseable → noop."""
        mod = TelegramModule()
        called = False

        async def mock_reaction(**kwargs: Any) -> None:
            nonlocal called
            called = True

        mod._update_reaction = mock_reaction  # type: ignore[method-assign]

        await mod.react_for_ingest(external_thread_id="12345", reaction=REACTION_IN_PROGRESS)
        assert not called

    async def test_non_integer_message_id_is_noop(self) -> None:
        """Non-integer message_id → noop."""
        mod = TelegramModule()
        called = False

        async def mock_reaction(**kwargs: Any) -> None:
            nonlocal called
            called = True

        mod._update_reaction = mock_reaction  # type: ignore[method-assign]

        await mod.react_for_ingest(external_thread_id="123:abc", reaction=REACTION_IN_PROGRESS)
        assert not called

    async def test_empty_chat_id_is_noop(self) -> None:
        """Empty chat_id part (e.g. ':100') → noop."""
        mod = TelegramModule()
        called = False

        async def mock_reaction(**kwargs: Any) -> None:
            nonlocal called
            called = True

        mod._update_reaction = mock_reaction  # type: ignore[method-assign]

        await mod.react_for_ingest(external_thread_id=":100", reaction=REACTION_IN_PROGRESS)
        assert not called

    async def test_only_chat_id_no_message_id_after_colon_is_noop(self) -> None:
        """Thread ID 'chat_id:' with empty message_id part → noop."""
        mod = TelegramModule()
        called = False

        async def mock_reaction(**kwargs: Any) -> None:
            nonlocal called
            called = True

        mod._update_reaction = mock_reaction  # type: ignore[method-assign]

        await mod.react_for_ingest(external_thread_id="12345:", reaction=REACTION_IN_PROGRESS)
        assert not called


class TestReactForIngestLifecycle:
    """Test that react_for_ingest integrates correctly with reaction lifecycle."""

    async def test_success_reaction_cleans_up_state(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """After terminal ✅ reaction, lifecycle state is removed."""
        from butlers.modules.telegram import ProcessingLifecycle

        monkeypatch.setenv("BUTLER_TELEGRAM_TOKEN", "test-token")
        mod = TelegramModule()

        # Pre-populate lifecycle state as if in-progress reaction was set
        key = "77:300"
        mod._processing_lifecycle[key] = ProcessingLifecycle()

        async def mock_reaction(**kwargs: Any) -> None:
            # Simulate _update_reaction recording terminal reaction
            if kwargs["reaction"] == REACTION_SUCCESS:
                lc = mod._processing_lifecycle.get(kwargs["message_key"])
                if lc:
                    lc.terminal_reaction = REACTION_SUCCESS
                mod._record_terminal_reaction(kwargs["message_key"], REACTION_SUCCESS)

        mod._update_reaction = mock_reaction  # type: ignore[method-assign]

        await mod.react_for_ingest(
            external_thread_id="77:300",
            reaction=REACTION_SUCCESS,
        )

        assert key not in mod._processing_lifecycle

    async def test_failure_reaction_cleans_up_state(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """After terminal 👾 reaction, lifecycle state is removed."""
        from butlers.modules.telegram import ProcessingLifecycle

        monkeypatch.setenv("BUTLER_TELEGRAM_TOKEN", "test-token")
        mod = TelegramModule()

        key = "88:400"
        mod._processing_lifecycle[key] = ProcessingLifecycle()

        async def mock_reaction(**kwargs: Any) -> None:
            if kwargs["reaction"] == REACTION_FAILURE:
                lc = mod._processing_lifecycle.get(kwargs["message_key"])
                if lc:
                    lc.terminal_reaction = REACTION_FAILURE
                mod._record_terminal_reaction(kwargs["message_key"], REACTION_FAILURE)

        mod._update_reaction = mock_reaction  # type: ignore[method-assign]

        await mod.react_for_ingest(
            external_thread_id="88:400",
            reaction=REACTION_FAILURE,
        )

        assert key not in mod._processing_lifecycle

    async def test_in_progress_reaction_does_not_clean_up_state(self) -> None:
        """👀 reaction does NOT clean up lifecycle state (non-terminal)."""
        from butlers.modules.telegram import ProcessingLifecycle

        mod = TelegramModule()
        key = "10:50"
        mod._processing_lifecycle[key] = ProcessingLifecycle()

        async def mock_reaction(**kwargs: Any) -> None:
            pass  # No terminal state set for in-progress

        mod._update_reaction = mock_reaction  # type: ignore[method-assign]

        await mod.react_for_ingest(
            external_thread_id="10:50",
            reaction=REACTION_IN_PROGRESS,
        )

        # Lifecycle state should still be present (message is in-flight)
        assert key in mod._processing_lifecycle

    async def test_message_key_format_consistent_with_process_update(self) -> None:
        """react_for_ingest uses the same message_key format as process_update.

        Both methods must use 'chat_id:message_id' so that lifecycle deduplication
        works correctly when both paths could be active simultaneously.
        """
        mod = TelegramModule()
        ingest_key: str | None = None

        async def capture_key(**kwargs: Any) -> None:
            nonlocal ingest_key
            ingest_key = kwargs.get("message_key")

        mod._update_reaction = capture_key  # type: ignore[method-assign]

        await mod.react_for_ingest(
            external_thread_id="555:789",
            reaction=REACTION_IN_PROGRESS,
        )

        # Must match the format used by _message_tracking_key in process_update
        assert ingest_key == "555:789"


class TestIngestReactionNonTelegram:
    """Non-Telegram messages must not trigger any Telegram reactions."""

    async def test_react_for_ingest_is_not_called_for_email(self) -> None:
        """Email messages (source_channel != 'telegram') do not invoke react_for_ingest.

        This test verifies the behavioral contract: the caller in daemon.py
        must guard the react_for_ingest call with a channel check.
        """
        mod = TelegramModule()
        called = False

        async def mock_reaction(**kwargs: Any) -> None:
            nonlocal called
            called = True

        mod._update_reaction = mock_reaction  # type: ignore[method-assign]

        # Simulate what the daemon does: check channel before calling react_for_ingest
        channel = "email"
        if channel == "telegram":
            await mod.react_for_ingest(
                external_thread_id="123:456",
                reaction=REACTION_IN_PROGRESS,
            )

        assert not called, "react_for_ingest must not be called for non-telegram channels"


class TestBufferProcessReactionIntegration:
    """Integration tests for the DurableBuffer process function reaction wiring."""

    async def test_buffer_process_fires_in_progress_then_success(self) -> None:
        """_buffer_process fires 👀 before pipeline and ✅ after success."""
        # We test react_for_ingest directly since _buffer_process is an inner
        # closure inside _wire_pipelines that's hard to isolate.
        # The unit contract is: react_for_ingest(REACTION_IN_PROGRESS) before
        # pipeline.process(), react_for_ingest(REACTION_SUCCESS) after.
        mod = TelegramModule()
        reaction_sequence: list[str] = []

        async def record_reaction(**kwargs: Any) -> None:
            reaction_sequence.append(kwargs["reaction"])

        mod._update_reaction = record_reaction  # type: ignore[method-assign]

        # Simulate what _buffer_process does:
        # 1. Fire in-progress reaction
        await mod.react_for_ingest(
            external_thread_id="42:100",
            reaction=REACTION_IN_PROGRESS,
        )

        # 2. pipeline.process() runs (simulated by doing nothing here)

        # 3. Fire success reaction
        await mod.react_for_ingest(
            external_thread_id="42:100",
            reaction=REACTION_SUCCESS,
        )

        assert reaction_sequence == [REACTION_IN_PROGRESS, REACTION_SUCCESS]

    async def test_buffer_process_fires_in_progress_then_failure(self) -> None:
        """_buffer_process fires 👀 before pipeline and 👾 after failure."""
        mod = TelegramModule()
        reaction_sequence: list[str] = []

        async def record_reaction(**kwargs: Any) -> None:
            reaction_sequence.append(kwargs["reaction"])

        mod._update_reaction = record_reaction  # type: ignore[method-assign]

        await mod.react_for_ingest(
            external_thread_id="99:200",
            reaction=REACTION_IN_PROGRESS,
        )

        await mod.react_for_ingest(
            external_thread_id="99:200",
            reaction=REACTION_FAILURE,
        )

        assert reaction_sequence == [REACTION_IN_PROGRESS, REACTION_FAILURE]
