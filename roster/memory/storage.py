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
