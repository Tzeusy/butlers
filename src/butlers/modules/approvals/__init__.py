"""Approvals module — human-in-the-loop approval mechanism for tool invocations."""

from butlers.modules.approvals.gate import apply_approval_gates, match_standing_rule
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
    "apply_approval_gates",
    "match_standing_rule",
    "validate_transition",
]
