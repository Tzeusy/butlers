"""Notifications API router — list and aggregate notification deliveries.

Provides endpoints for browsing notification history and retrieving
aggregated statistics for the dashboard overview.

Endpoints are stubs that return empty/zero data; real DB queries will be
wired in subsequent tasks.
"""

from __future__ import annotations

from fastapi import APIRouter

from butlers.api.models import ApiResponse, PaginatedResponse, PaginationMeta
from butlers.api.models.notification import NotificationStats, NotificationSummary

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("/", response_model=PaginatedResponse[NotificationSummary])
async def list_notifications(
    offset: int = 0,
    limit: int = 20,
) -> PaginatedResponse[NotificationSummary]:
    """Return a paginated list of notification deliveries.

    Stub implementation — returns an empty list.
    """
    return PaginatedResponse[NotificationSummary](
        data=[],
        meta=PaginationMeta(total=0, offset=offset, limit=limit),
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
