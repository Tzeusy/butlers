"""Stay in touch — cadence tracking and overdue contact detection."""

from __future__ import annotations

import uuid
from typing import Any

import asyncpg

from butlers.tools.relationship.contacts import _parse_contact
from butlers.tools.relationship.feed import _log_activity


async def stay_in_touch_set(
    pool: asyncpg.Pool,
    contact_id: uuid.UUID,
    frequency_days: int | None,
) -> dict[str, Any]:
    """Set or clear the stay-in-touch cadence for a contact.

    Pass frequency_days=None to clear the cadence (removes from overdue list).
    """
    row = await pool.fetchrow(
        """
        UPDATE contacts SET stay_in_touch_days = $2, updated_at = now()
        WHERE id = $1
        RETURNING *
        """,
        contact_id,
        frequency_days,
    )
    if row is None:
        raise ValueError(f"Contact {contact_id} not found")
    result = _parse_contact(row)
    if frequency_days is not None:
        await _log_activity(
            pool,
            contact_id,
            "stay_in_touch_set",
            f"Set stay-in-touch cadence to {frequency_days} days",
        )
    else:
        await _log_activity(
            pool, contact_id, "stay_in_touch_cleared", "Cleared stay-in-touch cadence"
        )
    return result


async def contacts_overdue(pool: asyncpg.Pool) -> list[dict[str, Any]]:
    """Return contacts whose last interaction exceeds their stay-in-touch cadence.

    Contacts with a cadence but no interactions are always overdue.
    Contacts with no cadence (NULL) are never returned.
    Archived contacts are excluded.

    Reads interactions from the SPO facts table (predicate='interaction') with
    a UNION fallback to the legacy interactions table if it still has data.
    """
    # Try SPO-first query; fall back to legacy interactions table if facts unavailable.
    try:
        rows = await pool.fetch(
            """
            WITH last_interactions AS (
                SELECT
                    c2.id AS contact_id,
                    MAX(f.valid_at) AS last_at
                FROM contacts c2
                LEFT JOIN facts f
                    ON f.subject = 'contact:' || c2.id::text
                   AND f.predicate = 'interaction'
                   AND f.scope = 'relationship'
                   AND f.validity = 'active'
                GROUP BY c2.id
            )
            SELECT
                c.*,
                li.last_at AS last_interaction_at,
                CASE
                    WHEN li.last_at IS NULL THEN NULL
                    ELSE EXTRACT(EPOCH FROM (now() - li.last_at)) / 86400.0
                END AS days_since_last_interaction
            FROM contacts c
            LEFT JOIN last_interactions li ON li.contact_id = c.id
            WHERE c.stay_in_touch_days IS NOT NULL
              AND c.listed = true
              AND (li.last_at IS NULL
                   OR li.last_at < now() - make_interval(days => c.stay_in_touch_days))
            ORDER BY c.first_name, c.last_name, c.nickname
            """
        )
    except asyncpg.UndefinedTableError:
        # facts table not yet present — fall back to legacy interactions table
        rows = await pool.fetch(
            """
            SELECT
                c.*,
                MAX(i.occurred_at) AS last_interaction_at,
                CASE
                    WHEN MAX(i.occurred_at) IS NULL THEN NULL
                    ELSE EXTRACT(EPOCH FROM (now() - MAX(i.occurred_at))) / 86400.0
                END AS days_since_last_interaction
            FROM contacts c
            LEFT JOIN interactions i ON c.id = i.contact_id
            WHERE c.stay_in_touch_days IS NOT NULL
              AND c.listed = true
            GROUP BY c.id
            HAVING MAX(i.occurred_at) IS NULL
                OR MAX(i.occurred_at) < now() - make_interval(days => c.stay_in_touch_days)
            ORDER BY c.first_name, c.last_name, c.nickname
            """
        )
    return [_parse_contact(row) for row in rows]
