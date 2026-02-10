"""Search-specific Pydantic models.

Provides ``SearchResult`` and ``SearchResponse`` for the cross-butler
fan-out search endpoint that queries sessions and state across all butler
databases.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SearchResult(BaseModel):
    """A single search result from a cross-butler fan-out search.

    Attributes
    ----------
    butler:
        Name of the butler whose database produced this result.
    matched_field:
        Which column/field matched the query (e.g. ``"prompt"``,
        ``"result"``, ``"key"``, ``"value"``).
    snippet:
        Relevant text excerpt containing the matched content.
    data:
        Full record data for constructing links and detail views.
    """

    butler: str
    matched_field: str
    snippet: str
    data: dict[str, Any] = Field(default_factory=dict)


class SearchResponse(BaseModel):
    """Grouped search results from a cross-butler fan-out search.

    Results are grouped by source table: sessions and state entries.
    """

    sessions: list[SearchResult] = Field(default_factory=list)
    state: list[SearchResult] = Field(default_factory=list)
