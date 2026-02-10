"""Shared Pydantic response/request models for the Dashboard API.

Provides generic wrappers (ApiResponse, PaginatedResponse), error format,
pagination metadata, and common summary models used across all endpoints.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Base response wrappers
# ---------------------------------------------------------------------------


class ApiMeta(BaseModel):
    """Extensible metadata bag attached to every API response."""

    model_config = {"extra": "allow"}


class ApiResponse[T](BaseModel):
    """Generic API response wrapper.

    All successful responses follow ``{"data": T, "meta": {...}}``.
    """

    data: T
    meta: ApiMeta = Field(default_factory=ApiMeta)


class ErrorDetail(BaseModel):
    """Structured error payload."""

    code: str
    message: str
    butler: str | None = None
    details: dict | None = None


class ErrorResponse(BaseModel):
    """Standard error response envelope."""

    error: ErrorDetail


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------


class PaginationMeta(BaseModel):
    """Pagination metadata for list endpoints."""

    total: int
    offset: int
    limit: int

    @property
    def has_more(self) -> bool:
        """True when more items exist beyond the current page."""
        return self.offset + self.limit < self.total

    model_config = {"json_schema_extra": {"properties": {"has_more": {"type": "boolean"}}}}


class PaginatedResponse[T](BaseModel):
    """API response wrapper for paginated list endpoints.

    ``{"data": [T, ...], "meta": PaginationMeta}``
    """

    data: list[T]
    meta: PaginationMeta


# ---------------------------------------------------------------------------
# Common domain summaries
# ---------------------------------------------------------------------------


class ScheduleEntry(BaseModel):
    """A single scheduled task from butler.toml."""

    name: str
    cron: str
    prompt: str


class ModuleInfo(BaseModel):
    """Module status information."""

    name: str
    enabled: bool = True
    config: dict | None = None


class ButlerSummary(BaseModel):
    """Lightweight butler representation for list views."""

    name: str
    status: str
    port: int


class ButlerDetail(ButlerSummary):
    """Full butler detail with config, modules, skills, and schedule."""

    description: str | None = None
    db_name: str | None = None
    modules: list[ModuleInfo] = Field(default_factory=list)
    schedules: list[ScheduleEntry] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)


class SessionSummary(BaseModel):
    """Lightweight session representation for list views."""

    id: UUID
    prompt: str
    trigger_source: str
    success: bool | None = None
    started_at: datetime
    completed_at: datetime | None = None
    duration_ms: int | None = None


class HealthResponse(BaseModel):
    """Health-check response."""

    status: str


# ---------------------------------------------------------------------------
# Notification models (re-exported from sub-module)
# ---------------------------------------------------------------------------

from butlers.api.models.notification import NotificationStats, NotificationSummary  # noqa: E402

__all__ = [
    "ApiMeta",
    "ApiResponse",
    "ButlerDetail",
    "ButlerSummary",
    "ErrorDetail",
    "ErrorResponse",
    "HealthResponse",
    "ModuleInfo",
    "NotificationStats",
    "NotificationSummary",
    "PaginatedResponse",
    "PaginationMeta",
    "ScheduleEntry",
    "SessionSummary",
]
