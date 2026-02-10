"""Active issues aggregation endpoint.

Scans all butlers for problems: unreachable services, module failures,
and other anomalies. Returns a sorted list of active issues.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends

from butlers.api.deps import (
    ButlerConnectionInfo,
    ButlerUnreachableError,
    MCPClientManager,
    get_butler_configs,
    get_mcp_manager,
)
from butlers.api.models import ApiResponse, Issue

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/issues", tags=["issues"])

_STATUS_TIMEOUT_S = 5.0


async def _check_butler_reachability(
    mgr: MCPClientManager,
    info: ButlerConnectionInfo,
) -> Issue | None:
    """Check if a butler is reachable. Returns an Issue if not."""
    try:
        client = await asyncio.wait_for(
            mgr.get_client(info.name),
            timeout=_STATUS_TIMEOUT_S,
        )
        await asyncio.wait_for(client.ping(), timeout=_STATUS_TIMEOUT_S)
        return None
    except (ButlerUnreachableError, TimeoutError):
        return Issue(
            severity="critical",
            type="unreachable",
            butler=info.name,
            description=f"Butler '{info.name}' is not responding",
            link=f"/butlers/{info.name}",
        )
    except Exception:
        logger.warning("Unexpected error checking butler %s", info.name, exc_info=True)
        return Issue(
            severity="critical",
            type="unreachable",
            butler=info.name,
            description=f"Butler '{info.name}' check failed unexpectedly",
            link=f"/butlers/{info.name}",
        )


@router.get("", response_model=ApiResponse[list[Issue]])
async def list_issues(
    mgr: MCPClientManager = Depends(get_mcp_manager),
    configs: list[ButlerConnectionInfo] = Depends(get_butler_configs),
) -> ApiResponse[list[Issue]]:
    """Return all active issues across butler infrastructure.

    Checks all butlers in parallel for:
    - Unreachable services (critical)
    - Module failures (warning) — stub for now
    - Notification failures (warning) — stub for now

    Results sorted by severity (critical first), then butler name.
    """
    tasks = [_check_butler_reachability(mgr, info) for info in configs]
    results = await asyncio.gather(*tasks)

    issues: list[Issue] = [r for r in results if r is not None]

    # Sort: critical first, then by butler name
    severity_order = {"critical": 0, "warning": 1}
    issues.sort(key=lambda i: (severity_order.get(i.severity, 2), i.butler))

    return ApiResponse[list[Issue]](data=issues)
