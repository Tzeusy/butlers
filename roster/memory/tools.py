"""Memory Butler MCP tools.

Thin tool wrappers that delegate to storage.py and search.py for the
actual logic.  Each function accepts an asyncpg Pool (and optionally an
EmbeddingEngine) and returns a result suitable for MCP tool responses.
"""

from __future__ import annotations

import importlib.util
import logging
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
# Embedding engine (loaded once, shared across all tool invocations)
# ---------------------------------------------------------------------------

_embedding_mod = _load_module("embedding")
EmbeddingEngine = _embedding_mod.EmbeddingEngine


def get_embedding_engine() -> Any:
    """Get or create the shared EmbeddingEngine singleton.

    Lazy-loads the model on first call.
    """
    global _embedding_engine
    if _embedding_engine is None:
        _embedding_engine = EmbeddingEngine()
    return _embedding_engine


_embedding_engine: Any = None


# ---------------------------------------------------------------------------
# Writing tools
# ---------------------------------------------------------------------------


async def memory_store_episode(
    pool: Pool,
    content: str,
    butler: str,
    *,
    session_id: str | None = None,
    importance: float = 5.0,
) -> dict[str, Any]:
    """Store a raw episode from a CC session.

    Delegates to the storage layer and returns an MCP-friendly dict with the
    new episode's ID and expiry timestamp.
    """
    result = await _storage.store_episode(
        pool, content, butler, session_id=session_id, importance=importance
    )
    return {
        "id": str(result["id"]),
        "expires_at": result["expires_at"].isoformat(),
    }


async def memory_store_fact(
    pool: Pool,
    embedding_engine,
    subject: str,
    predicate: str,
    content: str,
    *,
    importance: float = 5.0,
    permanence: str = "standard",
    scope: str = "global",
    tags: list[str] | None = None,
) -> dict[str, Any]:
    """Store a distilled fact, automatically superseding any existing match.

    Delegates to the storage layer and returns an MCP-friendly dict with the
    new fact's ID and the superseded fact's ID (if any).
    """
    result = await _storage.store_fact(
        pool,
        embedding_engine,
        subject,
        predicate,
        content,
        importance=importance,
        permanence=permanence,
        scope=scope,
        tags=tags,
    )
    return {
        "id": str(result["id"]),
        "superseded_id": (
            str(result.get("superseded_id")) if result.get("superseded_id") else None
        ),
    }


async def memory_store_rule(
    pool: Pool,
    embedding_engine,
    content: str,
    *,
    scope: str = "global",
    tags: list[str] | None = None,
) -> dict[str, Any]:
    """Store a new behavioral rule as a candidate.

    Delegates to the storage layer and returns an MCP-friendly dict with the
    new rule's ID.
    """
    result = await _storage.store_rule(
        pool, embedding_engine, content, scope=scope, tags=tags
    )
    return {"id": str(result["id"])}


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
