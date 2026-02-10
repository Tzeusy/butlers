"""Loans — track money lent or borrowed."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

import asyncpg

from butlers.tools.relationship.feed import _log_activity


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
