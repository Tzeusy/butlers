"""Approvals module — human-in-the-loop approval mechanism for tool invocations."""

from butlers.modules.approvals.gate import apply_approval_gates, match_standing_rule
from butlers.modules.approvals.module import (
    ApprovalsConfig,
    ApprovalsModule,
    InvalidTransitionError,
    validate_transition,
)
from butlers.modules.approvals.rules import match_rules, match_rules_from_list
from butlers.modules.approvals.sensitivity import suggest_constraints

__all__ = [
    "ApprovalsConfig",
    "ApprovalsModule",
    "InvalidTransitionError",
    "apply_approval_gates",
    "match_rules",
    "match_rules_from_list",
    "match_standing_rule",
    "suggest_constraints",
    "validate_transition",
]
