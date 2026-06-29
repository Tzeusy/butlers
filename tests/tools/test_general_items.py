"""Unit tests for General collection item helpers."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


@pytest.mark.asyncio
async def test_item_create_auto_creates_collection_before_insert() -> None:
    """item_create should not fail when the target collection is new."""
    from butlers.tools.general.items import item_create

    expected_id = uuid.uuid4()
    pool = SimpleNamespace(fetchval=AsyncMock(return_value=expected_id))

    item_id = await item_create(
        pool,
        "episodes",
        {"summary": "Captured note"},
        tags=["auto-created"],
    )

    assert item_id == expected_id
    query, *args = pool.fetchval.await_args.args
    assert "INSERT INTO collections (name)" in query
    assert "ON CONFLICT (name) DO UPDATE" in query
    assert "INSERT INTO collection_items" in query
    assert args == [
        "episodes",
        {"summary": "Captured note"},
        ["auto-created"],
    ]
