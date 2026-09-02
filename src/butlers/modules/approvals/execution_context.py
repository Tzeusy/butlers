"""Ambient, server-derived context for an approved tool execution."""

from __future__ import annotations

import contextvars
import uuid
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ApprovalExecutionContext:
    """Trusted approval lineage available only while the executor calls a tool."""

    action_id: uuid.UUID
    session_id: uuid.UUID | None
    actor: str


_current_execution: contextvars.ContextVar[ApprovalExecutionContext | None] = (
    contextvars.ContextVar("approval_execution_context", default=None)
)


def get_approval_execution_context() -> ApprovalExecutionContext | None:
    """Return the current approved-action lineage, if execution is approved."""
    return _current_execution.get()


def set_approval_execution_context(
    context: ApprovalExecutionContext,
) -> contextvars.Token[ApprovalExecutionContext | None]:
    """Bind trusted approval lineage around one executor-owned tool call."""
    return _current_execution.set(context)


def reset_approval_execution_context(
    token: contextvars.Token[ApprovalExecutionContext | None],
) -> None:
    """Restore the previous approved-action lineage."""
    _current_execution.reset(token)


__all__ = [
    "ApprovalExecutionContext",
    "get_approval_execution_context",
    "reset_approval_execution_context",
    "set_approval_execution_context",
]
