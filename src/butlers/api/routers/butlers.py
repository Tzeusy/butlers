"""Butler discovery and status endpoints.

Scans the roster directory for butler configs, then probes each butler's
MCP server in parallel to determine live status.  Unreachable butlers
(timeout, connection refused, etc.) are reported with ``status: "down"``
rather than causing the entire request to fail.
"""

from __future__ import annotations

import asyncio
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
    ScheduleEntry,
    SkillInfo,
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

    schedules = [ScheduleEntry(name=s.name, cron=s.cron, prompt=s.prompt) for s in config.schedules]

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
# Skills endpoint
# ---------------------------------------------------------------------------


def _read_skills(butler_dir: Path) -> list[SkillInfo]:
    """Read skill names and SKILL.md content from the butler's skills/ directory."""
    skills_dir = butler_dir / "skills"
    if not skills_dir.is_dir():
        return []

    skills: list[SkillInfo] = []
    for entry in sorted(skills_dir.iterdir()):
        skill_md = entry / "SKILL.md"
        if entry.is_dir() and skill_md.exists():
            content = skill_md.read_text(encoding="utf-8")
            skills.append(SkillInfo(name=entry.name, content=content))

    return skills


@router.get("/{name}/skills", response_model=ApiResponse[list[SkillInfo]])
async def list_butler_skills(
    name: str,
    configs: list[ButlerConnectionInfo] = Depends(get_butler_configs),
    roster_dir: Path = Depends(_get_roster_dir),
) -> ApiResponse[list[SkillInfo]]:
    """Return skills for a single butler with name and SKILL.md content."""
    connection_info: ButlerConnectionInfo | None = None
    for cfg in configs:
        if cfg.name == name:
            connection_info = cfg
            break

    if connection_info is None:
        raise HTTPException(status_code=404, detail=f"Butler not found: {name}")

    butler_dir = roster_dir / name
    skills = _read_skills(butler_dir)

    return ApiResponse[list[SkillInfo]](data=skills)
