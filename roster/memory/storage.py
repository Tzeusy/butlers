"""Core memory storage operations for the Memory Butler.

Provides async functions for storing episodes, facts, and rules in the
memory database.  All functions accept an asyncpg connection pool and
use the EmbeddingEngine for semantic vector generation.
"""

from __future__ import annotations

import importlib.util
import json
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from asyncpg import Pool

# ---------------------------------------------------------------------------
# Load sibling modules from disk (roster/ is not a Python package).
# ---------------------------------------------------------------------------

_MODULE_DIR = Path(__file__).resolve().parent


def _load_module(name: str):
    path = _MODULE_DIR / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_embedding_mod = _load_module("embedding")
_search_mod = _load_module("search_vector")

EmbeddingEngine = _embedding_mod.EmbeddingEngine
preprocess_text = _search_mod.preprocess_text
tsvector_sql = _search_mod.tsvector_sql

# Default episode time-to-live.
_DEFAULT_EPISODE_TTL_DAYS = 7

# ---------------------------------------------------------------------------
# Permanence -> decay-rate mapping (from butler.toml)
# ---------------------------------------------------------------------------
_PERMANENCE_DECAY: dict[str, float] = {
    "permanent": 0.0,
    "stable": 0.002,
    "standard": 0.008,
    "volatile": 0.03,
    "ephemeral": 0.1,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def store_episode(
    pool: Pool,
    content: str,
    butler: str,
    embedding_engine: EmbeddingEngine,
    *,
    session_id: uuid.UUID | None = None,
    importance: float = 5.0,
    metadata: dict | None = None,
) -> uuid.UUID:
    """Store a raw episode from a butler CC session.

    Generates both a semantic embedding and a full-text search vector for the
    content, then inserts a row into the ``episodes`` table.

    Args:
        pool: asyncpg connection pool for the memory database.
        content: Raw episode text content.
        butler: Name of the source butler.
        embedding_engine: EmbeddingEngine instance for generating vectors.
        session_id: Optional UUID of the source CC session.
        importance: Importance rating (default 5.0).
        metadata: Optional JSONB metadata dict.

    Returns:
        The UUID of the newly created episode row.
    """
    episode_id = uuid.uuid4()
    embedding = embedding_engine.embed(content)
    search_text = preprocess_text(content)
    expires_at = datetime.now(UTC) + timedelta(days=_DEFAULT_EPISODE_TTL_DAYS)

    sql = f"""
        INSERT INTO episodes (id, butler, session_id, content, embedding, search_vector,
                              importance, expires_at, metadata)
        VALUES ($1, $2, $3, $4, $5, {tsvector_sql("$6")}, $7, $8, $9)
    """

    meta_json = json.dumps(metadata or {})

    await pool.execute(
        sql,
        episode_id,
        butler,
        session_id,
        content,
        str(embedding),  # pgvector accepts string format '[1.0, 2.0, ...]'
        search_text,
        importance,
        expires_at,
        meta_json,
    )

    return episode_id


async def store_fact(
    pool: Pool,
    subject: str,
    predicate: str,
    content: str,
    embedding_engine: EmbeddingEngine,
    *,
    importance: float = 5.0,
    permanence: str = "standard",
    scope: str = "global",
    tags: list[str] | None = None,
    source_butler: str | None = None,
    source_episode_id: uuid.UUID | None = None,
    metadata: dict | None = None,
) -> uuid.UUID:
    """Store a distilled fact with optional supersession.

    If an active fact with the same ``(subject, predicate)`` already exists:

    1. Set the old fact's ``validity`` to ``'superseded'``.
    2. Link the new fact to the old one via ``supersedes_id``.
    3. Create a ``memory_links`` row with ``relation='supersedes'``.

    Returns:
        The UUID of the newly created fact.
    """
    fact_id = uuid.uuid4()
    embedding = embedding_engine.embed(content)
    search_text = preprocess_text(content)
    decay_rate = _PERMANENCE_DECAY.get(permanence, 0.008)
    now = datetime.now(UTC)
    tags_json = json.dumps(tags or [])
    meta_json = json.dumps(metadata or {})

    async with pool.acquire() as conn:
        async with conn.transaction():
            # Check for existing active fact with same subject+predicate
            existing = await conn.fetchrow(
                "SELECT id FROM facts "
                "WHERE subject = $1 AND predicate = $2 AND validity = 'active'",
                subject,
                predicate,
            )

            supersedes_id = None
            if existing:
                old_id = existing["id"]
                supersedes_id = old_id
                # Mark old fact as superseded
                await conn.execute(
                    "UPDATE facts SET validity = 'superseded' WHERE id = $1",
                    old_id,
                )

            # Insert new fact
            sql = f"""
                INSERT INTO facts (
                    id, subject, predicate, content, embedding, search_vector,
                    importance, confidence, decay_rate, permanence, source_butler,
                    source_episode_id, supersedes_id, validity, scope,
                    created_at, last_confirmed_at, tags, metadata
                )
                VALUES (
                    $1, $2, $3, $4, $5, {tsvector_sql("$6")},
                    $7, $8, $9, $10, $11,
                    $12, $13, 'active', $14,
                    $15, $15, $16, $17
                )
            """
            await conn.execute(
                sql,
                fact_id,
                subject,
                predicate,
                content,
                str(embedding),
                search_text,
                importance,
                1.0,  # confidence
                decay_rate,
                permanence,
                source_butler,
                source_episode_id,
                supersedes_id,
                scope,
                now,
                tags_json,
                meta_json,
            )

            # Create supersedes link if applicable
            if supersedes_id:
                await conn.execute(
                    "INSERT INTO memory_links "
                    "(source_type, source_id, target_type, target_id, relation) "
                    "VALUES ('fact', $1, 'fact', $2, 'supersedes')",
                    fact_id,
                    supersedes_id,
                )

    return fact_id


async def store_rule(
    pool: Pool,
    content: str,
    embedding_engine: EmbeddingEngine,
    *,
    scope: str = "global",
    tags: list[str] | None = None,
    source_butler: str | None = None,
    source_episode_id: uuid.UUID | None = None,
    metadata: dict | None = None,
) -> uuid.UUID:
    """Store a new behavioral rule as a candidate.

    Rules start as candidates with confidence=0.5 and effectiveness_score=0.0.
    They progress through maturity levels (candidate -> established -> proven)
    as they accumulate successful applications.

    Args:
        pool: asyncpg connection pool for the memory database.
        content: The rule description text.
        embedding_engine: EmbeddingEngine for generating semantic vectors.
        scope: Visibility scope ('global' or butler-specific).
        tags: Optional list of string tags.
        source_butler: Name of the butler that proposed this rule.
        source_episode_id: Optional source episode UUID.
        metadata: Optional JSONB metadata dict.

    Returns:
        The UUID of the newly created rule.
    """
    rule_id = uuid.uuid4()
    embedding = embedding_engine.embed(content)
    search_text = preprocess_text(content)
    now = datetime.now(UTC)
    tags_json = json.dumps(tags or [])
    meta_json = json.dumps(metadata or {})

    sql = f"""
        INSERT INTO rules (id, content, embedding, search_vector, scope, maturity,
                           confidence, decay_rate, effectiveness_score,
                           applied_count, success_count, harmful_count,
                           source_episode_id, source_butler, created_at, tags, metadata)
        VALUES ($1, $2, $3, {tsvector_sql("$4")}, $5, 'candidate',
                0.5, 0.01, 0.0,
                0, 0, 0,
                $6, $7, $8, $9, $10)
    """

    await pool.execute(
        sql,
        rule_id,
        content,
        str(embedding),
        search_text,
        scope,
        source_episode_id,
        source_butler,
        now,
        tags_json,
        meta_json,
    )

    return rule_id


# ---------------------------------------------------------------------------
# Memory retrieval with reference bumping
# ---------------------------------------------------------------------------

_VALID_MEMORY_TYPES = frozenset({"episode", "fact", "rule"})

# Map memory types to their table names
_TYPE_TABLE: dict[str, str] = {
    "episode": "episodes",
    "fact": "facts",
    "rule": "rules",
}


async def get_memory(
    pool: Pool,
    memory_type: str,
    memory_id: uuid.UUID,
) -> dict | None:
    """Retrieve a single memory by type and UUID, bumping its reference count.

    Atomically increments ``reference_count`` by 1 and sets
    ``last_referenced_at`` to now. Returns the full record as a dict,
    or ``None`` if not found.

    Args:
        pool: asyncpg connection pool.
        memory_type: One of 'episode', 'fact', 'rule'.
        memory_id: The UUID of the memory item.

    Returns:
        A dict of the full record, or None if not found.

    Raises:
        ValueError: If memory_type is invalid.
    """
    if memory_type not in _VALID_MEMORY_TYPES:
        raise ValueError(
            f"Invalid memory_type: {memory_type!r}. Must be one of {sorted(_VALID_MEMORY_TYPES)}"
        )

    table = _TYPE_TABLE[memory_type]

    # Bump reference_count and last_referenced_at, returning the updated row
    row = await pool.fetchrow(
        f"UPDATE {table} "
        f"SET reference_count = reference_count + 1, last_referenced_at = now() "
        f"WHERE id = $1 "
        f"RETURNING *",
        memory_id,
    )

    if row is None:
        return None

    return dict(row)
