"""Relationship butler tools — personal CRM for contacts and interactions."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import asyncpg

logger = logging.getLogger(__name__)

# Valid gift status transitions (pipeline order)
_GIFT_STATUS_ORDER = ["idea", "purchased", "wrapped", "given", "thanked"]


# ------------------------------------------------------------------
# Internal helper: activity feed
# ------------------------------------------------------------------


async def _log_activity(
    pool: asyncpg.Pool, contact_id: uuid.UUID, type: str, description: str
) -> None:
    """Log an activity to the activity feed."""
    await pool.execute(
        """
        INSERT INTO activity_feed (contact_id, type, description)
        VALUES ($1, $2, $3)
        """,
        contact_id,
        type,
        description,
    )


async def feed_get(
    pool: asyncpg.Pool, contact_id: uuid.UUID | None = None, limit: int = 50
) -> list[dict[str, Any]]:
    """Get activity feed entries, optionally filtered by contact."""
    if contact_id is not None:
        rows = await pool.fetch(
            """
            SELECT * FROM activity_feed
            WHERE contact_id = $1
            ORDER BY created_at DESC
            LIMIT $2
            """,
            contact_id,
            limit,
        )
    else:
        rows = await pool.fetch(
            """
            SELECT * FROM activity_feed
            ORDER BY created_at DESC
            LIMIT $1
            """,
            limit,
        )
    return [dict(row) for row in rows]


def _parse_contact(row: asyncpg.Record) -> dict[str, Any]:
    """Convert a contact row to a dict, parsing JSONB details if needed."""
    d = dict(row)
    if isinstance(d.get("details"), str):
        d["details"] = json.loads(d["details"])
    return d


# ------------------------------------------------------------------
# Contact CRUD
# ------------------------------------------------------------------


async def contact_create(
    pool: asyncpg.Pool, name: str, details: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Create a new contact."""
    row = await pool.fetchrow(
        """
        INSERT INTO contacts (name, details)
        VALUES ($1, $2::jsonb)
        RETURNING *
        """,
        name,
        json.dumps(details or {}),
    )
    result = _parse_contact(row)
    await _log_activity(pool, result["id"], "contact_created", f"Created contact '{name}'")
    return result


async def contact_update(
    pool: asyncpg.Pool, contact_id: uuid.UUID, **fields: Any
) -> dict[str, Any]:
    """Update a contact's fields (name, details)."""
    existing = await pool.fetchrow("SELECT * FROM contacts WHERE id = $1", contact_id)
    if existing is None:
        raise ValueError(f"Contact {contact_id} not found")

    name = fields.get("name", existing["name"])
    details = fields.get("details", existing["details"])
    if isinstance(details, dict):
        details = json.dumps(details)

    row = await pool.fetchrow(
        """
        UPDATE contacts SET name = $2, details = $3::jsonb, updated_at = now()
        WHERE id = $1
        RETURNING *
        """,
        contact_id,
        name,
        details,
    )
    result = _parse_contact(row)
    await _log_activity(pool, contact_id, "contact_updated", f"Updated contact '{name}'")
    return result


async def contact_get(pool: asyncpg.Pool, contact_id: uuid.UUID) -> dict[str, Any]:
    """Get a contact by ID."""
    row = await pool.fetchrow("SELECT * FROM contacts WHERE id = $1", contact_id)
    if row is None:
        raise ValueError(f"Contact {contact_id} not found")
    return _parse_contact(row)


async def contact_search(pool: asyncpg.Pool, query: str) -> list[dict[str, Any]]:
    """Search contacts by name (ILIKE) and details JSONB text."""
    rows = await pool.fetch(
        """
        SELECT * FROM contacts
        WHERE archived_at IS NULL
          AND (name ILIKE '%' || $1 || '%' OR details::text ILIKE '%' || $1 || '%')
        ORDER BY name
        """,
        query,
    )
    return [_parse_contact(row) for row in rows]


async def contact_archive(pool: asyncpg.Pool, contact_id: uuid.UUID) -> dict[str, Any]:
    """Soft delete a contact by setting archived_at."""
    row = await pool.fetchrow(
        """
        UPDATE contacts SET archived_at = now(), updated_at = now()
        WHERE id = $1
        RETURNING *
        """,
        contact_id,
    )
    if row is None:
        raise ValueError(f"Contact {contact_id} not found")
    result = _parse_contact(row)
    await _log_activity(pool, contact_id, "contact_archived", f"Archived contact '{row['name']}'")
    return result


# ------------------------------------------------------------------
# Relationships (bidirectional)
# ------------------------------------------------------------------


async def relationship_add(
    pool: asyncpg.Pool,
    contact_a: uuid.UUID,
    contact_b: uuid.UUID,
    type: str,
    notes: str | None = None,
) -> dict[str, Any]:
    """Create a bidirectional relationship (two rows)."""
    row_a = await pool.fetchrow(
        """
        INSERT INTO relationships (contact_a, contact_b, type, notes)
        VALUES ($1, $2, $3, $4)
        RETURNING *
        """,
        contact_a,
        contact_b,
        type,
        notes,
    )
    await pool.execute(
        """
        INSERT INTO relationships (contact_a, contact_b, type, notes)
        VALUES ($1, $2, $3, $4)
        """,
        contact_b,
        contact_a,
        type,
        notes,
    )
    result = dict(row_a)
    await _log_activity(
        pool, contact_a, "relationship_added", f"Added '{type}' relationship with {contact_b}"
    )
    await _log_activity(
        pool, contact_b, "relationship_added", f"Added '{type}' relationship with {contact_a}"
    )
    return result


async def relationship_list(pool: asyncpg.Pool, contact_id: uuid.UUID) -> list[dict[str, Any]]:
    """List all relationships for a contact."""
    rows = await pool.fetch(
        """
        SELECT r.*, c.name as related_name
        FROM relationships r
        JOIN contacts c ON r.contact_b = c.id
        WHERE r.contact_a = $1
        ORDER BY r.created_at
        """,
        contact_id,
    )
    return [dict(row) for row in rows]


async def relationship_remove(
    pool: asyncpg.Pool, contact_a: uuid.UUID, contact_b: uuid.UUID
) -> None:
    """Remove both directions of a relationship."""
    await pool.execute(
        """
        DELETE FROM relationships
        WHERE (contact_a = $1 AND contact_b = $2)
           OR (contact_a = $2 AND contact_b = $1)
        """,
        contact_a,
        contact_b,
    )
    await _log_activity(
        pool, contact_a, "relationship_removed", f"Removed relationship with {contact_b}"
    )
    await _log_activity(
        pool, contact_b, "relationship_removed", f"Removed relationship with {contact_a}"
    )


# ------------------------------------------------------------------
# Important dates
# ------------------------------------------------------------------


async def date_add(
    pool: asyncpg.Pool,
    contact_id: uuid.UUID,
    label: str,
    month: int,
    day: int,
    year: int | None = None,
) -> dict[str, Any]:
    """Add an important date for a contact."""
    row = await pool.fetchrow(
        """
        INSERT INTO important_dates (contact_id, label, month, day, year)
        VALUES ($1, $2, $3, $4, $5)
        RETURNING *
        """,
        contact_id,
        label,
        month,
        day,
        year,
    )
    result = dict(row)
    await _log_activity(
        pool, contact_id, "date_added", f"Added important date '{label}' ({month}/{day})"
    )
    return result


async def date_list(pool: asyncpg.Pool, contact_id: uuid.UUID) -> list[dict[str, Any]]:
    """List all important dates for a contact."""
    rows = await pool.fetch(
        "SELECT * FROM important_dates WHERE contact_id = $1 ORDER BY month, day",
        contact_id,
    )
    return [dict(row) for row in rows]


async def upcoming_dates(pool: asyncpg.Pool, days_ahead: int = 30) -> list[dict[str, Any]]:
    """Get upcoming important dates within the next N days using month/day matching."""
    from datetime import date, timedelta

    now = datetime.now(UTC)
    today = now.date()
    end_date = today + timedelta(days=days_ahead)

    rows = await pool.fetch(
        """
        SELECT d.*, c.name as contact_name
        FROM important_dates d
        JOIN contacts c ON d.contact_id = c.id
        WHERE c.archived_at IS NULL
        ORDER BY d.month, d.day
        """
    )

    results = []
    for row in rows:
        d = dict(row)
        # Check if this month/day falls within our window
        # Try current year first, then next year for wrapping
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
    content: str,
    emotion: str | None = None,
) -> dict[str, Any]:
    """Create a note about a contact."""
    row = await pool.fetchrow(
        """
        INSERT INTO notes (contact_id, content, emotion)
        VALUES ($1, $2, $3)
        RETURNING *
        """,
        contact_id,
        content,
        emotion,
    )
    result = dict(row)
    snippet = content[:50] + "..." if len(content) > 50 else content
    await _log_activity(pool, contact_id, "note_created", f"Added note: '{snippet}'")
    return result


async def note_list(pool: asyncpg.Pool, contact_id: uuid.UUID) -> list[dict[str, Any]]:
    """List all notes for a contact."""
    rows = await pool.fetch(
        "SELECT * FROM notes WHERE contact_id = $1 ORDER BY created_at DESC",
        contact_id,
    )
    return [dict(row) for row in rows]


async def note_search(pool: asyncpg.Pool, query: str) -> list[dict[str, Any]]:
    """Search notes by content (ILIKE)."""
    rows = await pool.fetch(
        """
        SELECT n.*, c.name as contact_name
        FROM notes n
        JOIN contacts c ON n.contact_id = c.id
        WHERE n.content ILIKE '%' || $1 || '%'
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
    summary: str | None = None,
    occurred_at: datetime | None = None,
) -> dict[str, Any]:
    """Log an interaction with a contact."""
    row = await pool.fetchrow(
        """
        INSERT INTO interactions (contact_id, type, summary, occurred_at)
        VALUES ($1, $2, $3, COALESCE($4, now()))
        RETURNING *
        """,
        contact_id,
        type,
        summary,
        occurred_at,
    )
    result = dict(row)
    await _log_activity(pool, contact_id, "interaction_logged", f"Logged '{type}' interaction")
    return result


async def interaction_list(
    pool: asyncpg.Pool, contact_id: uuid.UUID, limit: int = 20
) -> list[dict[str, Any]]:
    """List interactions for a contact, most recent first."""
    rows = await pool.fetch(
        """
        SELECT * FROM interactions
        WHERE contact_id = $1
        ORDER BY occurred_at DESC
        LIMIT $2
        """,
        contact_id,
        limit,
    )
    return [dict(row) for row in rows]


# ------------------------------------------------------------------
# Reminders
# ------------------------------------------------------------------


async def reminder_create(
    pool: asyncpg.Pool,
    contact_id: uuid.UUID,
    message: str,
    reminder_type: str,
    cron: str | None = None,
    due_at: datetime | None = None,
) -> dict[str, Any]:
    """Create a reminder for a contact."""
    row = await pool.fetchrow(
        """
        INSERT INTO reminders (contact_id, message, reminder_type, cron, due_at)
        VALUES ($1, $2, $3, $4, $5)
        RETURNING *
        """,
        contact_id,
        message,
        reminder_type,
        cron,
        due_at,
    )
    result = dict(row)
    await _log_activity(pool, contact_id, "reminder_created", f"Created reminder: '{message}'")
    return result


async def reminder_list(pool: asyncpg.Pool, contact_id: uuid.UUID) -> list[dict[str, Any]]:
    """List reminders for a contact."""
    rows = await pool.fetch(
        "SELECT * FROM reminders WHERE contact_id = $1 ORDER BY created_at DESC",
        contact_id,
    )
    return [dict(row) for row in rows]


async def reminder_dismiss(pool: asyncpg.Pool, reminder_id: uuid.UUID) -> dict[str, Any]:
    """Dismiss a reminder."""
    row = await pool.fetchrow(
        """
        UPDATE reminders SET dismissed = true
        WHERE id = $1
        RETURNING *
        """,
        reminder_id,
    )
    if row is None:
        raise ValueError(f"Reminder {reminder_id} not found")
    result = dict(row)
    await _log_activity(
        pool, result["contact_id"], "reminder_dismissed", f"Dismissed reminder: '{row['message']}'"
    )
    return result


# ------------------------------------------------------------------
# Gifts
# ------------------------------------------------------------------


async def gift_add(
    pool: asyncpg.Pool,
    contact_id: uuid.UUID,
    description: str,
    occasion: str | None = None,
) -> dict[str, Any]:
    """Add a gift idea for a contact."""
    row = await pool.fetchrow(
        """
        INSERT INTO gifts (contact_id, description, occasion)
        VALUES ($1, $2, $3)
        RETURNING *
        """,
        contact_id,
        description,
        occasion,
    )
    result = dict(row)
    await _log_activity(pool, contact_id, "gift_added", f"Added gift idea: '{description}'")
    return result


async def gift_update_status(pool: asyncpg.Pool, gift_id: uuid.UUID, status: str) -> dict[str, Any]:
    """Update gift status, validating pipeline order."""
    if status not in _GIFT_STATUS_ORDER:
        raise ValueError(f"Invalid status '{status}'. Must be one of {_GIFT_STATUS_ORDER}")

    row = await pool.fetchrow("SELECT * FROM gifts WHERE id = $1", gift_id)
    if row is None:
        raise ValueError(f"Gift {gift_id} not found")

    current_idx = _GIFT_STATUS_ORDER.index(row["status"])
    new_idx = _GIFT_STATUS_ORDER.index(status)
    if new_idx <= current_idx:
        raise ValueError(
            f"Cannot move from '{row['status']}' to '{status}'. "
            f"Pipeline: {' -> '.join(_GIFT_STATUS_ORDER)}"
        )

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
        f"Gift '{row['description']}' status: {row['status']} -> {status}",
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
    contact_id: uuid.UUID,
    amount: Decimal,
    direction: str,
    description: str | None = None,
) -> dict[str, Any]:
    """Create a loan record."""
    row = await pool.fetchrow(
        """
        INSERT INTO loans (contact_id, amount, direction, description)
        VALUES ($1, $2, $3, $4)
        RETURNING *
        """,
        contact_id,
        amount,
        direction,
        description,
    )
    result = dict(row)
    await _log_activity(
        pool,
        contact_id,
        "loan_created",
        f"Created loan: {direction} {amount}",
    )
    return result


async def loan_settle(pool: asyncpg.Pool, loan_id: uuid.UUID) -> dict[str, Any]:
    """Settle a loan."""
    row = await pool.fetchrow(
        """
        UPDATE loans SET settled = true, settled_at = now()
        WHERE id = $1
        RETURNING *
        """,
        loan_id,
    )
    if row is None:
        raise ValueError(f"Loan {loan_id} not found")
    result = dict(row)
    await _log_activity(
        pool,
        result["contact_id"],
        "loan_settled",
        f"Settled loan: {row['direction']} {row['amount']}",
    )
    return result


async def loan_list(pool: asyncpg.Pool, contact_id: uuid.UUID) -> list[dict[str, Any]]:
    """List loans for a contact."""
    rows = await pool.fetch(
        "SELECT * FROM loans WHERE contact_id = $1 ORDER BY created_at DESC",
        contact_id,
    )
    return [dict(row) for row in rows]


# ------------------------------------------------------------------
# Groups
# ------------------------------------------------------------------


async def group_create(pool: asyncpg.Pool, name: str) -> dict[str, Any]:
    """Create a contact group."""
    row = await pool.fetchrow(
        "INSERT INTO groups (name) VALUES ($1) RETURNING *",
        name,
    )
    return dict(row)


async def group_add_member(
    pool: asyncpg.Pool, group_id: uuid.UUID, contact_id: uuid.UUID
) -> dict[str, Any]:
    """Add a contact to a group."""
    await pool.execute(
        "INSERT INTO group_members (group_id, contact_id) VALUES ($1, $2)",
        group_id,
        contact_id,
    )
    await _log_activity(pool, contact_id, "group_joined", f"Joined group {group_id}")
    return {"group_id": group_id, "contact_id": contact_id}


async def group_list(pool: asyncpg.Pool) -> list[dict[str, Any]]:
    """List all groups."""
    rows = await pool.fetch("SELECT * FROM groups ORDER BY name")
    return [dict(row) for row in rows]


async def group_members(pool: asyncpg.Pool, group_id: uuid.UUID) -> list[dict[str, Any]]:
    """List all members of a group."""
    rows = await pool.fetch(
        """
        SELECT c.*
        FROM contacts c
        JOIN group_members gm ON c.id = gm.contact_id
        WHERE gm.group_id = $1
        ORDER BY c.name
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
    pool: asyncpg.Pool, label_id: uuid.UUID, contact_id: uuid.UUID
) -> dict[str, Any]:
    """Assign a label to a contact."""
    await pool.execute(
        "INSERT INTO contact_labels (label_id, contact_id) VALUES ($1, $2)",
        label_id,
        contact_id,
    )
    await _log_activity(pool, contact_id, "label_assigned", f"Assigned label {label_id}")
    return {"label_id": label_id, "contact_id": contact_id}


async def contact_search_by_label(pool: asyncpg.Pool, label_name: str) -> list[dict[str, Any]]:
    """Search contacts by label name."""
    rows = await pool.fetch(
        """
        SELECT c.*
        FROM contacts c
        JOIN contact_labels cl ON c.id = cl.contact_id
        JOIN labels l ON cl.label_id = l.id
        WHERE l.name = $1 AND c.archived_at IS NULL
        ORDER BY c.name
        """,
        label_name,
    )
    return [_parse_contact(row) for row in rows]


# ------------------------------------------------------------------
# Quick facts
# ------------------------------------------------------------------


async def fact_set(
    pool: asyncpg.Pool, contact_id: uuid.UUID, key: str, value: str
) -> dict[str, Any]:
    """Set a quick fact for a contact (UPSERT)."""
    row = await pool.fetchrow(
        """
        INSERT INTO quick_facts (contact_id, key, value)
        VALUES ($1, $2, $3)
        ON CONFLICT (contact_id, key) DO UPDATE SET value = $3, updated_at = now()
        RETURNING *
        """,
        contact_id,
        key,
        value,
    )
    result = dict(row)
    await _log_activity(pool, contact_id, "fact_set", f"Set fact '{key}' = '{value}'")
    return result


async def fact_list(pool: asyncpg.Pool, contact_id: uuid.UUID) -> list[dict[str, Any]]:
    """List all quick facts for a contact."""
    rows = await pool.fetch(
        "SELECT * FROM quick_facts WHERE contact_id = $1 ORDER BY key",
        contact_id,
    )
    return [dict(row) for row in rows]


# ------------------------------------------------------------------
# vCard import/export
# ------------------------------------------------------------------


async def contact_export_vcard(pool: asyncpg.Pool, contact_id: uuid.UUID | None = None) -> str:
    """Export one or all contacts as vCard 3.0.

    Args:
        pool: Database connection pool
        contact_id: Optional contact ID. If None, exports all non-archived contacts.

    Returns:
        vCard 3.0 formatted string (multiple vCards if exporting all)
    """
    import vobject

    if contact_id is not None:
        # Export single contact
        contact = await contact_get(pool, contact_id)
        contacts = [contact]
    else:
        # Export all non-archived contacts
        rows = await pool.fetch("SELECT * FROM contacts WHERE archived_at IS NULL ORDER BY name")
        contacts = [_parse_contact(row) for row in rows]

    vcards = []
    for contact in contacts:
        vcard = vobject.vCard()

        # FN (Formatted Name) - required field
        vcard.add("fn")
        vcard.fn.value = contact["name"]

        # N (Name) - required field, split name into components
        vcard.add("n")
        name_parts = contact["name"].split(" ", 1)
        if len(name_parts) == 2:
            vcard.n.value = vobject.vcard.Name(family=name_parts[1], given=name_parts[0])
        else:
            vcard.n.value = vobject.vcard.Name(family=name_parts[0])

        details = contact.get("details", {})

        # TEL (Phone) - from details.contact_info
        phones = details.get("phones", [])
        for phone in phones:
            tel = vcard.add("tel")
            tel.value = phone.get("number", "")
            tel.type_param = phone.get("type", "VOICE")

        # EMAIL - from details.emails
        emails = details.get("emails", [])
        for email in emails:
            email_field = vcard.add("email")
            email_field.value = email.get("address", "")
            email_field.type_param = email.get("type", "INTERNET")

        # ADR (Address) - from details.addresses
        addresses = details.get("addresses", [])
        for addr in addresses:
            adr = vcard.add("adr")
            adr.value = vobject.vcard.Address(
                street=addr.get("street", ""),
                city=addr.get("city", ""),
                region=addr.get("state", ""),
                code=addr.get("postal_code", ""),
                country=addr.get("country", ""),
            )
            adr.type_param = addr.get("type", "HOME")

        # BDAY (Birthday) - from important_dates
        dates = await date_list(pool, contact["id"])
        for date in dates:
            if date["label"].lower() == "birthday":
                vcard.add("bday")
                if date.get("year"):
                    vcard.bday.value = f"{date['year']:04d}-{date['month']:02d}-{date['day']:02d}"
                else:
                    vcard.bday.value = f"--{date['month']:02d}-{date['day']:02d}"
                break

        # ORG (Organization) - from quick_facts.company
        facts = await fact_list(pool, contact["id"])
        facts_dict = {f["key"]: f["value"] for f in facts}

        if "company" in facts_dict:
            vcard.add("org")
            vcard.org.value = [facts_dict["company"]]

        # TITLE (Job Title) - from quick_facts.job_title
        if "job_title" in facts_dict:
            vcard.add("title")
            vcard.title.value = facts_dict["job_title"]

        # NOTE - combine emotion notes if any
        notes = await note_list(pool, contact["id"])
        if notes:
            note_texts = [n["content"] for n in notes[:3]]  # Limit to 3 most recent
            vcard.add("note")
            vcard.note.value = "\n---\n".join(note_texts)

        vcards.append(vcard.serialize())

    return "".join(vcards)


async def contact_import_vcard(pool: asyncpg.Pool, vcf_content: str) -> list[dict[str, Any]]:
    """Import vCard data and create contacts.

    Parses vCard 3.0/4.0 content and creates contacts with:
    - FN → name
    - TEL → details.phones
    - EMAIL → details.emails
    - ADR → details.addresses
    - BDAY → important_dates (birthday)
    - ORG → quick_facts (company)
    - TITLE → quick_facts (job_title)
    - NOTE → notes

    Args:
        pool: Database connection pool
        vcf_content: vCard formatted string (can contain multiple vCards)

    Returns:
        List of created contact dicts
    """
    import vobject

    created_contacts = []

    # Parse vCard(s) - vobject can handle multiple vCards in one string
    try:
        vcards = vobject.readComponents(vcf_content)
    except (vobject.base.ParseError, Exception) as e:
        raise ValueError(f"Failed to parse vCard content: {e}") from e

    for vcard in vcards:
        # Required: FN (Formatted Name)
        if not hasattr(vcard, "fn"):
            logger.warning("Skipping vCard without FN field")
            continue

        name = vcard.fn.value

        # Build details dict
        details = {"phones": [], "emails": [], "addresses": []}

        # TEL (Phone numbers)
        if hasattr(vcard, "tel_list"):
            for tel in vcard.tel_list:
                phone_type = "VOICE"
                if hasattr(tel, "type_param"):
                    phone_type = tel.type_param if isinstance(tel.type_param, str) else "VOICE"
                details["phones"].append({"number": tel.value, "type": phone_type})

        # EMAIL
        if hasattr(vcard, "email_list"):
            for email in vcard.email_list:
                email_type = "INTERNET"
                if hasattr(email, "type_param"):
                    if isinstance(email.type_param, str):
                        email_type = email.type_param
                    else:
                        email_type = "INTERNET"
                details["emails"].append({"address": email.value, "type": email_type})

        # ADR (Addresses)
        if hasattr(vcard, "adr_list"):
            for adr in vcard.adr_list:
                addr_type = "HOME"
                if hasattr(adr, "type_param"):
                    addr_type = adr.type_param if isinstance(adr.type_param, str) else "HOME"

                addr_value = adr.value
                details["addresses"].append(
                    {
                        "street": addr_value.street if hasattr(addr_value, "street") else "",
                        "city": addr_value.city if hasattr(addr_value, "city") else "",
                        "state": addr_value.region if hasattr(addr_value, "region") else "",
                        "postal_code": addr_value.code if hasattr(addr_value, "code") else "",
                        "country": addr_value.country if hasattr(addr_value, "country") else "",
                        "type": addr_type,
                    }
                )

        # Create the contact
        contact = await contact_create(pool, name, details)
        created_contacts.append(contact)

        # BDAY (Birthday) → important_dates
        if hasattr(vcard, "bday"):
            bday_value = vcard.bday.value
            if isinstance(bday_value, str):
                # Parse date string: YYYY-MM-DD or --MM-DD
                parts = bday_value.strip().split("-")
                parts = [p for p in parts if p]  # Remove empty strings

                if len(parts) >= 2:
                    try:
                        if len(parts) == 3:
                            # YYYY-MM-DD
                            year = int(parts[0])
                            month = int(parts[1])
                            day = int(parts[2])
                            await date_add(pool, contact["id"], "birthday", month, day, year)
                        else:
                            # --MM-DD or MM-DD
                            month = int(parts[0])
                            day = int(parts[1])
                            await date_add(pool, contact["id"], "birthday", month, day)
                    except (ValueError, IndexError) as e:
                        logger.warning(f"Failed to parse birthday '{bday_value}': {e}")
            elif hasattr(bday_value, "year"):
                # Date object
                try:
                    await date_add(
                        pool,
                        contact["id"],
                        "birthday",
                        bday_value.month,
                        bday_value.day,
                        bday_value.year,
                    )
                except Exception as e:
                    logger.warning(f"Failed to add birthday: {e}")

        # ORG (Organization) → quick_facts.company
        if hasattr(vcard, "org"):
            org_value = vcard.org.value
            if isinstance(org_value, list) and org_value:
                await fact_set(pool, contact["id"], "company", org_value[0])
            elif isinstance(org_value, str):
                await fact_set(pool, contact["id"], "company", org_value)

        # TITLE (Job Title) → quick_facts.job_title
        if hasattr(vcard, "title"):
            await fact_set(pool, contact["id"], "job_title", vcard.title.value)

        # NOTE → notes
        if hasattr(vcard, "note"):
            note_value = vcard.note.value
            if note_value:
                # Split on --- if it was exported from our system
                note_parts = note_value.split("\n---\n")
                for note_text in note_parts:
                    if note_text.strip():
                        await note_create(pool, contact["id"], note_text.strip())

    return created_contacts
