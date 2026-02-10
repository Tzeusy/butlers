"""Memory Butler MCP tools.

Thin tool wrappers that delegate to storage.py and search.py for the
actual logic.  Each function accepts an asyncpg Pool (and optionally an
EmbeddingEngine) and returns a result suitable for MCP tool responses.
"""

from __future__ import annotations

import importlib.util
import logging
import uuid
from datetime import datetime
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
# Serialization helper
# ---------------------------------------------------------------------------


def _serialize_row(row: dict) -> dict[str, Any]:
    """Convert a row dict to JSON-serializable format."""
    result = {}
    for key, value in row.items():
        if isinstance(value, uuid.UUID):
            result[key] = str(value)
        elif isinstance(value, datetime):
            result[key] = value.isoformat()
        else:
            result[key] = value
    return result


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


async def memory_search(
    pool: Pool,
    embedding_engine,
    query: str,
    *,
    types: list[str] | None = None,
    scope: str | None = None,
    mode: str = "hybrid",
    limit: int = 10,
    min_confidence: float = 0.2,
) -> list[dict[str, Any]]:
    """Search across memory types using hybrid, semantic, or keyword mode.

    Delegates to _search.search() and serializes the results for JSON output.
    """
    results = await _search.search(
        pool,
        query,
        embedding_engine,
        types=types,
        scope=scope,
        mode=mode,
        limit=limit,
        min_confidence=min_confidence,
    )
    return [_serialize_row(r) for r in results]


async def memory_recall(
    pool: Pool,
    embedding_engine,
    topic: str,
    *,
    scope: str | None = None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """High-level composite-scored retrieval of relevant facts and rules.

    Delegates to _search.recall() and serializes the results for JSON output.
    """
    results = await _search.recall(
        pool,
        topic,
        embedding_engine,
        scope=scope,
        limit=limit,
    )
    return [_serialize_row(r) for r in results]


async def memory_get(
    pool: Pool,
    memory_type: str,
    memory_id: str,
) -> dict[str, Any] | None:
    """Retrieve a specific memory by type and ID.

    Converts the string memory_id to a UUID, delegates to _storage.get_memory(),
    and serializes the result for JSON output.
    """
    result = await _storage.get_memory(pool, memory_type, uuid.UUID(memory_id))
    if result is None:
        return None
    return _serialize_row(result)


# ---------------------------------------------------------------------------
# Feedback tools
# ---------------------------------------------------------------------------


async def memory_confirm(
    pool: Pool,
    memory_type: str,
    memory_id: str,
) -> dict[str, Any]:
    """Confirm a fact or rule is still accurate, resetting confidence decay.

    Converts memory_id to UUID, delegates to _storage.confirm_memory().
    Returns {"confirmed": bool}.
    """
    result = await _storage.confirm_memory(pool, memory_type, uuid.UUID(memory_id))
    return {"confirmed": result}


async def memory_mark_helpful(
    pool: Pool,
    rule_id: str,
) -> dict[str, Any]:
    """Report a rule was applied successfully.

    Delegates to _storage.mark_helpful() and returns the serialized result.
    """
    result = await _storage.mark_helpful(pool, uuid.UUID(rule_id))
    if result is None:
        return {"error": "Rule not found"}
    return _serialize_row(result)


async def memory_mark_harmful(
    pool: Pool,
    rule_id: str,
    *,
    reason: str | None = None,
) -> dict[str, Any]:
    """Report a rule caused problems.

    Delegates to _storage.mark_harmful() and returns the serialized result.
    """
    result = await _storage.mark_harmful(pool, uuid.UUID(rule_id), reason=reason)
    if result is None:
        return {"error": "Rule not found"}
    return _serialize_row(result)


# ---------------------------------------------------------------------------
# Management tools
# ---------------------------------------------------------------------------


async def memory_forget(
    pool: Pool,
    memory_type: str,
    memory_id: str,
) -> dict[str, Any]:
    """Soft-delete a memory by type and ID.

    Args:
        pool: asyncpg connection pool.
        memory_type: One of 'episode', 'fact', 'rule'.
        memory_id: UUID string of the memory to forget.

    Returns:
        Dict with key ``forgotten`` (bool) indicating success.
    """
    result = await _storage.forget_memory(pool, memory_type, uuid.UUID(memory_id))
    return {"forgotten": result}


async def memory_stats(
    pool: Pool,
    *,
    scope: str | None = None,
) -> dict[str, Any]:
    """Return system health indicators across all memory types.

    Args:
        pool: asyncpg connection pool.
        scope: Optional scope filter for facts and rules.

    Returns:
        Dict with keys ``episodes``, ``facts``, ``rules``, each containing
        count breakdowns by status/maturity.
    """
    # --- Episodes ---
    ep_total = await pool.fetchval("SELECT COUNT(*) FROM episodes")
    ep_unconsolidated = await pool.fetchval(
        "SELECT COUNT(*) FROM episodes WHERE consolidated = false"
    )
    ep_backlog_age = await pool.fetchval(
        "SELECT EXTRACT(EPOCH FROM (now() - MIN(created_at))) / 3600 "
        "FROM episodes WHERE consolidated = false"
    )

    # --- Facts ---
    scope_filter_facts = ""
    scope_params: list[Any] = []
    if scope is not None:
        scope_filter_facts = " AND scope IN ('global', $1)"
        scope_params = [scope]

    facts_active = await pool.fetchval(
        "SELECT COUNT(*) FROM facts WHERE validity = 'active'"
        " AND (metadata->>'status' IS NULL OR metadata->>'status' != 'fading')"
        + scope_filter_facts,
        *scope_params,
    )
    facts_fading = await pool.fetchval(
        "SELECT COUNT(*) FROM facts WHERE validity = 'active'"
        " AND metadata->>'status' = 'fading'"
        + scope_filter_facts,
        *scope_params,
    )
    facts_superseded = await pool.fetchval(
        "SELECT COUNT(*) FROM facts WHERE validity = 'superseded'" + scope_filter_facts,
        *scope_params,
    )
    facts_expired = await pool.fetchval(
        "SELECT COUNT(*) FROM facts WHERE validity = 'expired'" + scope_filter_facts,
        *scope_params,
    )

    # --- Rules ---
    scope_filter_rules = ""
    if scope is not None:
        scope_filter_rules = " AND scope IN ('global', $1)"

    rules_candidate = await pool.fetchval(
        "SELECT COUNT(*) FROM rules WHERE maturity = 'candidate'"
        " AND (metadata->>'forgotten')::boolean IS NOT TRUE"
        + scope_filter_rules,
        *scope_params,
    )
    rules_established = await pool.fetchval(
        "SELECT COUNT(*) FROM rules WHERE maturity = 'established'"
        " AND (metadata->>'forgotten')::boolean IS NOT TRUE"
        + scope_filter_rules,
        *scope_params,
    )
    rules_proven = await pool.fetchval(
        "SELECT COUNT(*) FROM rules WHERE maturity = 'proven'"
        " AND (metadata->>'forgotten')::boolean IS NOT TRUE"
        + scope_filter_rules,
        *scope_params,
    )
    rules_anti_pattern = await pool.fetchval(
        "SELECT COUNT(*) FROM rules WHERE maturity = 'anti_pattern'" + scope_filter_rules,
        *scope_params,
    )
    rules_forgotten = await pool.fetchval(
        "SELECT COUNT(*) FROM rules WHERE (metadata->>'forgotten')::boolean IS TRUE"
        + scope_filter_rules,
        *scope_params,
    )

    return {
        "episodes": {
            "total": ep_total,
            "unconsolidated": ep_unconsolidated,
            "backlog_age_hours": float(ep_backlog_age) if ep_backlog_age is not None else None,
        },
        "facts": {
            "active": facts_active,
            "fading": facts_fading,
            "superseded": facts_superseded,
            "expired": facts_expired,
        },
        "rules": {
            "candidate": rules_candidate,
            "established": rules_established,
            "proven": rules_proven,
            "anti_pattern": rules_anti_pattern,
            "forgotten": rules_forgotten,
        },
    }


# ---------------------------------------------------------------------------
# Context building
# ---------------------------------------------------------------------------


async def memory_context(
    pool: Pool,
    embedding_engine,
    trigger_prompt: str,
    butler: str,
    *,
    token_budget: int = 3000,
) -> str:
    """Build a memory context block for injection into a CC system prompt.

    Retrieves the most relevant facts and rules via composite-scored recall,
    then formats them into a structured text block that fits within the
    given token budget.

    Args:
        pool: asyncpg connection pool.
        embedding_engine: EmbeddingEngine instance for semantic search.
        trigger_prompt: The prompt/topic to search for relevant memories.
        butler: Butler name used as scope filter.
        token_budget: Maximum approximate token count (1 token ~ 4 chars).

    Returns:
        Formatted memory context string with Key Facts and Active Rules sections.
    """
    results = await _search.recall(
        pool, trigger_prompt, embedding_engine, scope=butler, limit=20
    )

    # Separate facts and rules, already sorted by composite_score descending
    facts = [r for r in results if r.get("memory_type") == "fact"]
    rules = [r for r in results if r.get("memory_type") == "rule"]

    header = "# Memory Context\n"
    facts_header = "\n## Key Facts\n"
    rules_header = "\n## Active Rules\n"

    # Start building text within budget
    lines: list[str] = [header]
    budget_chars = token_budget * 4

    def _chars_used() -> int:
        return sum(len(line) for line in lines)

    # Add facts section
    if facts:
        lines.append(facts_header)
        for f in facts:
            subject = f.get("subject", "?")
            predicate = f.get("predicate", "?")
            content = f.get("content", "")
            confidence = f.get("confidence", 0.0)
            line = f"- [{subject}] [{predicate}]: {content} (confidence: {confidence:.2f})\n"
            if _chars_used() + len(line) > budget_chars:
                break
            lines.append(line)

    # Add rules section
    if rules:
        rules_hdr_candidate = rules_header
        # Check if adding the header + at least one rule fits
        if _chars_used() + len(rules_hdr_candidate) < budget_chars:
            lines.append(rules_hdr_candidate)
            for r in rules:
                content = r.get("content", "")
                maturity = r.get("maturity", "?")
                effectiveness = r.get("effectiveness_score", 0.0)
                line = f"- {content} (maturity: {maturity}, effectiveness: {effectiveness:.2f})\n"
                if _chars_used() + len(line) > budget_chars:
                    break
                lines.append(line)

    return "".join(lines)
