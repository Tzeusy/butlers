"""Schedule-specific Pydantic models.

Provides request/response models for the schedules CRUD endpoints.
Reads come from the butler's ``scheduled_tasks`` table; writes are
proxied through MCP tool calls.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class Schedule(BaseModel):
    """Full scheduled task record from the ``scheduled_tasks`` table."""

    id: UUID
    name: str
    cron: str
    prompt: str
    source: str = "db"
    enabled: bool = True
    next_run_at: datetime | None = None
    last_run_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class ScheduleCreate(BaseModel):
    """Request body for creating a new scheduled task."""

    name: str
    cron: str
    prompt: str


class ScheduleUpdate(BaseModel):
    """Request body for updating a scheduled task.

    All fields are optional; only provided fields are applied.
    """

    name: str | None = None
    cron: str | None = None
    prompt: str | None = None
    enabled: bool | None = None
