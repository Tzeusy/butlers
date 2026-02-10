"""Notification history endpoint — paginated, filterable notification log.

Queries the Switchboard butler's ``notifications`` table and returns results
in the standard ``PaginatedResponse`` envelope.
"""

from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, Query

from butlers.api.db import DatabaseManager
from butlers.api.models import ApiResponse, PaginatedResponse, PaginationMeta
from butlers.api.models.notification import NotificationStats, NotificationSummary

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


def _get_db_manager() -> DatabaseManager:
    """Dependency stub — overridden at app startup or in tests."""
    raise RuntimeError("DatabaseManager not initialized")


@router.get("/", response_model=PaginatedResponse[NotificationSummary])
async def list_notifications(
    offset: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(50, ge=1, le=200, description="Max records to return"),
    butler: str | None = Query(None, description="Filter by source butler name"),
    channel: str | None = Query(None, description="Filter by delivery channel"),
    status: str | None = Query(None, description="Filter by status (sent/failed/pending)"),
    since: datetime | None = Query(None, description="Only notifications created after this time"),
    until: datetime | None = Query(None, description="Only notifications created before this time"),
    db: DatabaseManager = Depends(_get_db_manager),
) -> PaginatedResponse[NotificationSummary]:
    """Return paginated notification history from the Switchboard database.

    Supports filtering by butler, channel, status, and date range.
    Results are ordered by ``created_at DESC`` (newest first).
    """
    pool = db.pool("switchboard")

    # Build dynamic WHERE clause
    conditions: list[str] = []
    args: list[object] = []
    idx = 1

    if butler is not None:
        conditions.append(f"source_butler = ${idx}")
        args.append(butler)
        idx += 1

    if channel is not None:
        conditions.append(f"channel = ${idx}")
        args.append(channel)
        idx += 1

    if status is not None:
        conditions.append(f"status = ${idx}")
        args.append(status)
        idx += 1

    if since is not None:
        conditions.append(f"created_at >= ${idx}")
        args.append(since)
        idx += 1

    if until is not None:
        conditions.append(f"created_at <= ${idx}")
        args.append(until)
        idx += 1

    where_clause = (" WHERE " + " AND ".join(conditions)) if conditions else ""

    # Count query
    count_sql = f"SELECT count(*) FROM notifications{where_clause}"
    count_row = await pool.fetchval(count_sql, *args)
    total = count_row or 0

    # Data query
    data_sql = (
        f"SELECT id, source_butler, channel, recipient, message, metadata, "
        f"status, error, session_id, trace_id, created_at "
        f"FROM notifications{where_clause} "
        f"ORDER BY created_at DESC "
        f"OFFSET ${idx} LIMIT ${idx + 1}"
    )
    args.extend([offset, limit])

    rows = await pool.fetch(data_sql, *args)

    notifications = [
        NotificationSummary(
            id=row["id"],
            source_butler=row["source_butler"],
            channel=row["channel"],
            recipient=row["recipient"],
            message=row["message"],
            metadata=dict(row["metadata"]) if row["metadata"] else None,
            status=row["status"],
            error=row["error"],
            session_id=row["session_id"],
            trace_id=row["trace_id"],
            created_at=row["created_at"],
        )
        for row in rows
    ]

    return PaginatedResponse[NotificationSummary](
        data=notifications,
        meta=PaginationMeta(total=total, offset=offset, limit=limit),
    )


@router.get("/stats", response_model=ApiResponse[NotificationStats])
async def notification_stats() -> ApiResponse[NotificationStats]:
    """Return aggregated notification statistics.

    Stub implementation — returns zero counts.
    """
    return ApiResponse[NotificationStats](
        data=NotificationStats(
            total=0,
            sent=0,
            failed=0,
            by_channel={},
            by_butler={},
        ),
    )
