"""Butler detail endpoint — single butler lookup with live status.

Provides GET /api/butlers/{name} which returns full butler detail including
config summary, module list, skills, schedule, and live status from MCP.
"""

from __future__ import annotations

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
    ModuleInfo,
    ScheduleEntry,
)
from butlers.config import ConfigError, load_config

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/butlers", tags=["butlers"])

# Default roster location relative to the repository root.
_DEFAULT_ROSTER_DIR = Path(__file__).resolve().parents[4] / "roster"


def _get_roster_dir() -> Path:
    """Return the roster directory path. Override in tests."""
    return _DEFAULT_ROSTER_DIR


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

    Returns 404 if the butler name is not found in the roster.
    """
    # Find the connection info for this butler
    connection_info: ButlerConnectionInfo | None = None
    for cfg in configs:
        if cfg.name == name:
            connection_info = cfg
            break

    if connection_info is None:
        raise HTTPException(status_code=404, detail=f"Butler not found: {name}")

    # Load full config from butler.toml
    butler_dir = roster_dir / name
    try:
        config = load_config(butler_dir)
    except ConfigError:
        raise HTTPException(status_code=404, detail=f"Butler not found: {name}")

    # Build module info
    modules = [
        ModuleInfo(name=mod_name, enabled=True, config=mod_cfg or None)
        for mod_name, mod_cfg in config.modules.items()
    ]

    # Build schedule entries
    schedules = [ScheduleEntry(name=s.name, cron=s.cron, prompt=s.prompt) for s in config.schedules]

    # Discover skills from the skills/ directory
    skills = _discover_skills(butler_dir)

    # Determine live status via MCP
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
    """List skill names from the butler's skills/ directory.

    Each subdirectory of ``skills/`` that contains a ``SKILL.md`` file is
    considered a valid skill. Returns a sorted list of skill directory names.
    """
    skills_dir = butler_dir / "skills"
    if not skills_dir.is_dir():
        return []

    skills: list[str] = []
    for entry in sorted(skills_dir.iterdir()):
        if entry.is_dir() and (entry / "SKILL.md").exists():
            skills.append(entry.name)

    return skills


async def _get_live_status(name: str, mcp_manager: MCPClientManager) -> str:
    """Attempt to determine a butler's live status via MCP ping.

    Returns "online" if the butler responds, "offline" if unreachable.
    """
    try:
        client = await mcp_manager.get_client(name)
        await client.ping()
        return "online"
    except ButlerUnreachableError:
        return "offline"
    except Exception:
        logger.warning("Unexpected error pinging butler %s", name, exc_info=True)
        return "offline"
