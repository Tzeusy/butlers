"""Shared helpers for health butler tools."""

from __future__ import annotations

import json
from typing import Any

import asyncpg


def _row_to_dict(row: asyncpg.Record) -> dict[str, Any]:
    """Convert an asyncpg Record to a dict, parsing JSONB strings."""
    d = dict(row)
    for key in ("value", "nutrition", "tags", "schedule"):
        if key in d and isinstance(d[key], str):
            d[key] = json.loads(d[key])
    return d
