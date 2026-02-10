"""Trace-specific Pydantic models.

Provides ``SpanNode``, ``TraceSummary``, and ``TraceDetail`` for the trace
endpoints that aggregate cross-butler distributed traces.

A trace is identified by a unique ``trace_id`` in the sessions table. Each
trace has one or more sessions (spans) sharing that trace_id. Spans are
linked via ``parent_session_id`` to form a tree structure.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class SpanNode(BaseModel):
    """A single span in a distributed trace, corresponding to one session."""

    id: UUID
    butler: str
    prompt: str
    trigger_source: str
    success: bool | None = None
    started_at: datetime
    completed_at: datetime | None = None
    duration_ms: int | None = None
    model: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    parent_session_id: UUID | None = None
    children: list[SpanNode] = Field(default_factory=list)


class TraceSummary(BaseModel):
    """Lightweight trace representation for list views.

    Aggregates metadata about a trace: how many spans it has, total duration,
    root butler, and overall status.
    """

    trace_id: str
    root_butler: str
    span_count: int
    total_duration_ms: int | None = None
    started_at: datetime
    status: str  # "success", "failed", "running", "partial"


class TraceDetail(TraceSummary):
    """Full trace detail with assembled span tree.

    Extends ``TraceSummary`` with the complete span tree, where root spans
    (those with ``parent_session_id=None``) contain nested children.
    """

    spans: list[SpanNode] = Field(default_factory=list)
