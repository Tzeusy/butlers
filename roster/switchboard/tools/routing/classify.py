"""Message classification — classify and decompose messages across butlers."""

from __future__ import annotations

import json
import logging
from typing import Any

from butlers.tools.switchboard.registry import list_butlers

logger = logging.getLogger(__name__)


async def classify_message(
    pool: Any,
    message: str,
    dispatch_fn: Any,
) -> list[dict[str, str]]:
    """Use CC spawner to classify and decompose a message across butlers.

    Spawns a CC instance that sees the butler registry and determines
    which butler(s) should handle the message.  If the message spans
    multiple domains the CC instance decomposes it into distinct
    sub-messages, each tagged with the target butler.

    Returns a list of dicts with keys ``'butler'`` and ``'prompt'``.
    For single-domain messages the list contains exactly one entry.
    Falls back to ``[{'butler': 'general', 'prompt': message}]`` when
    classification fails.
    """
    fallback = [{"butler": "general", "prompt": message}]

    butlers = await list_butlers(pool)
    butler_list = "\n".join(
        f"- {b['name']}: {b.get('description') or 'No description'}" for b in butlers
    )

    prompt = (
        "Analyze the following message and determine which butler(s) should handle it.\n"
        "If the message spans multiple domains, decompose it into distinct sub-messages,\n"
        "each tagged with the appropriate butler.\n\n"
        f"Available butlers:\n{butler_list}\n\n"
        f"Message: {message}\n\n"
        'Respond with ONLY a JSON array. Each element must have keys "butler" and "prompt".\n'
        "Example for a single-domain message:\n"
        '[{"butler": "health", "prompt": "Log weight at 75kg"}]\n'
        "Example for a multi-domain message:\n"
        '[{"butler": "health", "prompt": "Log weight at 75kg"}, '
        '{"butler": "relationship", "prompt": "Remind me to call Mom on Tuesday"}]\n'
        "Respond with ONLY the JSON array, no other text."
    )

    try:
        result = await dispatch_fn(prompt=prompt, trigger_source="tick")
        if result and hasattr(result, "result") and result.result:
            return _parse_classification(result.result, butlers, message)
    except Exception:
        logger.exception("Classification failed")

    return fallback


def _parse_classification(
    raw: str,
    butlers: list[dict[str, Any]],
    original_message: str,
) -> list[dict[str, str]]:
    """Parse the JSON classification response from CC.

    Validates that each entry references a known butler and has the
    required keys.  Returns the fallback on any parse or validation
    error.
    """
    fallback = [{"butler": "general", "prompt": original_message}]
    known = {b["name"] for b in butlers}

    try:
        parsed = json.loads(raw.strip())
    except (json.JSONDecodeError, ValueError):
        logger.warning("classify_message: failed to parse JSON: %s", raw)
        return fallback

    if not isinstance(parsed, list) or len(parsed) == 0:
        return fallback

    entries: list[dict[str, str]] = []
    for item in parsed:
        if not isinstance(item, dict):
            return fallback
        butler_name = item.get("butler", "").strip().lower()
        sub_prompt = item.get("prompt", "").strip()
        if not butler_name or not sub_prompt:
            return fallback
        if butler_name not in known:
            return fallback
        entries.append({"butler": butler_name, "prompt": sub_prompt})

    return entries if entries else fallback
