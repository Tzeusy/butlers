"""Memory writing tools — store episodes, facts, and rules."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from asyncpg import Pool

from butlers.tools.memory._helpers import _storage

logger = logging.getLogger(__name__)


async def memory_store_episode(
    pool: Pool,
    content: str,
    butler: str,
    *,
    session_id: str | None = None,
    importance: float = 5.0,
) -> dict[str, Any]:
    """Store a raw episode from a CC session.

    Delegates to the storage layer and returns an MCP-friendly dict with the
    new episode's ID and expiry timestamp.
    """
    result = await _storage.store_episode(
        pool, content, butler, session_id=session_id, importance=importance
    )
    return {
        "id": str(result["id"]),
        "expires_at": result["expires_at"].isoformat(),
    }


async def memory_store_fact(
    pool: Pool,
    embedding_engine,
    subject: str,
    predicate: str,
    content: str,
    *,
    importance: float = 5.0,
    permanence: str = "standard",
    scope: str = "global",
    tags: list[str] | None = None,
) -> dict[str, Any]:
    """Store a distilled fact, automatically superseding any existing match.

    Delegates to the storage layer and returns an MCP-friendly dict with the
    new fact's ID and the superseded fact's ID (if any).
    """
    result = await _storage.store_fact(
        pool,
        embedding_engine,
        subject,
        predicate,
        content,
        importance=importance,
        permanence=permanence,
        scope=scope,
        tags=tags,
    )
    return {
        "id": str(result["id"]),
        "superseded_id": (
            str(result.get("superseded_id")) if result.get("superseded_id") else None
        ),
    }


async def memory_store_rule(
    pool: Pool,
    embedding_engine,
    content: str,
    *,
    scope: str = "global",
    tags: list[str] | None = None,
) -> dict[str, Any]:
    """Store a new behavioral rule as a candidate.

    Delegates to the storage layer and returns an MCP-friendly dict with the
    new rule's ID.
    """
    result = await _storage.store_rule(
        pool, embedding_engine, content, scope=scope, tags=tags
    )
    return {"id": str(result["id"])}
