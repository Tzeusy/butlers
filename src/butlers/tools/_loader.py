"""Dynamic loader for butler-specific tools from config directories.

Each butler keeps its tools in ``butlers/<name>/tools.py`` (the config directory).
This module provides ``register_butler_tools`` which uses ``importlib`` to load
those files and inject them into ``sys.modules`` as ``butlers.tools.<name>`` so
that existing import paths continue to work throughout the codebase.
"""

from __future__ import annotations

import importlib.util
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def register_butler_tools(
    butler_name: str,
    config_dir: Path,
) -> None:
    """Load ``tools.py`` from *config_dir* and register it as ``butlers.tools.<butler_name>``.

    Parameters
    ----------
    butler_name:
        The butler identifier (e.g. ``"switchboard"``).
    config_dir:
        Path to the butler's config directory (e.g. ``butlers/switchboard/``).
        Must contain a ``tools.py`` file.

    Raises
    ------
    FileNotFoundError
        If ``tools.py`` does not exist in *config_dir*.
    ImportError
        If the module cannot be loaded.
    """
    tools_path = config_dir / "tools.py"
    if not tools_path.exists():
        raise FileNotFoundError(f"No tools.py found in {config_dir}")

    module_name = f"butlers.tools.{butler_name}"

    # Skip if already registered.
    if module_name in sys.modules:
        return

    spec = importlib.util.spec_from_file_location(module_name, tools_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot create module spec for {tools_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    logger.debug("Registered butler tools: %s from %s", module_name, tools_path)


def _discover_butler_names(butlers_root: Path) -> list[str]:
    """Discover butler names that have a ``tools.py`` in their config directory.

    Scans ``butlers_root/*/tools.py`` and returns a sorted list of directory
    names (butler identifiers) that contain a ``tools.py`` file.

    Parameters
    ----------
    butlers_root:
        Path to the ``butlers/`` directory containing butler config dirs.

    Returns
    -------
    list[str]
        Sorted list of butler names with a ``tools.py`` file.
    """
    if not butlers_root.is_dir():
        return []
    return sorted(
        entry.name
        for entry in butlers_root.iterdir()
        if entry.is_dir() and (entry / "tools.py").exists()
    )


def register_all_butler_tools(butlers_root: Path | None = None) -> None:
    """Register tools for all discovered butlers.

    Scans ``butlers/*/tools.py`` to dynamically discover butler tools.
    No hardcoded butler names — adding a new butler with a ``tools.py``
    file is automatically picked up.

    Parameters
    ----------
    butlers_root:
        Path to the ``butlers/`` directory containing butler config dirs.
        If *None*, auto-detects by walking up from this file's location
        to find the repository root.
    """
    if butlers_root is None:
        # Auto-detect: this file is at src/butlers/tools/_loader.py
        # repo root is 4 levels up: _loader.py -> tools/ -> butlers/ -> src/ -> repo root
        repo_root = Path(__file__).resolve().parent.parent.parent.parent
        butlers_root = repo_root / "butlers"

    for name in _discover_butler_names(butlers_root):
        config_dir = butlers_root / name
        try:
            register_butler_tools(name, config_dir)
        except Exception:
            logger.warning("Failed to register tools for butler: %s", name, exc_info=True)
