"""Butler list endpoint — discover butlers and probe live status.

Scans the roster directory for butler configs, then probes each butler's
MCP server in parallel to determine live status.  Unreachable butlers
(timeout, connection refused, etc.) are reported with ``status: "down"``
rather than causing the entire request to fail.

Route:
    GET /api/butlers  ->  ApiResponse[list[ButlerSummary]]
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
from butlers.api.models import ApiResponse, ButlerSummary

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/butlers", tags=["butlers"])

# Timeout (in seconds) for each individual butler status probe.
_STATUS_TIMEOUT_S = 5.0


async def _probe_butler(
    mgr: MCPClientManager,
    info: ButlerConnectionInfo,
) -> ButlerSummary:
    """Probe a single butler's MCP server and return a summary.

    Attempts to connect via the MCP client and call ``ping()``.  If the
    butler responds, ``status`` is ``"ok"``.  Any failure (connection
    refused, timeout, unexpected error) results in ``status: "down"``.

    Parameters
    ----------
    mgr:
        The MCP client manager with butler connection info pre-registered.
    info:
        Static config for the butler being probed.

    Returns
    -------
    ButlerSummary
        Always returns a summary — never raises.
    """
    try:
        client = await asyncio.wait_for(
            mgr.get_client(info.name),
            timeout=_STATUS_TIMEOUT_S,
        )
        # If we got a connected client, the butler is reachable.
        # Try a lightweight ping to confirm it's responsive.
        await asyncio.wait_for(client.ping(), timeout=_STATUS_TIMEOUT_S)
        status = "ok"
    except ButlerUnreachableError:
        logger.debug("Butler %s is unreachable", info.name)
        status = "down"
    except TimeoutError:
        logger.debug("Butler %s timed out", info.name)
        status = "down"
    except Exception:
        logger.warning("Unexpected error probing butler %s", info.name, exc_info=True)
        status = "down"

    return ButlerSummary(
        name=info.name,
        status=status,
        port=info.port,
        description=info.description,
    )


@router.get("", response_model=ApiResponse[list[ButlerSummary]])
async def list_butlers(
    mgr: MCPClientManager = Depends(get_mcp_manager),
    configs: list[ButlerConnectionInfo] = Depends(get_butler_configs),
) -> ApiResponse[list[ButlerSummary]]:
    """Return all discovered butlers with live status.

    Discovers butlers from the roster directory (pre-loaded at startup),
    probes each butler's MCP server in parallel with a per-butler timeout,
    and returns an aggregated list.  Unreachable butlers are included with
    ``status: "down"`` rather than being omitted.
    """
    tasks = [_probe_butler(mgr, info) for info in configs]
    summaries = await asyncio.gather(*tasks)

    return ApiResponse[list[ButlerSummary]](data=list(summaries))
