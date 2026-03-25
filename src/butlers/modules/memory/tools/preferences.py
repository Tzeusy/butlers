"""Memory preferences tools — retrieve user preferences from the facts store."""

from __future__ import annotations

import datetime as _dt
import logging
import math
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from asyncpg import Pool

logger = logging.getLogger(__name__)


def _compute_effective_confidence(row: dict[str, Any]) -> float:
    """Compute effective (decayed) confidence using the standard decay formula.

    Formula: confidence * exp(-decay_rate * days_elapsed)
    where days_elapsed = (now - last_confirmed_at or created_at) / 86400.

    When decay_rate is 0.0 (permanent), returns confidence unchanged.
    When last_confirmed_at and created_at are both None, returns 0.0.

    Args:
        row: Dict with keys: confidence, decay_rate, last_confirmed_at, created_at.

    Returns:
        Effective confidence float (0.0–1.0).
    """
    confidence = row.get("confidence", 1.0) or 1.0
    decay_rate = row.get("decay_rate", 0.0) or 0.0

    if decay_rate == 0.0:
        return confidence

    anchor = row.get("last_confirmed_at") or row.get("created_at")
    if anchor is None:
        return 0.0

    now = datetime.now(UTC)
    days_elapsed = max((now - anchor).total_seconds() / 86400.0, 0.0)
    return confidence * math.exp(-decay_rate * days_elapsed)


async def get_preferences(
    pool: Pool,
    *,
    scope: str | None = None,
    predicate_pattern: str | None = None,
) -> list[dict[str, Any]]:
    """Retrieve all active user preferences for the owner entity.

    Queries facts WHERE predicate LIKE 'preferences:%' AND validity = 'active'
    AND entity_id matches the owner entity resolved from shared.contacts.

    Args:
        pool: asyncpg connection pool.
        scope: Optional filter on the scope column (exact match, e.g. 'travel').
        predicate_pattern: Optional SQL LIKE pattern for the predicate column
            (e.g. 'preferences:health_%'). Must start with 'preferences:'.
            When omitted, defaults to 'preferences:%'.

    Returns:
        List of preference dicts ordered by predicate ASC. Each dict contains:
        - predicate (str)
        - value (str) — from the content column
        - scope (str)
        - importance (float)
        - permanence (str)
        - effective_confidence (float) — computed via decay formula
        - updated_at (str) — ISO-8601 timestamp from created_at
    """
    # Resolve owner entity_id from shared.contacts
    owner_entity_id = await _resolve_owner_entity_id(pool)
    if owner_entity_id is None:
        return []

    # Build query with optional filters
    params: list[Any] = [owner_entity_id]
    conditions = [
        "f.entity_id = $1",
        "f.validity = 'active'",
    ]

    # Apply predicate LIKE filter
    effective_pattern = predicate_pattern or "preferences:%"
    params.append(effective_pattern)
    conditions.append(f"f.predicate LIKE ${len(params)}")

    # Optional scope filter
    if scope is not None:
        params.append(scope)
        conditions.append(f"f.scope = ${len(params)}")

    where_clause = " AND ".join(conditions)
    sql = f"""
        SELECT
            f.predicate,
            f.content,
            f.scope,
            f.importance,
            f.permanence,
            f.confidence,
            f.decay_rate,
            f.last_confirmed_at,
            f.created_at
        FROM facts f
        WHERE {where_clause}
        ORDER BY f.predicate ASC
    """

    try:
        rows = await pool.fetch(sql, *params)
    except Exception:
        logger.debug("get_preferences query failed", exc_info=True)
        return []

    results = []
    for row in rows:
        row_dict = dict(row)
        eff_conf = _compute_effective_confidence(row_dict)
        created_at = row_dict.get("created_at")
        if isinstance(created_at, _dt.datetime):
            updated_at = created_at.isoformat()
        else:
            updated_at = str(created_at or "")
        results.append(
            {
                "predicate": row_dict["predicate"],
                "value": row_dict["content"],
                "scope": row_dict["scope"],
                "importance": row_dict["importance"],
                "permanence": row_dict["permanence"],
                "effective_confidence": round(eff_conf, 6),
                "updated_at": updated_at,
            }
        )
    return results


async def _resolve_owner_entity_id(pool: Pool) -> Any | None:
    """Resolve the owner entity UUID from shared.contacts.

    Looks up contacts WHERE roles @> '["owner"]' and returns the entity_id
    of the first match that has a non-null entity_id.

    Returns:
        UUID of the owner entity, or None if not found.
    """
    sql = """
        SELECT entity_id
        FROM shared.contacts
        WHERE roles @> '["owner"]'
          AND entity_id IS NOT NULL
        LIMIT 1
    """
    try:
        row = await pool.fetchrow(sql)
        return row["entity_id"] if row else None
    except Exception:
        logger.debug("Owner entity resolution failed", exc_info=True)
        return None
