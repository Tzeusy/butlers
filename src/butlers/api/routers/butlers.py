"""Butler discovery and status endpoints.

Scans the roster directory for butler configs, then probes each butler's
MCP server in parallel to determine live status.  Unreachable butlers
(timeout, connection refused, etc.) are reported with ``status: "down"``
rather than causing the entire request to fail.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from butlers.api.deps import (
    ButlerConnectionInfo,
    ButlerUnreachableError,
    MCPClientManager,
    get_butler_configs,
    get_mcp_manager,
)
from butlers.api.models import (
    ApiResponse,
    ButlerDetail,
    ButlerSummary,
    ModuleInfo,
    ModuleStatus,
    ScheduleEntry,
)
from butlers.config import ConfigError, load_config

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/butlers", tags=["butlers"])

# Timeout (in seconds) for each individual butler status probe.
_STATUS_TIMEOUT_S = 5.0

# Default roster location relative to the repository root.
_DEFAULT_ROSTER_DIR = Path(__file__).resolve().parents[4] / "roster"


def _get_roster_dir() -> Path:
    """Return the roster directory path. Override in tests."""
    return _DEFAULT_ROSTER_DIR


# ---------------------------------------------------------------------------
# List endpoint
# ---------------------------------------------------------------------------


async def _probe_butler(
    mgr: MCPClientManager,
    info: ButlerConnectionInfo,
) -> ButlerSummary:
    """Probe a single butler's MCP server and return a summary.

    Attempts to connect via the MCP client and call ``ping()``.  If the
    butler responds, ``status`` is ``"ok"``.  Any failure (connection
    refused, timeout, unexpected error) results in ``status: "down"``.
    """
    try:
        client = await asyncio.wait_for(
            mgr.get_client(info.name),
            timeout=_STATUS_TIMEOUT_S,
        )
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
    """Return all discovered butlers with live status."""
    tasks = [_probe_butler(mgr, info) for info in configs]
    summaries = await asyncio.gather(*tasks)
    return ApiResponse[list[ButlerSummary]](data=list(summaries))


# ---------------------------------------------------------------------------
# Detail endpoint
# ---------------------------------------------------------------------------


@router.get("/{name}", response_model=ApiResponse[ButlerDetail])
async def get_butler_detail(
    name: str,
    configs: list[ButlerConnectionInfo] = Depends(get_butler_configs),
    mcp_manager: MCPClientManager = Depends(get_mcp_manager),
    roster_dir: Path = Depends(_get_roster_dir),
) -> ApiResponse[ButlerDetail]:
    """Return detailed information for a single butler.

    Looks up the butler by name in the roster directory, parses its config,
    discovers skills, and attempts to get live status via MCP.
    """
    connection_info: ButlerConnectionInfo | None = None
    for cfg in configs:
        if cfg.name == name:
            connection_info = cfg
            break

    if connection_info is None:
        raise HTTPException(status_code=404, detail=f"Butler not found: {name}")

    butler_dir = roster_dir / name
    try:
        config = load_config(butler_dir)
    except ConfigError:
        raise HTTPException(status_code=404, detail=f"Butler not found: {name}")

    modules = [
        ModuleInfo(name=mod_name, enabled=True, config=mod_cfg or None)
        for mod_name, mod_cfg in config.modules.items()
    ]

    schedules = [
        ScheduleEntry(name=s.name, cron=s.cron, prompt=s.prompt) for s in config.schedules
    ]

    skills = _discover_skills(butler_dir)
    status = await _get_live_status(name, mcp_manager)

    detail = ButlerDetail(
        name=config.name,
        port=config.port,
        status=status,
        description=config.description,
        db_name=config.db_name,
        modules=modules,
        schedules=schedules,
        skills=skills,
    )

    return ApiResponse[ButlerDetail](data=detail)


def _discover_skills(butler_dir: Path) -> list[str]:
    """List skill names from the butler's skills/ directory."""
    skills_dir = butler_dir / "skills"
    if not skills_dir.is_dir():
        return []

    skills: list[str] = []
    for entry in sorted(skills_dir.iterdir()):
        if entry.is_dir() and (entry / "SKILL.md").exists():
            skills.append(entry.name)

    return skills


async def _get_live_status(name: str, mcp_manager: MCPClientManager) -> str:
    """Attempt to determine a butler's live status via MCP ping."""
    try:
        client = await mcp_manager.get_client(name)
        await client.ping()
        return "online"
    except ButlerUnreachableError:
        return "offline"
    except Exception:
        logger.warning("Unexpected error pinging butler %s", name, exc_info=True)
        return "offline"


# ---------------------------------------------------------------------------
# Module health endpoint
# ---------------------------------------------------------------------------


async def _get_module_health_via_mcp(
    name: str,
    mcp_manager: MCPClientManager,
    module_names: list[str],
) -> list[ModuleStatus]:
    """Call the butler's MCP ``status()`` tool and extract per-module health.

    The ``status()`` tool returns a dict with a ``modules`` field listing
    loaded module names and a ``health`` field indicating overall butler
    health.  Modules present in the response are considered ``"connected"``;
    modules configured but absent from the live response are ``"unknown"``.

    If the butler is unreachable, all modules are returned with
    ``status="unknown"``.
    """
    try:
        client = await asyncio.wait_for(
            mcp_manager.get_client(name),
            timeout=_STATUS_TIMEOUT_S,
        )
        result = await asyncio.wait_for(
            client.call_tool("status", {}),
            timeout=_STATUS_TIMEOUT_S,
        )

        # Parse the status response — content[0].text is JSON
        status_data: dict = {}
        if result.content:
            text = result.content[0].text if hasattr(result.content[0], "text") else ""
            if text:
                status_data = json.loads(text)

        live_modules: set[str] = set(status_data.get("modules", []))
        butler_health = status_data.get("health", "unknown")

        modules: list[ModuleStatus] = []
        for mod_name in module_names:
            if mod_name in live_modules:
                # Module is loaded and running — derive status from butler health
                if butler_health == "ok":
                    mod_status = "connected"
                elif butler_health == "degraded":
                    mod_status = "degraded"
                else:
                    mod_status = "unknown"
            else:
                # Module is configured but not present in live response
                mod_status = "error"
                modules.append(
                    ModuleStatus(
                        name=mod_name,
                        enabled=True,
                        status=mod_status,
                        error="Module configured but not loaded by butler",
                    )
                )
                continue

            modules.append(
                ModuleStatus(name=mod_name, enabled=True, status=mod_status)
            )

        return modules

    except (ButlerUnreachableError, TimeoutError):
        return [
            ModuleStatus(name=mod_name, enabled=True, status="unknown")
            for mod_name in module_names
        ]
    except Exception:
        logger.warning(
            "Unexpected error fetching module health for butler %s",
            name,
            exc_info=True,
        )
        return [
            ModuleStatus(name=mod_name, enabled=True, status="unknown")
            for mod_name in module_names
        ]


@router.get("/{name}/modules", response_model=ApiResponse[list[ModuleStatus]])
async def get_butler_modules(
    name: str,
    configs: list[ButlerConnectionInfo] = Depends(get_butler_configs),
    mcp_manager: MCPClientManager = Depends(get_mcp_manager),
    roster_dir: Path = Depends(_get_roster_dir),
) -> ApiResponse[list[ModuleStatus]]:
    """Return module list with health status for a single butler.

    Reads the butler's configured modules from ``butler.toml``, then
    attempts to obtain live health status by calling the butler's MCP
    ``status()`` tool.  If the butler is unreachable, all modules are
    returned with ``status="unknown"``.
    """
    # Verify butler exists in discovered configs
    connection_info: ButlerConnectionInfo | None = None
    for cfg in configs:
        if cfg.name == name:
            connection_info = cfg
            break

    if connection_info is None:
        raise HTTPException(status_code=404, detail=f"Butler not found: {name}")

    # Load butler config to get module list
    butler_dir = roster_dir / name
    try:
        config = load_config(butler_dir)
    except ConfigError:
        raise HTTPException(status_code=404, detail=f"Butler not found: {name}")

    module_names = list(config.modules.keys())

    if not module_names:
        return ApiResponse[list[ModuleStatus]](data=[])

    # Get live module health via MCP
    module_statuses = await _get_module_health_via_mcp(
        name, mcp_manager, module_names
    )

    return ApiResponse[list[ModuleStatus]](data=module_statuses)
