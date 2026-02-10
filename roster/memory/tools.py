"""Memory Butler MCP tools.

Thin tool wrappers that delegate to storage.py and search.py for the
actual logic.  Each function accepts an asyncpg Pool (and optionally an
EmbeddingEngine) and returns a result suitable for MCP tool responses.
"""

from __future__ import annotations

import importlib.util
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
