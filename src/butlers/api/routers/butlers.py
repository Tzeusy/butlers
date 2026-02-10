"""Butler discovery and status endpoints.

Provides list and detail views for butler instances registered in the
system.  Placeholder implementations return empty/404 responses — the
actual data-fetching logic will be added in subsequent tasks.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from butlers.api.models import ApiResponse
from butlers.api.models.butler import ButlerDetail, ButlerSummary

router = APIRouter(prefix="/api/butlers", tags=["butlers"])


@router.get("/", response_model=ApiResponse[list[ButlerSummary]])
async def list_butlers() -> ApiResponse[list[ButlerSummary]]:
    """Return a list of all known butlers.

    Placeholder — returns an empty list until butler discovery is wired up.
    """
    return ApiResponse[list[ButlerSummary]](data=[])


@router.get("/{name}", response_model=ApiResponse[ButlerDetail])
async def get_butler(name: str) -> ApiResponse[ButlerDetail]:
    """Return detailed information for a single butler.

    Placeholder — always raises 404 until butler lookup is wired up.
    """
    raise HTTPException(status_code=404, detail=f"Butler '{name}' not found")
