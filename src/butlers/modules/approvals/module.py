"""Approvals module — MCP tools for managing the pending action approval queue.

Provides six tools:
- list_pending_actions: list actions with optional status filter
- show_pending_action: show full details for a single action
- approve_action: approve and execute a pending action
- reject_action: reject with optional reason
- pending_action_count: count of pending actions
- expire_stale_actions: mark expired actions past their expires_at
"""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel

from butlers.modules.approvals.models import ActionStatus, ApprovalRule, PendingAction
from butlers.modules.base import Module

logger = logging.getLogger(__name__)

# Valid status transitions: source -> set of valid targets
_VALID_TRANSITIONS: dict[ActionStatus, set[ActionStatus]] = {
    ActionStatus.PENDING: {ActionStatus.APPROVED, ActionStatus.REJECTED, ActionStatus.EXPIRED},
    ActionStatus.APPROVED: {ActionStatus.EXECUTED},
    ActionStatus.REJECTED: set(),
    ActionStatus.EXPIRED: set(),
    ActionStatus.EXECUTED: set(),
}


class InvalidTransitionError(Exception):
    """Raised when an invalid status transition is attempted."""


def validate_transition(current: ActionStatus, target: ActionStatus) -> None:
    """Validate that a status transition is allowed.

    Raises InvalidTransitionError if the transition is not in the valid set.
    """
    valid = _VALID_TRANSITIONS.get(current, set())
    if target not in valid:
        raise InvalidTransitionError(
            f"Cannot transition from '{current.value}' to '{target.value}'"
        )


class ApprovalsConfig(BaseModel):
    """Configuration for the Approvals module."""

    default_limit: int = 50


# Type alias for tool executor callbacks
ToolExecutor = Callable[[str, dict[str, Any]], Coroutine[Any, Any, dict[str, Any]]]


class ApprovalsModule(Module):
    """Approvals module providing human-in-the-loop tool approval MCP tools.

    All tools operate on the butler's own DB via the ``db`` connection pool
    passed during ``register_tools()``.
    """

    def __init__(self) -> None:
        self._config: ApprovalsConfig = ApprovalsConfig()
        self._db: Any = None
        self._tool_executor: ToolExecutor | None = None

    @property
    def name(self) -> str:
        return "approvals"

    @property
    def config_schema(self) -> type[BaseModel]:
        return ApprovalsConfig

    @property
    def dependencies(self) -> list[str]:
        return []

    def migration_revisions(self) -> str | None:
        return "approvals"

    def set_tool_executor(self, executor: ToolExecutor) -> None:
        """Set the callback used by approve_action to execute the original tool.

        The executor receives (tool_name, tool_args) and returns a result dict.
        This is designed to be wired up by the MCP dispatch interception layer
        (task clc.4). Until then, approve_action will store the approval but
        skip execution if no executor is set.
        """
        self._tool_executor = executor

    async def register_tools(self, mcp: Any, config: Any, db: Any) -> None:
        """Register all 6 approval queue MCP tools."""
        self._config = ApprovalsConfig(**(config or {}))
        self._db = db
        module = self  # capture for closures

        @mcp.tool()
        async def list_pending_actions(
            status: str | None = None, limit: int | None = None
        ) -> list[dict]:
            """List pending actions with optional status filter and limit."""
            return await module._list_pending_actions(status=status, limit=limit)

        @mcp.tool()
        async def show_pending_action(action_id: str) -> dict:
            """Show full details for a single pending action."""
            return await module._show_pending_action(action_id)

        @mcp.tool()
        async def approve_action(action_id: str, create_rule: bool = False) -> dict:
            """Approve a pending action and execute it."""
            return await module._approve_action(action_id, create_rule=create_rule)

        @mcp.tool()
        async def reject_action(action_id: str, reason: str | None = None) -> dict:
            """Reject a pending action with optional reason."""
            return await module._reject_action(action_id, reason=reason)

        @mcp.tool()
        async def pending_action_count() -> dict:
            """Return count of pending actions."""
            return await module._pending_action_count()

        @mcp.tool()
        async def expire_stale_actions() -> dict:
            """Mark expired actions that are past their expires_at."""
            return await module._expire_stale_actions()

    async def on_startup(self, config: Any, db: Any) -> None:
        """Initialize config and store db reference."""
        self._config = ApprovalsConfig(**(config or {}))
        self._db = db

    async def on_shutdown(self) -> None:
        """No persistent resources to clean up."""
        pass

    # ------------------------------------------------------------------
    # Tool implementations
    # ------------------------------------------------------------------

    async def _list_pending_actions(
        self, status: str | None = None, limit: int | None = None
    ) -> list[dict]:
        """List pending actions with optional filters."""
        effective_limit = limit if limit is not None else self._config.default_limit

        if status is not None:
            # Validate the status value
            try:
                ActionStatus(status)
            except ValueError:
                return [{"error": f"Invalid status: {status}"}]

            query = (
                "SELECT * FROM pending_actions WHERE status = $1 "
                "ORDER BY requested_at DESC LIMIT $2"
            )
            rows = await self._db.fetch(query, status, effective_limit)
        else:
            query = "SELECT * FROM pending_actions ORDER BY requested_at DESC LIMIT $1"
            rows = await self._db.fetch(query, effective_limit)

        return [PendingAction.from_row(row).to_dict() for row in rows]

    async def _show_pending_action(self, action_id: str) -> dict:
        """Show full details for a single pending action."""
        try:
            parsed_id = uuid.UUID(action_id)
        except ValueError:
            return {"error": f"Invalid action_id: {action_id}"}

        row = await self._db.fetchrow("SELECT * FROM pending_actions WHERE id = $1", parsed_id)
        if row is None:
            return {"error": f"Action not found: {action_id}"}

        return PendingAction.from_row(row).to_dict()

    async def _approve_action(self, action_id: str, create_rule: bool = False) -> dict:
        """Approve a pending action, execute it, and optionally create a rule."""
        try:
            parsed_id = uuid.UUID(action_id)
        except ValueError:
            return {"error": f"Invalid action_id: {action_id}"}

        row = await self._db.fetchrow("SELECT * FROM pending_actions WHERE id = $1", parsed_id)
        if row is None:
            return {"error": f"Action not found: {action_id}"}

        action = PendingAction.from_row(row)

        # Validate transition: pending -> approved
        try:
            validate_transition(action.status, ActionStatus.APPROVED)
        except InvalidTransitionError as exc:
            return {"error": str(exc)}

        now = datetime.now(UTC)

        # Transition to approved
        await self._db.execute(
            "UPDATE pending_actions SET status = $1, decided_by = $2, decided_at = $3 "
            "WHERE id = $4",
            ActionStatus.APPROVED.value,
            "user:manual",
            now,
            parsed_id,
        )

        # Execute the original tool if an executor is available
        execution_result: dict[str, Any] | None = None
        if self._tool_executor is not None:
            try:
                execution_result = await self._tool_executor(action.tool_name, action.tool_args)
            except Exception as exc:
                logger.error("Tool execution failed for action %s: %s", action_id, exc)
                execution_result = {"error": str(exc)}

        # Transition to executed
        try:
            validate_transition(ActionStatus.APPROVED, ActionStatus.EXECUTED)
        except InvalidTransitionError:
            # This should never happen since approved -> executed is valid
            pass

        await self._db.execute(
            "UPDATE pending_actions SET status = $1, execution_result = $2 WHERE id = $3",
            ActionStatus.EXECUTED.value,
            json.dumps(execution_result) if execution_result is not None else None,
            parsed_id,
        )

        # Optionally create an approval rule from this action
        rule_dict: dict[str, Any] | None = None
        if create_rule:
            rule_id = uuid.uuid4()
            rule = ApprovalRule(
                id=rule_id,
                tool_name=action.tool_name,
                arg_constraints=action.tool_args,
                description=f"Auto-created from approved action {action_id}",
                created_from=parsed_id,
                created_at=now,
            )
            await self._db.execute(
                "INSERT INTO approval_rules "
                "(id, tool_name, arg_constraints, description, created_from, created_at, "
                "active) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7)",
                rule.id,
                rule.tool_name,
                json.dumps(rule.arg_constraints),
                rule.description,
                rule.created_from,
                rule.created_at,
                rule.active,
            )
            rule_dict = rule.to_dict()

        # Re-read the final state
        final_row = await self._db.fetchrow(
            "SELECT * FROM pending_actions WHERE id = $1", parsed_id
        )
        result = PendingAction.from_row(final_row).to_dict()
        if rule_dict is not None:
            result["created_rule"] = rule_dict

        return result

    async def _reject_action(self, action_id: str, reason: str | None = None) -> dict:
        """Reject a pending action with optional reason."""
        try:
            parsed_id = uuid.UUID(action_id)
        except ValueError:
            return {"error": f"Invalid action_id: {action_id}"}

        row = await self._db.fetchrow("SELECT * FROM pending_actions WHERE id = $1", parsed_id)
        if row is None:
            return {"error": f"Action not found: {action_id}"}

        action = PendingAction.from_row(row)

        # Validate transition: pending -> rejected
        try:
            validate_transition(action.status, ActionStatus.REJECTED)
        except InvalidTransitionError as exc:
            return {"error": str(exc)}

        now = datetime.now(UTC)

        # Build decided_by with optional reason
        decided_by = "user:manual"
        if reason:
            decided_by = f"user:manual (reason: {reason})"

        await self._db.execute(
            "UPDATE pending_actions SET status = $1, decided_by = $2, decided_at = $3 "
            "WHERE id = $4",
            ActionStatus.REJECTED.value,
            decided_by,
            now,
            parsed_id,
        )

        final_row = await self._db.fetchrow(
            "SELECT * FROM pending_actions WHERE id = $1", parsed_id
        )
        return PendingAction.from_row(final_row).to_dict()

    async def _pending_action_count(self) -> dict:
        """Return counts of pending actions by status."""
        rows = await self._db.fetch(
            "SELECT status, COUNT(*) as count FROM pending_actions GROUP BY status"
        )
        counts = {row["status"]: row["count"] for row in rows}
        total = sum(counts.values())
        return {
            "total": total,
            "by_status": counts,
        }

    async def _expire_stale_actions(self) -> dict:
        """Mark actions past their expires_at as expired."""
        now = datetime.now(UTC)

        # Find all pending actions that have expired
        rows = await self._db.fetch(
            "SELECT * FROM pending_actions WHERE status = $1 AND expires_at IS NOT NULL "
            "AND expires_at < $2",
            ActionStatus.PENDING.value,
            now,
        )

        expired_ids: list[str] = []
        for row in rows:
            action = PendingAction.from_row(row)
            try:
                validate_transition(action.status, ActionStatus.EXPIRED)
            except InvalidTransitionError:
                continue

            await self._db.execute(
                "UPDATE pending_actions SET status = $1, decided_by = $2, decided_at = $3 "
                "WHERE id = $4",
                ActionStatus.EXPIRED.value,
                "system:expiry",
                now,
                action.id,
            )
            expired_ids.append(str(action.id))

        return {
            "expired_count": len(expired_ids),
            "expired_ids": expired_ids,
        }
