"""Approvals module — human-in-the-loop approval mechanism for tool invocations."""

from butlers.modules.approvals.module import (
    ApprovalsConfig,
    ApprovalsModule,
    InvalidTransitionError,
    validate_transition,
)

__all__ = [
    "ApprovalsConfig",
    "ApprovalsModule",
    "InvalidTransitionError",
    "validate_transition",
]
