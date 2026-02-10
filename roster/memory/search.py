"""Search functions for the Memory Butler.

Provides keyword search across memory types using PostgreSQL full-text search.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from asyncpg import Pool

_MODULE_DIR = Path(__file__).resolve().parent


def _load_module(name: str):
    path = _MODULE_DIR / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_search_vector_mod = _load_module("search_vector")
preprocess_search_query = _search_vector_mod.preprocess_search_query

_VALID_TABLES = frozenset({"episodes", "facts", "rules"})
_SCOPED_TABLES = frozenset({"facts", "rules"})

# PostgreSQL text-search configuration
_TS_CONFIG = "english"


async def keyword_search(
    pool: Pool,
    query_text: str,
    table: str,
    *,
    limit: int = 10,
    scope: str | None = None,
) -> list[dict]:
    """Search by keyword using PostgreSQL full-text search.

    Uses plainto_tsquery for safe handling of user input (no special
    operator syntax required). Results are ranked by ts_rank.

    Args:
        pool: asyncpg connection pool.
        query_text: User search text (will be preprocessed).
        table: Table name ('episodes', 'facts', 'rules').
        limit: Max results (default 10).
        scope: Optional scope filter (only for facts/rules).

    Returns:
        List of dicts with keys: all table columns plus 'rank'.
        Ordered by rank descending (best match first).

    Raises:
        ValueError: If table is invalid.
    """
    if table not in _VALID_TABLES:
        raise ValueError(f"Invalid table: {table!r}. Must be one of {sorted(_VALID_TABLES)}")

    cleaned_query = preprocess_search_query(query_text)
    if not cleaned_query:
        return []

    # Build WHERE clause
    conditions = [f"search_vector @@ plainto_tsquery('{_TS_CONFIG}', $1)"]
    params: list = [cleaned_query]
    param_idx = 2

    if scope is not None and table in _SCOPED_TABLES:
        conditions.append(f"scope = ${param_idx}")
        params.append(scope)
        param_idx += 1

    if table == "facts":
        conditions.append("validity = 'active'")

    if table == "rules":
        conditions.append("(metadata->>'forgotten')::boolean IS NOT TRUE")

    where = " AND ".join(conditions)

    sql = f"""
        SELECT *, ts_rank(search_vector, plainto_tsquery('{_TS_CONFIG}', $1)) AS rank
        FROM {table}
        WHERE {where}
        ORDER BY rank DESC
        LIMIT ${param_idx}
    """
    params.append(limit)

    rows = await pool.fetch(sql, *params)
    return [dict(r) for r in rows]
