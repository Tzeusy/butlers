"""Tests for 'healing' trigger source and session_set_healing_fingerprint.

Covers:
- TRIGGER_SOURCES frozenset includes 'healing'
- session_create accepts 'healing' as a valid trigger_source (no ValueError)
- session_set_healing_fingerprint is callable (no error on mock pool)
- _is_valid_trigger_source correctly validates 'healing'
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# TRIGGER_SOURCES constant and _is_valid_trigger_source
# ---------------------------------------------------------------------------


def test_trigger_sources_and_validation() -> None:
    """TRIGGER_SOURCES includes 'healing' and all originals; validation is correct."""
    from butlers.core.sessions import TRIGGER_SOURCES, _is_valid_trigger_source

    # 'healing' is present
    assert "healing" in TRIGGER_SOURCES

    # All original sources still present
    for source in ("tick", "external", "trigger", "route"):
        assert source in TRIGGER_SOURCES, f"Missing trigger source: {source}"

    # Validation
    assert _is_valid_trigger_source("healing") is True
    assert _is_valid_trigger_source("unknown") is False
    assert _is_valid_trigger_source("heal") is False
    assert _is_valid_trigger_source("healing:foo") is False


# ---------------------------------------------------------------------------
# session_create — healing trigger source is accepted
# ---------------------------------------------------------------------------


class _FakePool:
    """Fake asyncpg pool that captures fetchval/execute calls."""

    def __init__(self, *, return_id: uuid.UUID | None = None) -> None:
        self._return_id = return_id or uuid.uuid4()
        self.fetchval_calls: list[tuple[str, tuple]] = []
        self.execute_calls: list[tuple[str, tuple]] = []

    async def fetchval(self, sql: str, *args: Any) -> uuid.UUID:
        self.fetchval_calls.append((sql, args))
        return self._return_id

    async def execute(self, sql: str, *args: Any) -> str:
        self.execute_calls.append((sql, args))
        return "UPDATE 1"


async def test_session_create_healing_source() -> None:
    """session_create accepts 'healing'; rejects invalid sources with error mentioning 'healing'."""
    from butlers.core.sessions import session_create

    pool = _FakePool()
    request_id = str(uuid.uuid4())

    # 'healing' is valid — should not raise
    result = await session_create(
        pool,
        prompt="Healing agent investigating error abc123",
        trigger_source="healing",
        request_id=request_id,
    )
    assert result == pool._return_id
    assert len(pool.fetchval_calls) == 1

    # Invalid source — raises ValueError mentioning 'healing'
    with pytest.raises(ValueError, match="healing"):
        await session_create(
            pool,
            prompt="Test",
            trigger_source="not_valid",
            request_id=str(uuid.uuid4()),
        )


# ---------------------------------------------------------------------------
# session_set_healing_fingerprint
# ---------------------------------------------------------------------------


async def test_session_set_healing_fingerprint() -> None:
    """session_set_healing_fingerprint issues UPDATE; no raise on zero rows matched."""
    from butlers.core.sessions import session_set_healing_fingerprint

    pool = _FakePool()
    session_id = uuid.uuid4()
    fingerprint = "a" * 64

    await session_set_healing_fingerprint(pool, session_id, fingerprint)

    assert len(pool.execute_calls) == 1
    sql, args = pool.execute_calls[0]
    assert "healing_fingerprint" in sql
    assert session_id in args
    assert fingerprint in args

    # No raise on zero rows matched (same pool, different session)
    await session_set_healing_fingerprint(pool, uuid.uuid4(), "b" * 64)
