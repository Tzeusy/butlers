"""Cost and usage tracking endpoints.

Provides aggregate cost summaries, daily time series, and
top-spending sessions. Cost estimation uses the pricing.toml
configuration loaded at startup.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter

from butlers.api.models import ApiResponse, CostSummary, DailyCost, TopSession

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/costs", tags=["costs"])


@router.get("/summary", response_model=ApiResponse[CostSummary])
async def get_cost_summary() -> ApiResponse[CostSummary]:
    """Return aggregate cost summary across all butlers.

    Note: Returns placeholder data until database integration is complete.
    """
    summary = CostSummary(
        total_cost_usd=0.0,
        total_sessions=0,
        total_input_tokens=0,
        total_output_tokens=0,
    )
    return ApiResponse[CostSummary](data=summary)


@router.get("/daily", response_model=ApiResponse[list[DailyCost]])
async def get_daily_costs() -> ApiResponse[list[DailyCost]]:
    """Return daily cost time series.

    Note: Returns empty list until database integration is complete.
    """
    return ApiResponse[list[DailyCost]](data=[])


@router.get("/top-sessions", response_model=ApiResponse[list[TopSession]])
async def get_top_sessions() -> ApiResponse[list[TopSession]]:
    """Return most expensive sessions.

    Note: Returns empty list until database integration is complete.
    """
    return ApiResponse[list[TopSession]](data=[])
