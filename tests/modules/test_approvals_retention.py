"""Real-Postgres regression coverage for approvals retention lifecycle rules."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from butlers.modules.approvals.retention import RetentionPolicy, cleanup_old_actions

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]


async def _insert_old_action(
    pool,
    *,
    status: str,
    execution_result: dict[str, object] | None = None,
) -> UUID:
    """Insert an action that is safely outside the default retention window."""
    action_id = uuid4()
    decided_at = datetime.now(UTC) - timedelta(days=365)
    await pool.execute(
        """
        INSERT INTO pending_actions (
            id, tool_name, tool_args, status, decided_at, execution_result
        )
        VALUES ($1, $2, $3, $4, $5, $6)
        """,
        action_id,
        "memory_entity_merge",
        {"source_entity_id": "source", "target_entity_id": "target"},
        status,
        decided_at,
        execution_result,
    )
    return action_id


async def test_old_approved_unexecuted_action_is_excluded_from_retention_dry_run(
    approvals_pool,
) -> None:
    """An approved entity merge remains retryable, so dry-run cannot count it."""
    approved_id = await _insert_old_action(approvals_pool, status="approved")
    await _insert_old_action(approvals_pool, status="rejected")
    await _insert_old_action(approvals_pool, status="expired")
    await _insert_old_action(
        approvals_pool,
        status="executed",
        execution_result={"success": True},
    )

    counts = await cleanup_old_actions(
        approvals_pool,
        RetentionPolicy(pending_actions_retention_days=90),
        dry_run=True,
    )

    assert counts == {"executed": 1, "expired": 1, "rejected": 1}
    approved = await approvals_pool.fetchrow(
        "SELECT status, execution_result FROM pending_actions WHERE id = $1",
        approved_id,
    )
    assert approved is not None
    assert approved["status"] == "approved"
    assert approved["execution_result"] is None


async def test_old_approved_unexecuted_action_survives_retention_delete(
    approvals_pool,
) -> None:
    """Deleting terminal actions must retain an approved entity merge and its replay data."""
    approved_id = await _insert_old_action(approvals_pool, status="approved")
    rejected_id = await _insert_old_action(approvals_pool, status="rejected")
    expired_id = await _insert_old_action(approvals_pool, status="expired")
    executed_id = await _insert_old_action(
        approvals_pool,
        status="executed",
        execution_result={"success": True},
    )

    counts = await cleanup_old_actions(
        approvals_pool,
        RetentionPolicy(pending_actions_retention_days=90),
    )

    assert counts == {"executed": 1, "expired": 1, "rejected": 1}
    approved = await approvals_pool.fetchrow(
        "SELECT status, execution_result FROM pending_actions WHERE id = $1",
        approved_id,
    )
    assert approved is not None
    assert approved["status"] == "approved"
    assert approved["execution_result"] is None
    for terminal_id in (rejected_id, expired_id, executed_id):
        assert (
            await approvals_pool.fetchrow(
                "SELECT id FROM pending_actions WHERE id = $1",
                terminal_id,
            )
            is None
        )
