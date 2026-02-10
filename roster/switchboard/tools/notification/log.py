"""Notification logging — log notification deliveries."""

from __future__ import annotations

import json
from typing import Any

import asyncpg


async def log_notification(
    pool: asyncpg.Pool,
    source_butler: str,
    channel: str,
    recipient: str,
    message: str,
    metadata: dict[str, Any] | None = None,
    status: str = "sent",
    error: str | None = None,
    session_id: str | None = None,
    trace_id: str | None = None,
) -> str:
    """Log a notification delivery to the notifications table.

    Returns the UUID of the created notification log entry.

    Parameters
    ----------
    pool:
        Database connection pool.
    source_butler:
        Name of the butler that initiated the delivery.
    channel:
        Delivery channel (e.g., "telegram", "email").
    recipient:
        Recipient identifier (chat_id, email address, etc.).
    message:
        The notification message body.
    metadata:
        Optional additional metadata dict.
    status:
        Delivery status (e.g., "sent", "failed").
    error:
        Error message if delivery failed.
    session_id:
        Optional session UUID for tracing.
    trace_id:
        Optional OpenTelemetry trace ID.
    """
    row = await pool.fetchrow(
        """
        INSERT INTO notifications
            (source_butler, channel, recipient, message, metadata, status, error,
             session_id, trace_id)
        VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7, $8, $9)
        RETURNING id
        """,
        source_butler,
        channel,
        recipient,
        message,
        json.dumps(metadata or {}),
        status,
        error,
        session_id,
        trace_id,
    )
    return str(row["id"])
