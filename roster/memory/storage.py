"""Core memory storage operations for the Memory Butler."""

from __future__ import annotations

import importlib.util
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from asyncpg import Pool

# Load sibling modules from disk (roster/ is not a Python package)
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
