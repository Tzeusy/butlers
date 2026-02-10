"""Memory Butler MCP tools.

Thin tool wrappers that delegate to storage.py and search.py for the
actual logic.  Each function accepts an asyncpg Pool (and optionally an
EmbeddingEngine) and returns a result suitable for MCP tool responses.
"""

from __future__ import annotations

import importlib.util
import json
import logging
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from asyncpg import Pool

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Load sibling modules from disk (roster/ is not a Python package).
# ---------------------------------------------------------------------------

_MODULE_DIR = Path(__file__).resolve().parent


def _load_module(name: str):
    path = _MODULE_DIR / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_storage = _load_module("storage")
_search = _load_module("search")


# ---------------------------------------------------------------------------
# Writing tools
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Reading tools
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Feedback tools
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Management tools
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Context building
# ---------------------------------------------------------------------------
