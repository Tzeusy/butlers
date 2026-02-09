"""Relationship butler tools — personal CRM for contacts and interactions."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

import asyncpg

logger = logging.getLogger(__name__)

# Valid gift status pipeline (spec order)
_GIFT_STATUS_ORDER = ["idea", "searched", "found", "bought", "given"]


# ------------------------------------------------------------------
# Internal helper: activity feed
# ------------------------------------------------------------------


async def _log_activity(
    pool: asyncpg.Pool,
    contact_id: uuid.UUID,
    action: str,
    summary: str,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
) -> None:
    """Log an activity to the contact_feed table."""
    await pool.execute(
        """
        INSERT INTO contact_feed (contact_id, action, entity_type, entity_id, summary)
        VALUES ($1, $2, $3, $4, $5)
        """,
        contact_id,
        action,
        entity_type,
        entity_id,
        summary,
    )


async def feed_get(
    pool: asyncpg.Pool,
    contact_id: uuid.UUID | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Get activity feed entries, optionally filtered by contact."""
    if contact_id is not None:
        rows = await pool.fetch(
            """
            SELECT * FROM contact_feed
            WHERE contact_id = $1
            ORDER BY created_at DESC
            LIMIT $2 OFFSET $3
            """,
            contact_id,
            limit,
            offset,
        )
    else:
        rows = await pool.fetch(
            """
            SELECT * FROM contact_feed
            ORDER BY created_at DESC
            LIMIT $1 OFFSET $2
            """,
            limit,
            offset,
        )
    return [dict(row) for row in rows]


def _parse_contact(row: asyncpg.Record) -> dict[str, Any]:
    """Convert a contact row to a dict, parsing JSONB metadata if needed."""
    d = dict(row)
    if isinstance(d.get("metadata"), str):
        d["metadata"] = json.loads(d["metadata"])
    return d


# ------------------------------------------------------------------
# Contact CRUD
# ------------------------------------------------------------------


async def contact_create(
    pool: asyncpg.Pool,
    first_name: str | None = None,
    last_name: str | None = None,
    nickname: str | None = None,
    company: str | None = None,
    job_title: str | None = None,
    gender: str | None = None,
    pronouns: str | None = None,
    avatar_url: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a new contact with proper columns per spec."""
    row = await pool.fetchrow(
        """
        INSERT INTO contacts
            (first_name, last_name, nickname, company, job_title,
             gender, pronouns, avatar_url, metadata)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb)
        RETURNING *
        """,
        first_name,
        last_name,
        nickname,
        company,
        job_title,
        gender,
        pronouns,
        avatar_url,
        json.dumps(metadata or {}),
    )
    result = _parse_contact(row)
    display = first_name or nickname or last_name or "Unknown"
    await _log_activity(
        pool,
        result["id"],
        "contact_created",
        f"Created contact '{display}'",
        entity_type="contact",
        entity_id=result["id"],
    )
    return result


async def contact_update(
    pool: asyncpg.Pool, contact_id: uuid.UUID, **fields: Any
) -> dict[str, Any]:
    """Update a contact's fields. At least one field must be provided."""
    allowed = {
        "first_name",
        "last_name",
        "nickname",
        "company",
        "job_title",
        "gender",
        "pronouns",
        "avatar_url",
        "metadata",
    }
    to_update = {k: v for k, v in fields.items() if k in allowed}
    if not to_update:
        raise ValueError("At least one field must be provided for update")

    existing = await pool.fetchrow("SELECT * FROM contacts WHERE id = $1", contact_id)
    if existing is None:
        raise ValueError(f"Contact {contact_id} not found")

    set_clauses = []
    params: list[Any] = [contact_id]
    idx = 2
    for col, val in to_update.items():
        if col == "metadata" and isinstance(val, dict):
            set_clauses.append(f"{col} = ${idx}::jsonb")
            params.append(json.dumps(val))
        else:
            set_clauses.append(f"{col} = ${idx}")
            params.append(val)
        idx += 1

    set_clauses.append("updated_at = now()")
    set_sql = ", ".join(set_clauses)

    row = await pool.fetchrow(
        f"UPDATE contacts SET {set_sql} WHERE id = $1 RETURNING *",  # noqa: S608
        *params,
    )
    result = _parse_contact(row)
    display = result.get("first_name") or result.get("nickname") or str(contact_id)
    await _log_activity(
        pool,
        contact_id,
        "contact_updated",
        f"Updated contact '{display}'",
        entity_type="contact",
        entity_id=contact_id,
    )
    return result


async def contact_get(pool: asyncpg.Pool, contact_id: uuid.UUID) -> dict[str, Any] | None:
    """Get a contact by ID. Returns None if not found (per spec)."""
    row = await pool.fetchrow("SELECT * FROM contacts WHERE id = $1", contact_id)
    if row is None:
        return None
    return _parse_contact(row)


async def contact_search(
    pool: asyncpg.Pool, query: str, limit: int = 20, offset: int = 0
) -> list[dict[str, Any]]:
    """Search contacts by first_name, last_name, nickname, or company (ILIKE). Only listed=true."""
    rows = await pool.fetch(
        """
        SELECT * FROM contacts
        WHERE listed = true
          AND (
            first_name ILIKE '%' || $1 || '%'
            OR last_name ILIKE '%' || $1 || '%'
            OR nickname ILIKE '%' || $1 || '%'
            OR company ILIKE '%' || $1 || '%'
          )
        ORDER BY first_name, last_name
        LIMIT $2 OFFSET $3
        """,
        query,
        limit,
        offset,
    )
    return [_parse_contact(row) for row in rows]


async def contact_archive(pool: asyncpg.Pool, contact_id: uuid.UUID) -> dict[str, Any]:
    """Soft delete a contact by setting listed=false."""
    row = await pool.fetchrow(
        """
        UPDATE contacts SET listed = false, updated_at = now()
        WHERE id = $1
        RETURNING *
        """,
        contact_id,
    )
    if row is None:
        raise ValueError(f"Contact {contact_id} not found")
    result = _parse_contact(row)
    display = result.get("first_name") or str(contact_id)
    await _log_activity(
        pool,
        contact_id,
        "contact_archived",
        f"Archived contact '{display}'",
        entity_type="contact",
        entity_id=contact_id,
    )
    return result


# ------------------------------------------------------------------
# Contact info (email, phone, social, etc.)
# ------------------------------------------------------------------


async def contact_info_add(
    pool: asyncpg.Pool,
    contact_id: uuid.UUID,
    type: str,
    value: str,
    label: str | None = None,
) -> dict[str, Any]:
    """Add contact information (email, phone, etc.)."""
    row = await pool.fetchrow(
        """
        INSERT INTO contact_info (contact_id, type, value, label)
        VALUES ($1, $2, $3, $4)
        RETURNING *
        """,
        contact_id,
        type,
        value,
        label,
    )
    result = dict(row)
    await _log_activity(
        pool,
        contact_id,
        "contact_info_added",
        f"Added {type}: {value}",
        entity_type="contact_info",
        entity_id=result["id"],
    )
    return result


async def contact_info_list(pool: asyncpg.Pool, contact_id: uuid.UUID) -> list[dict[str, Any]]:
    """List all contact info for a contact."""
    rows = await pool.fetch(
        "SELECT * FROM contact_info WHERE contact_id = $1 ORDER BY type, label",
        contact_id,
    )
    return [dict(row) for row in rows]


async def contact_info_remove(pool: asyncpg.Pool, info_id: uuid.UUID) -> None:
    """Remove a contact info entry."""
    result = await pool.execute("DELETE FROM contact_info WHERE id = $1", info_id)
    if result == "DELETE 0":
        raise ValueError(f"Contact info {info_id} not found")


# ------------------------------------------------------------------
# Addresses
# ------------------------------------------------------------------


async def address_add(
    pool: asyncpg.Pool,
    contact_id: uuid.UUID,
    type: str | None = None,
    line_1: str | None = None,
    line_2: str | None = None,
    city: str | None = None,
    province: str | None = None,
    postal_code: str | None = None,
    country: str | None = None,
    is_current: bool = True,
) -> dict[str, Any]:
    """Add an address for a contact."""
    row = await pool.fetchrow(
        """
        INSERT INTO addresses
            (contact_id, type, line_1, line_2, city, province, postal_code, country, is_current)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        RETURNING *
        """,
        contact_id,
        type,
        line_1,
        line_2,
        city,
        province,
        postal_code,
        country,
        is_current,
    )
    result = dict(row)
    await _log_activity(
        pool,
        contact_id,
        "address_added",
        f"Added {type or 'other'} address",
        entity_type="address",
        entity_id=result["id"],
    )
    return result


async def address_list(pool: asyncpg.Pool, contact_id: uuid.UUID) -> list[dict[str, Any]]:
    """List all addresses for a contact."""
    rows = await pool.fetch(
        "SELECT * FROM addresses WHERE contact_id = $1 ORDER BY is_current DESC, created_at DESC",
        contact_id,
    )
    return [dict(row) for row in rows]


async def address_remove(pool: asyncpg.Pool, address_id: uuid.UUID) -> None:
    """Remove an address."""
    result = await pool.execute("DELETE FROM addresses WHERE id = $1", address_id)
    if result == "DELETE 0":
        raise ValueError(f"Address {address_id} not found")


# ------------------------------------------------------------------
# Relationships (bidirectional with reverse_type)
# ------------------------------------------------------------------


async def relationship_add(
    pool: asyncpg.Pool,
    contact_id: uuid.UUID,
    related_contact_id: uuid.UUID,
    group_type: str,
    type: str,
    reverse_type: str,
) -> dict[str, Any]:
    """Create a bidirectional relationship (two rows) per spec."""
    row_a = await pool.fetchrow(
        """
        INSERT INTO relationships (contact_id, related_contact_id, group_type, type, reverse_type)
        VALUES ($1, $2, $3, $4, $5)
        RETURNING *
        """,
        contact_id,
        related_contact_id,
        group_type,
        type,
        reverse_type,
    )
    await pool.execute(
        """
        INSERT INTO relationships (contact_id, related_contact_id, group_type, type, reverse_type)
        VALUES ($1, $2, $3, $4, $5)
        """,
        related_contact_id,
        contact_id,
        group_type,
        reverse_type,
        type,
    )
    result = dict(row_a)
    await _log_activity(
        pool,
        contact_id,
        "relationship_added",
        f"Added '{type}' relationship with {related_contact_id}",
        entity_type="relationship",
        entity_id=result["id"],
    )
    await _log_activity(
        pool,
        related_contact_id,
        "relationship_added",
        f"Added '{reverse_type}' relationship with {contact_id}",
        entity_type="relationship",
        entity_id=result["id"],
    )
    return result


async def relationship_list(pool: asyncpg.Pool, contact_id: uuid.UUID) -> list[dict[str, Any]]:
    """List all relationships for a contact."""
    rows = await pool.fetch(
        """
        SELECT r.*, c.first_name as related_first_name, c.last_name as related_last_name
        FROM relationships r
        JOIN contacts c ON r.related_contact_id = c.id
        WHERE r.contact_id = $1
        ORDER BY r.created_at
        """,
        contact_id,
    )
    return [dict(row) for row in rows]


async def relationship_remove(pool: asyncpg.Pool, relationship_id: uuid.UUID) -> None:
    """Remove a relationship by ID (deletes both directions)."""
    row = await pool.fetchrow("SELECT * FROM relationships WHERE id = $1", relationship_id)
    if row is None:
        raise ValueError(f"Relationship {relationship_id} not found")

    # Delete both directions
    await pool.execute(
        """
        DELETE FROM relationships
        WHERE (contact_id = $1 AND related_contact_id = $2 AND type = $3)
           OR (contact_id = $2 AND related_contact_id = $1 AND type = $4)
        """,
        row["contact_id"],
        row["related_contact_id"],
        row["type"],
        row["reverse_type"],
    )
    await _log_activity(
        pool,
        row["contact_id"],
        "relationship_removed",
        f"Removed relationship with {row['related_contact_id']}",
        entity_type="relationship",
        entity_id=relationship_id,
    )
    await _log_activity(
        pool,
        row["related_contact_id"],
        "relationship_removed",
        f"Removed relationship with {row['contact_id']}",
        entity_type="relationship",
        entity_id=relationship_id,
    )


# ------------------------------------------------------------------
# Important dates
# ------------------------------------------------------------------


async def date_add(
    pool: asyncpg.Pool,
    contact_id: uuid.UUID,
    label: str,
    day: int | None = None,
    month: int | None = None,
    year: int | None = None,
) -> dict[str, Any]:
    """Add an important date for a contact."""
    row = await pool.fetchrow(
        """
        INSERT INTO important_dates (contact_id, label, day, month, year)
        VALUES ($1, $2, $3, $4, $5)
        RETURNING *
        """,
        contact_id,
        label,
        day,
        month,
        year,
    )
    result = dict(row)
    await _log_activity(
        pool,
        contact_id,
        "date_added",
        f"Added important date '{label}' ({month}/{day})",
        entity_type="important_date",
        entity_id=result["id"],
    )
    return result


async def date_list(pool: asyncpg.Pool, contact_id: uuid.UUID) -> list[dict[str, Any]]:
    """List all important dates for a contact."""
    rows = await pool.fetch(
        "SELECT * FROM important_dates WHERE contact_id = $1 ORDER BY month, day",
        contact_id,
    )
    return [dict(row) for row in rows]


async def upcoming_dates(pool: asyncpg.Pool, days: int = 7) -> list[dict[str, Any]]:
    """Get upcoming important dates within the next N days using month/day matching."""
    from datetime import date, timedelta

    now = datetime.now(UTC)
    today = now.date()
    end_date = today + timedelta(days=days)

    rows = await pool.fetch(
        """
        SELECT d.*, c.first_name, c.last_name
        FROM important_dates d
        JOIN contacts c ON d.contact_id = c.id
        WHERE c.listed = true AND d.month IS NOT NULL AND d.day IS NOT NULL
        ORDER BY d.month, d.day
        """
    )

    results = []
    for row in rows:
        d = dict(row)
        # Check if this month/day falls within our window
        for try_year in [today.year, today.year + 1]:
            try:
                candidate = date(try_year, d["month"], d["day"])
                if today <= candidate <= end_date:
                    d["upcoming_date"] = candidate.isoformat()
                    results.append(d)
                    break
            except ValueError:
                # Invalid date (e.g., Feb 30)
                continue

    return results


# ------------------------------------------------------------------
# Notes
# ------------------------------------------------------------------


async def note_create(
    pool: asyncpg.Pool,
    contact_id: uuid.UUID,
    body: str,
    title: str | None = None,
    emotion: str | None = None,
) -> dict[str, Any]:
    """Create a note about a contact."""
    row = await pool.fetchrow(
        """
        INSERT INTO notes (contact_id, title, body, emotion)
        VALUES ($1, $2, $3, $4)
        RETURNING *
        """,
        contact_id,
        title,
        body,
        emotion,
    )
    result = dict(row)
    snippet = body[:50] + "..." if len(body) > 50 else body
    await _log_activity(
        pool,
        contact_id,
        "note_created",
        f"Added note: '{snippet}'",
        entity_type="note",
        entity_id=result["id"],
    )
    return result


async def note_list(
    pool: asyncpg.Pool, contact_id: uuid.UUID, limit: int = 20, offset: int = 0
) -> list[dict[str, Any]]:
    """List all notes for a contact."""
    rows = await pool.fetch(
        "SELECT * FROM notes WHERE contact_id = $1 ORDER BY created_at DESC LIMIT $2 OFFSET $3",
        contact_id,
        limit,
        offset,
    )
    return [dict(row) for row in rows]


async def note_search(
    pool: asyncpg.Pool, query: str, contact_id: uuid.UUID | None = None
) -> list[dict[str, Any]]:
    """Search notes by body/title content (ILIKE), optionally scoped to a contact."""
    if contact_id is not None:
        rows = await pool.fetch(
            """
            SELECT n.*, c.first_name as contact_first_name, c.last_name as contact_last_name
            FROM notes n
            JOIN contacts c ON n.contact_id = c.id
            WHERE n.contact_id = $2
              AND (n.body ILIKE '%' || $1 || '%' OR n.title ILIKE '%' || $1 || '%')
            ORDER BY n.created_at DESC
            """,
            query,
            contact_id,
        )
    else:
        rows = await pool.fetch(
            """
            SELECT n.*, c.first_name as contact_first_name, c.last_name as contact_last_name
            FROM notes n
            JOIN contacts c ON n.contact_id = c.id
            WHERE n.body ILIKE '%' || $1 || '%' OR n.title ILIKE '%' || $1 || '%'
            ORDER BY n.created_at DESC
            """,
            query,
        )
    return [dict(row) for row in rows]


# ------------------------------------------------------------------
# Interactions
# ------------------------------------------------------------------


async def interaction_log(
    pool: asyncpg.Pool,
    contact_id: uuid.UUID,
    type: str,
    direction: str | None = None,
    summary: str | None = None,
    duration_minutes: int | None = None,
    occurred_at: datetime | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Log an interaction with a contact."""
    row = await pool.fetchrow(
        """
        INSERT INTO interactions
            (contact_id, type, direction, summary, duration_minutes, occurred_at, metadata)
        VALUES ($1, $2, $3, $4, $5, COALESCE($6, now()), $7::jsonb)
        RETURNING *
        """,
        contact_id,
        type,
        direction,
        summary,
        duration_minutes,
        occurred_at,
        json.dumps(metadata or {}),
    )
    result = dict(row)
    if isinstance(result.get("metadata"), str):
        result["metadata"] = json.loads(result["metadata"])
    await _log_activity(
        pool,
        contact_id,
        "interaction_logged",
        f"Logged '{type}' interaction",
        entity_type="interaction",
        entity_id=result["id"],
    )
    return result


async def interaction_list(
    pool: asyncpg.Pool,
    contact_id: uuid.UUID,
    type: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """List interactions for a contact, most recent first."""
    if type is not None:
        rows = await pool.fetch(
            """
            SELECT * FROM interactions
            WHERE contact_id = $1 AND type = $2
            ORDER BY occurred_at DESC
            LIMIT $3 OFFSET $4
            """,
            contact_id,
            type,
            limit,
            offset,
        )
    else:
        rows = await pool.fetch(
            """
            SELECT * FROM interactions
            WHERE contact_id = $1
            ORDER BY occurred_at DESC
            LIMIT $2 OFFSET $3
            """,
            contact_id,
            limit,
            offset,
        )
    results = []
    for row in rows:
        d = dict(row)
        if isinstance(d.get("metadata"), str):
            d["metadata"] = json.loads(d["metadata"])
        results.append(d)
    return results


# ------------------------------------------------------------------
# Reminders
# ------------------------------------------------------------------


async def reminder_create(
    pool: asyncpg.Pool,
    label: str,
    type: str,
    next_trigger_at: datetime | None = None,
    contact_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    """Create a reminder for a contact."""
    row = await pool.fetchrow(
        """
        INSERT INTO reminders (contact_id, label, type, next_trigger_at)
        VALUES ($1, $2, $3, $4)
        RETURNING *
        """,
        contact_id,
        label,
        type,
        next_trigger_at,
    )
    result = dict(row)
    if contact_id is not None:
        await _log_activity(
            pool,
            contact_id,
            "reminder_created",
            f"Created reminder: '{label}'",
            entity_type="reminder",
            entity_id=result["id"],
        )
    return result


async def reminder_list(
    pool: asyncpg.Pool,
    contact_id: uuid.UUID | None = None,
    include_dismissed: bool = False,
) -> list[dict[str, Any]]:
    """List reminders, optionally filtered by contact."""
    if contact_id is not None:
        if include_dismissed:
            rows = await pool.fetch(
                "SELECT * FROM reminders WHERE contact_id = $1 ORDER BY created_at DESC",
                contact_id,
            )
        else:
            rows = await pool.fetch(
                """
                SELECT * FROM reminders
                WHERE contact_id = $1 AND next_trigger_at IS NOT NULL
                ORDER BY next_trigger_at ASC
                """,
                contact_id,
            )
    elif include_dismissed:
        rows = await pool.fetch("SELECT * FROM reminders ORDER BY created_at DESC")
    else:
        rows = await pool.fetch(
            """
            SELECT * FROM reminders
            WHERE next_trigger_at IS NOT NULL
            ORDER BY next_trigger_at ASC
            """
        )
    return [dict(row) for row in rows]


async def reminder_dismiss(pool: asyncpg.Pool, reminder_id: uuid.UUID) -> dict[str, Any]:
    """Dismiss a reminder. One-time: nullify next_trigger_at. Recurring: advance."""
    from dateutil.relativedelta import relativedelta

    row = await pool.fetchrow("SELECT * FROM reminders WHERE id = $1", reminder_id)
    if row is None:
        raise ValueError(f"Reminder {reminder_id} not found")

    now = datetime.now(UTC)
    reminder_type = row["type"]

    if reminder_type == "one_time":
        updated = await pool.fetchrow(
            """
            UPDATE reminders SET last_triggered_at = $2, next_trigger_at = NULL
            WHERE id = $1
            RETURNING *
            """,
            reminder_id,
            now,
        )
    elif reminder_type == "recurring_yearly":
        next_at = row["next_trigger_at"] + relativedelta(years=1)
        updated = await pool.fetchrow(
            """
            UPDATE reminders SET last_triggered_at = $2, next_trigger_at = $3
            WHERE id = $1
            RETURNING *
            """,
            reminder_id,
            now,
            next_at,
        )
    elif reminder_type == "recurring_monthly":
        next_at = row["next_trigger_at"] + relativedelta(months=1)
        updated = await pool.fetchrow(
            """
            UPDATE reminders SET last_triggered_at = $2, next_trigger_at = $3
            WHERE id = $1
            RETURNING *
            """,
            reminder_id,
            now,
            next_at,
        )
    else:
        # Fallback for unknown type — treat as one_time
        updated = await pool.fetchrow(
            """
            UPDATE reminders SET last_triggered_at = $2, next_trigger_at = NULL
            WHERE id = $1
            RETURNING *
            """,
            reminder_id,
            now,
        )

    result = dict(updated)
    if result.get("contact_id") is not None:
        await _log_activity(
            pool,
            result["contact_id"],
            "reminder_dismissed",
            f"Dismissed reminder: '{row['label']}'",
            entity_type="reminder",
            entity_id=reminder_id,
        )
    return result


# ------------------------------------------------------------------
# Gifts
# ------------------------------------------------------------------


async def gift_add(
    pool: asyncpg.Pool,
    contact_id: uuid.UUID,
    name: str,
    description: str | None = None,
    occasion: str | None = None,
    estimated_price_cents: int | None = None,
    url: str | None = None,
) -> dict[str, Any]:
    """Add a gift idea for a contact."""
    row = await pool.fetchrow(
        """
        INSERT INTO gifts (contact_id, name, description, occasion, estimated_price_cents, url)
        VALUES ($1, $2, $3, $4, $5, $6)
        RETURNING *
        """,
        contact_id,
        name,
        description,
        occasion,
        estimated_price_cents,
        url,
    )
    result = dict(row)
    await _log_activity(
        pool,
        contact_id,
        "gift_added",
        f"Added gift idea: '{name}'",
        entity_type="gift",
        entity_id=result["id"],
    )
    return result


async def gift_update_status(pool: asyncpg.Pool, gift_id: uuid.UUID, status: str) -> dict[str, Any]:
    """Update gift status, validating it is a valid status value."""
    if status not in _GIFT_STATUS_ORDER:
        raise ValueError(f"Invalid status '{status}'. Must be one of {_GIFT_STATUS_ORDER}")

    row = await pool.fetchrow("SELECT * FROM gifts WHERE id = $1", gift_id)
    if row is None:
        raise ValueError(f"Gift {gift_id} not found")

    updated = await pool.fetchrow(
        """
        UPDATE gifts SET status = $2, updated_at = now()
        WHERE id = $1
        RETURNING *
        """,
        gift_id,
        status,
    )
    result = dict(updated)
    await _log_activity(
        pool,
        result["contact_id"],
        "gift_status_updated",
        f"Gift '{row['name']}' status: {row['status']} -> {status}",
        entity_type="gift",
        entity_id=gift_id,
    )
    return result


async def gift_list(
    pool: asyncpg.Pool, contact_id: uuid.UUID, status: str | None = None
) -> list[dict[str, Any]]:
    """List gifts for a contact, optionally filtered by status."""
    if status is not None:
        rows = await pool.fetch(
            """
            SELECT * FROM gifts
            WHERE contact_id = $1 AND status = $2
            ORDER BY created_at DESC
            """,
            contact_id,
            status,
        )
    else:
        rows = await pool.fetch(
            "SELECT * FROM gifts WHERE contact_id = $1 ORDER BY created_at DESC",
            contact_id,
        )
    return [dict(row) for row in rows]


# ------------------------------------------------------------------
# Loans
# ------------------------------------------------------------------


async def loan_create(
    pool: asyncpg.Pool,
    lender_contact_id: uuid.UUID,
    borrower_contact_id: uuid.UUID,
    name: str,
    amount_cents: int,
    currency: str = "USD",
    loaned_at: datetime | None = None,
) -> dict[str, Any]:
    """Create a loan record."""
    row = await pool.fetchrow(
        """
        INSERT INTO loans
            (lender_contact_id, borrower_contact_id, name, amount_cents, currency, loaned_at)
        VALUES ($1, $2, $3, $4, $5, $6)
        RETURNING *
        """,
        lender_contact_id,
        borrower_contact_id,
        name,
        amount_cents,
        currency,
        loaned_at,
    )
    result = dict(row)
    await _log_activity(
        pool,
        lender_contact_id,
        "loan_created",
        f"Created loan: {name} ({amount_cents} {currency})",
        entity_type="loan",
        entity_id=result["id"],
    )
    await _log_activity(
        pool,
        borrower_contact_id,
        "loan_created",
        f"Created loan: {name} ({amount_cents} {currency})",
        entity_type="loan",
        entity_id=result["id"],
    )
    return result


async def loan_settle(pool: asyncpg.Pool, loan_id: uuid.UUID) -> dict[str, Any]:
    """Settle a loan."""
    row = await pool.fetchrow("SELECT * FROM loans WHERE id = $1", loan_id)
    if row is None:
        raise ValueError(f"Loan {loan_id} not found")
    if row["settled"]:
        raise ValueError(f"Loan {loan_id} is already settled")

    updated = await pool.fetchrow(
        """
        UPDATE loans SET settled = true, settled_at = now()
        WHERE id = $1
        RETURNING *
        """,
        loan_id,
    )
    result = dict(updated)
    await _log_activity(
        pool,
        result["lender_contact_id"],
        "loan_settled",
        f"Settled loan: {result['name']}",
        entity_type="loan",
        entity_id=loan_id,
    )
    return result


async def loan_list(
    pool: asyncpg.Pool, contact_id: uuid.UUID, settled: bool | None = None
) -> list[dict[str, Any]]:
    """List loans involving a contact (as lender or borrower)."""
    if settled is not None:
        rows = await pool.fetch(
            """
            SELECT * FROM loans
            WHERE (lender_contact_id = $1 OR borrower_contact_id = $1)
              AND settled = $2
            ORDER BY created_at DESC
            """,
            contact_id,
            settled,
        )
    else:
        rows = await pool.fetch(
            """
            SELECT * FROM loans
            WHERE lender_contact_id = $1 OR borrower_contact_id = $1
            ORDER BY created_at DESC
            """,
            contact_id,
        )
    return [dict(row) for row in rows]


# ------------------------------------------------------------------
# Groups
# ------------------------------------------------------------------


async def group_create(pool: asyncpg.Pool, name: str, type: str | None = None) -> dict[str, Any]:
    """Create a contact group."""
    row = await pool.fetchrow(
        "INSERT INTO groups (name, type) VALUES ($1, $2) RETURNING *",
        name,
        type,
    )
    return dict(row)


async def group_add_member(
    pool: asyncpg.Pool, group_id: uuid.UUID, contact_id: uuid.UUID, role: str | None = None
) -> dict[str, Any]:
    """Add a contact to a group."""
    await pool.execute(
        "INSERT INTO group_members (group_id, contact_id, role) VALUES ($1, $2, $3)",
        group_id,
        contact_id,
        role,
    )
    await _log_activity(
        pool, contact_id, "group_joined", f"Joined group {group_id}", entity_type="group"
    )
    return {"group_id": group_id, "contact_id": contact_id, "role": role}


async def group_list(pool: asyncpg.Pool) -> list[dict[str, Any]]:
    """List all groups with member details."""
    groups = await pool.fetch("SELECT * FROM groups ORDER BY name")
    results = []
    for g in groups:
        gd = dict(g)
        members = await pool.fetch(
            """
            SELECT gm.contact_id, gm.role, c.first_name, c.last_name
            FROM group_members gm
            JOIN contacts c ON gm.contact_id = c.id
            WHERE gm.group_id = $1
            ORDER BY c.first_name, c.last_name
            """,
            g["id"],
        )
        gd["members"] = [dict(m) for m in members]
        results.append(gd)
    return results


async def group_members(pool: asyncpg.Pool, group_id: uuid.UUID) -> list[dict[str, Any]]:
    """List all members of a group."""
    rows = await pool.fetch(
        """
        SELECT c.*, gm.role
        FROM contacts c
        JOIN group_members gm ON c.id = gm.contact_id
        WHERE gm.group_id = $1
        ORDER BY c.first_name, c.last_name
        """,
        group_id,
    )
    return [_parse_contact(row) for row in rows]


# ------------------------------------------------------------------
# Labels
# ------------------------------------------------------------------


async def label_create(pool: asyncpg.Pool, name: str, color: str | None = None) -> dict[str, Any]:
    """Create a label."""
    row = await pool.fetchrow(
        "INSERT INTO labels (name, color) VALUES ($1, $2) RETURNING *",
        name,
        color,
    )
    return dict(row)


async def label_assign(
    pool: asyncpg.Pool, contact_id: uuid.UUID, label_id: uuid.UUID
) -> dict[str, Any]:
    """Assign a label to a contact."""
    await pool.execute(
        "INSERT INTO contact_labels (contact_id, label_id) VALUES ($1, $2)",
        contact_id,
        label_id,
    )
    await _log_activity(
        pool, contact_id, "label_assigned", f"Assigned label {label_id}", entity_type="label"
    )
    return {"label_id": label_id, "contact_id": contact_id}


async def contact_search_by_label(pool: asyncpg.Pool, label_id: uuid.UUID) -> list[dict[str, Any]]:
    """Search contacts by label ID (only listed=true)."""
    rows = await pool.fetch(
        """
        SELECT c.*
        FROM contacts c
        JOIN contact_labels cl ON c.id = cl.contact_id
        WHERE cl.label_id = $1 AND c.listed = true
        ORDER BY c.first_name, c.last_name
        """,
        label_id,
    )
    return [_parse_contact(row) for row in rows]


# ------------------------------------------------------------------
# Quick facts
# ------------------------------------------------------------------


async def fact_set(
    pool: asyncpg.Pool, contact_id: uuid.UUID, category: str, content: str
) -> dict[str, Any]:
    """Set a quick fact for a contact (insert only; no upsert since spec has no UNIQUE)."""
    row = await pool.fetchrow(
        """
        INSERT INTO quick_facts (contact_id, category, content)
        VALUES ($1, $2, $3)
        RETURNING *
        """,
        contact_id,
        category,
        content,
    )
    result = dict(row)
    await _log_activity(
        pool,
        contact_id,
        "fact_set",
        f"Set fact '{category}' = '{content}'",
        entity_type="quick_fact",
        entity_id=result["id"],
    )
    return result


async def fact_list(pool: asyncpg.Pool, contact_id: uuid.UUID) -> list[dict[str, Any]]:
    """List all quick facts for a contact."""
    rows = await pool.fetch(
        "SELECT * FROM quick_facts WHERE contact_id = $1 ORDER BY category",
        contact_id,
    )
    return [dict(row) for row in rows]
