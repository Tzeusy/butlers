"""Search functions for the Memory butler.

Provides semantic (vector), keyword (full-text), and hybrid (RRF-fused)
search across the episodes, facts, and rules tables.

All functions accept an asyncpg connection pool and return lists of dicts.
"""

from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from asyncpg import Pool

# ---------------------------------------------------------------------------
# Load sibling modules from disk (roster/ is not a Python package).
# ---------------------------------------------------------------------------

_MODULE_DIR = Path(__file__).resolve().parent


def _load_module(name: str):
    spec = importlib.util.spec_from_file_location(name, _MODULE_DIR / f"{name}.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_search_vector_mod = _load_module("search_vector")
preprocess_search_query = _search_vector_mod.preprocess_search_query

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_VALID_TABLES = frozenset({"episodes", "facts", "rules"})

# RRF fusion constant (standard value from the original RRF paper).
_RRF_K = 60


# ---------------------------------------------------------------------------
# Table-specific SQL filter fragments
# ---------------------------------------------------------------------------


def _scope_filter(table: str, scope: str | None, params: list) -> str:
    """Return a SQL AND clause for scope/butler filtering.

    Appends bind values to *params* and returns a SQL fragment that can be
    concatenated after a WHERE clause.  Returns ``""`` when no filter is
    needed.
    """
    if scope is None:
        return ""

    idx = len(params) + 1
    if table == "episodes":
        params.append(scope)
        return f" AND butler = ${idx}"
    else:
        # facts and rules use the scope column
        params.append(scope)
        return f" AND scope = ${idx}"


def _validity_filter(table: str) -> str:
    """Return a SQL AND clause enforcing validity/forgotten constraints."""
    if table == "facts":
        return " AND validity = 'active'"
    if table == "rules":
        return " AND (metadata->>'forgotten')::boolean IS NOT TRUE"
    return ""


# ---------------------------------------------------------------------------
# Semantic search (cosine distance via pgvector)
# ---------------------------------------------------------------------------


async def semantic_search(
    pool: Pool,
    query_embedding: list[float],
    table: str,
    *,
    limit: int = 10,
    scope: str | None = None,
) -> list[dict]:
    """Search *table* by cosine similarity to *query_embedding*.

    Uses pgvector's ``<=>`` cosine distance operator.  Lower distance means
    higher similarity; we return ``similarity = 1 - distance``.

    Args:
        pool: asyncpg connection pool.
        query_embedding: 384-dimensional float vector.
        table: One of ``'episodes'``, ``'facts'``, ``'rules'``.
        limit: Maximum number of results.
        scope: Optional scope/butler filter.

    Returns:
        List of row dicts ordered by similarity descending, each with an
        added ``similarity`` key.

    Raises:
        ValueError: If *table* is not one of the valid table names.
    """
    if table not in _VALID_TABLES:
        raise ValueError(f"Invalid table: {table!r}. Must be one of {sorted(_VALID_TABLES)}")

    params: list = [str(query_embedding)]
    scope_clause = _scope_filter(table, scope, params)
    validity_clause = _validity_filter(table)
    limit_idx = len(params) + 1
    params.append(limit)

    sql = (
        f"SELECT *, 1 - (embedding <=> $1) AS similarity"
        f" FROM {table}"
        f" WHERE TRUE{validity_clause}{scope_clause}"
        f" ORDER BY embedding <=> $1"
        f" LIMIT ${limit_idx}"
    )

    rows = await pool.fetch(sql, *params)
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Keyword search (PostgreSQL full-text search)
# ---------------------------------------------------------------------------


async def keyword_search(
    pool: Pool,
    query_text: str,
    table: str,
    *,
    limit: int = 10,
    scope: str | None = None,
) -> list[dict]:
    """Search *table* using PostgreSQL full-text search.

    Preprocesses *query_text* via :func:`preprocess_search_query`, then
    matches against the ``search_vector`` column using ``plainto_tsquery``.
    Results are ranked by ``ts_rank``.

    Args:
        pool: asyncpg connection pool.
        query_text: User search query text.
        table: One of ``'episodes'``, ``'facts'``, ``'rules'``.
        limit: Maximum number of results.
        scope: Optional scope/butler filter.

    Returns:
        List of row dicts ordered by text rank descending, each with an
        added ``rank`` key.

    Raises:
        ValueError: If *table* is not one of the valid table names.
    """
    if table not in _VALID_TABLES:
        raise ValueError(f"Invalid table: {table!r}. Must be one of {sorted(_VALID_TABLES)}")

    cleaned = preprocess_search_query(query_text)
    if not cleaned:
        return []

    params: list = [cleaned]
    scope_clause = _scope_filter(table, scope, params)
    validity_clause = _validity_filter(table)
    limit_idx = len(params) + 1
    params.append(limit)

    sql = (
        f"SELECT *, ts_rank(search_vector, plainto_tsquery('english', $1)) AS rank"
        f" FROM {table}"
        f" WHERE search_vector @@ plainto_tsquery('english', $1)"
        f"{validity_clause}{scope_clause}"
        f" ORDER BY rank DESC"
        f" LIMIT ${limit_idx}"
    )

    rows = await pool.fetch(sql, *params)
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Hybrid search (Reciprocal Rank Fusion)
# ---------------------------------------------------------------------------


async def hybrid_search(
    pool: Pool,
    query_text: str,
    query_embedding: list[float],
    table: str,
    *,
    limit: int = 10,
    scope: str | None = None,
) -> list[dict]:
    """Hybrid search combining semantic and keyword search via RRF.

    Runs both search methods, then fuses results using Reciprocal Rank
    Fusion.  Each result gets::

        rrf_score = 1/(k + semantic_rank) + 1/(k + keyword_rank)

    where ``k=60``.  Results appearing in only one list use
    ``rank = limit + 1`` for the missing dimension.

    Args:
        pool: asyncpg connection pool.
        query_text: User search text for keyword matching.
        query_embedding: 384-d vector for semantic matching.
        table: Table name (``'episodes'``, ``'facts'``, ``'rules'``).
        limit: Max results per search method and for final output.
        scope: Optional scope filter.

    Returns:
        List of dicts with ``rrf_score``, ``semantic_rank``, and
        ``keyword_rank`` added.  Ordered by ``rrf_score`` descending.

    Raises:
        ValueError: If *table* is not one of the valid table names.
    """
    if table not in _VALID_TABLES:
        raise ValueError(f"Invalid table: {table!r}. Must be one of {sorted(_VALID_TABLES)}")

    # Run both searches
    semantic_results = await semantic_search(
        pool,
        query_embedding,
        table,
        limit=limit,
        scope=scope,
    )
    keyword_results = await keyword_search(
        pool,
        query_text,
        table,
        limit=limit,
        scope=scope,
    )

    # Build rank maps keyed by id
    default_rank = limit + 1

    semantic_ranks: dict[uuid.UUID, int] = {}
    semantic_data: dict[uuid.UUID, dict] = {}
    for rank, row in enumerate(semantic_results, start=1):
        rid = row["id"]
        semantic_ranks[rid] = rank
        semantic_data[rid] = row

    keyword_ranks: dict[uuid.UUID, int] = {}
    keyword_data: dict[uuid.UUID, dict] = {}
    for rank, row in enumerate(keyword_results, start=1):
        rid = row["id"]
        keyword_ranks[rid] = rank
        keyword_data[rid] = row

    # Union all IDs
    all_ids = set(semantic_ranks.keys()) | set(keyword_ranks.keys())

    # Compute RRF scores
    fused: list[dict] = []
    for rid in all_ids:
        s_rank = semantic_ranks.get(rid, default_rank)
        k_rank = keyword_ranks.get(rid, default_rank)
        rrf_score = 1.0 / (_RRF_K + s_rank) + 1.0 / (_RRF_K + k_rank)

        # Use data from whichever search found it (prefer semantic)
        row = semantic_data.get(rid) or keyword_data[rid]
        result = dict(row)
        result["rrf_score"] = rrf_score
        result["semantic_rank"] = s_rank
        result["keyword_rank"] = k_rank
        fused.append(result)

    # Sort by RRF score descending, then by semantic rank ascending as tiebreaker
    fused.sort(key=lambda r: (-r["rrf_score"], r["semantic_rank"]))

    return fused[:limit]
