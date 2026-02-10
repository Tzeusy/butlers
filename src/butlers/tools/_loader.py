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

# Butler names whose tools live in the config directories.
BUTLER_NAMES = ("general", "health", "heartbeat", "relationship", "switchboard")


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


def register_all_butler_tools(butlers_root: Path | None = None) -> None:
    """Register tools for all known butlers.

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

    for name in BUTLER_NAMES:
        config_dir = butlers_root / name
        tools_path = config_dir / "tools.py"
        if tools_path.exists():
            try:
                register_butler_tools(name, config_dir)
            except Exception:
                logger.warning("Failed to register tools for butler: %s", name, exc_info=True)
