"""Integration tests for canonical async ingest across source connectors."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from butlers.modules.email import EmailModule
from butlers.modules.pipeline import MessagePipeline
from butlers.modules.telegram import TelegramModule

pytestmark = pytest.mark.unit


def _mock_pool() -> MagicMock:
    conn = AsyncMock()
    conn.fetchval = AsyncMock(side_effect=[101, 102, 103, 104, 105, 106])
    acquire_cm = AsyncMock()
    acquire_cm.__aenter__.return_value = conn
    acquire_cm.__aexit__.return_value = False

    pool = MagicMock()
    pool.acquire.return_value = acquire_cm
    return pool


async def _wait_for(condition, *, timeout: float = 1.5) -> None:
    deadline = time.perf_counter() + timeout
    while time.perf_counter() < deadline:
        if condition():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("Timed out waiting for condition")


async def test_telegram_and_email_share_canonical_non_blocking_ingest():
    """Telegram and Email adapters both return 202/request_id before routing completes."""

    async def classify_fn(pool, message, dispatch_fn):
        return "general"

    async def route_fn(pool, target, tool_name, args, source):
        await asyncio.sleep(0.25)
        return {"result": "ok"}

    pipeline = MessagePipeline(
        switchboard_pool=_mock_pool(),
        dispatch_fn=AsyncMock(),
        classify_fn=classify_fn,
        route_fn=route_fn,
    )

    telegram = TelegramModule()
    telegram.set_pipeline(pipeline)

    email = EmailModule()
    email.set_pipeline(pipeline)

    update = {"update_id": 9001, "message": {"message_id": 7, "text": "hello", "chat": {"id": 42}}}
    email_data = {
        "message_id": "email-7",
        "from": "sender@example.com",
        "subject": "Need help",
        "body": "Please route this",
    }

    started_at = time.perf_counter()
    telegram_receipt = await telegram.accept_update(update)
    email_receipt = await email.accept_incoming(email_data)
    elapsed = time.perf_counter() - started_at

    assert telegram_receipt is not None
    assert telegram_receipt["status_code"] == 202
    assert telegram_receipt["request_id"]

    assert email_receipt is not None
    assert email_receipt["status_code"] == 202
    assert email_receipt["request_id"]

    assert telegram_receipt["request_id"] != email_receipt["request_id"]
    assert elapsed < 0.20

    await _wait_for(lambda: len(telegram._routed_messages) == 1)
    await _wait_for(lambda: len(email._routed_messages) == 1)

    assert telegram._routed_messages[0].target_butler == "general"
    assert email._routed_messages[0].target_butler == "general"
