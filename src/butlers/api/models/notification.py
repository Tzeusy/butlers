"""Pydantic models for the notifications API.

Maps to the ``notifications`` database table and provides an aggregation
model for dashboard statistics.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class NotificationSummary(BaseModel):
    """Lightweight notification representation for list views.

    Mirrors the columns of the ``notifications`` DB table, excluding
    internal tracing fields (metadata, session_id, trace_id).
    """

    id: UUID
    source_butler: str
    channel: str
    recipient: str | None = None
    message: str
    status: str
    error: str | None = None
    created_at: datetime


class NotificationStats(BaseModel):
    """Aggregated notification statistics for the dashboard overview.

    Provides total counts, sent/failed breakdowns, and per-channel /
    per-butler distributions.
    """

    total: int
    sent: int
    failed: int
    by_channel: dict[str, int]
    by_butler: dict[str, int]
