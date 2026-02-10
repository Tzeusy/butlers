"""Notification-related Pydantic models for the Dashboard API."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class NotificationSummary(BaseModel):
    """Notification record matching the Switchboard ``notifications`` table schema."""

    id: UUID
    source_butler: str
    channel: str
    recipient: str
    message: str
    metadata: dict | None = None
    status: str
    error: str | None = None
    session_id: UUID | None = None
    trace_id: str | None = None
    created_at: datetime
