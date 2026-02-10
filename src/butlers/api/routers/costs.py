"""Cost and usage tracking endpoints.

Provides aggregate cost summaries, daily time series, and
top-spending sessions. Cost estimation uses the pricing.toml
configuration loaded at startup.
"""

from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, Depends, Query

from butlers.api.deps import (
    ButlerConnectionInfo,
    ButlerUnreachableError,
    MCPClientManager,
    get_butler_configs,
    get_mcp_manager,
    get_pricing,
)
from butlers.api.models import ApiResponse, CostSummary, DailyCost, TopSession
from butlers.api.pricing import PricingConfig, estimate_session_cost

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/costs", tags=["costs"])

_STATUS_TIMEOUT_S = 5.0


async def _get_butler_session_stats(
    mgr: MCPClientManager,
    info: ButlerConnectionInfo,
    pricing: PricingConfig,
    period: str,
) -> tuple[str, float, int, int, int, dict[str, float]]:
    """Query a butler for session cost stats.

    Returns (name, cost, sessions, input_tokens, output_tokens, by_model).
    """
    try:
        client = await asyncio.wait_for(mgr.get_client(info.name), timeout=_STATUS_TIMEOUT_S)
        result = await asyncio.wait_for(
            client.call_tool("sessions_summary", {"period": period}),
            timeout=_STATUS_TIMEOUT_S,
        )
        if result.content:
            text = result.content[0].text if hasattr(result.content[0], "text") else ""
            if text:
                data = json.loads(text)
                total_cost = 0.0
                by_model: dict[str, float] = {}
                for model_id, stats in data.get("by_model", {}).items():
                    cost = estimate_session_cost(
                        pricing,
                        model_id,
                        stats.get("input_tokens", 0),
                        stats.get("output_tokens", 0),
                    )
                    total_cost += cost
                    by_model[model_id] = by_model.get(model_id, 0.0) + cost
                return (
                    info.name,
                    total_cost,
                    data.get("total_sessions", 0),
                    data.get("total_input_tokens", 0),
                    data.get("total_output_tokens", 0),
                    by_model,
                )
    except (ButlerUnreachableError, TimeoutError, Exception):
        pass
    return (info.name, 0.0, 0, 0, 0, {})


@router.get("/summary", response_model=ApiResponse[CostSummary])
async def get_cost_summary(
    period: str = Query("today", pattern="^(today|7d|30d)$"),
    mgr: MCPClientManager = Depends(get_mcp_manager),
    configs: list[ButlerConnectionInfo] = Depends(get_butler_configs),
    pricing: PricingConfig = Depends(get_pricing),
) -> ApiResponse[CostSummary]:
    """Return aggregate cost summary across all butlers."""
    tasks = [_get_butler_session_stats(mgr, info, pricing, period) for info in configs]
    results = await asyncio.gather(*tasks)

    total_cost = 0.0
    total_sessions = 0
    total_input = 0
    total_output = 0
    by_butler: dict[str, float] = {}
    by_model: dict[str, float] = {}

    for name, cost, sessions, inp, out, models in results:
        total_cost += cost
        total_sessions += sessions
        total_input += inp
        total_output += out
        if cost > 0:
            by_butler[name] = cost
        for model_id, model_cost in models.items():
            by_model[model_id] = by_model.get(model_id, 0.0) + model_cost

    summary = CostSummary(
        period=period,
        total_cost_usd=round(total_cost, 6),
        total_sessions=total_sessions,
        total_input_tokens=total_input,
        total_output_tokens=total_output,
        by_butler=by_butler,
        by_model=by_model,
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
