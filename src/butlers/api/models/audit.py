"""Pydantic models for the audit log API.

Maps to the ``dashboard_audit_log`` table in the Switchboard database.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class AuditEntry(BaseModel):
    """Single audit log entry from the dashboard_audit_log table."""

    id: UUID
    butler: str
    operation: str
    request_summary: dict = Field(default_factory=dict)
    result: str
    error: str | None = None
    user_context: dict = Field(default_factory=dict)
    created_at: datetime
