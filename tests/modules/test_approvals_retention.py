"""Real-Postgres regression coverage for approvals retention lifecycle rules."""

from __future__ import annotations

import asyncio
import shutil
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import asyncpg
import pytest

from alembic import command
from butlers.db import register_jsonb_codec
from butlers.migrations import _build_alembic_config
from butlers.modules.approvals.retention import RetentionPolicy, cleanup_old_actions
from butlers.testing.migration import (
    create_migrated_test_db,
    create_migration_db,
    migration_db_name,
)

docker_available = shutil.which("docker") is not None
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not docker_available, reason="Docker not available"),
    pytest.mark.asyncio(loop_scope="session"),
]


@pytest.fixture(scope="module")
def migrated_approvals_db_url(postgres_container) -> str:
    """Provision the real approvals migration chain once for this module."""
    return create_migrated_test_db(
        postgres_container,
        migration_db_name(),
        chains=["approvals"],
    )


@pytest.fixture
async def approvals_pool(migrated_approvals_db_url: str) -> asyncpg.Pool:
    """Return a clean real-migrated approvals pool for each regression test."""
    pool = await asyncpg.create_pool(
        migrated_approvals_db_url,
        min_size=1,
        max_size=3,
        init=register_jsonb_codec,
    )
    await pool.execute(
        "TRUNCATE TABLE approval_events, approval_push_emissions, "
        "autonomy_approval_history, autonomy_suggestions, pending_actions, approval_rules "
        "RESTART IDENTITY CASCADE"
    )
    try:
        yield pool
    finally:
        await pool.close()


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


async def test_terminal_retention_keeps_immutable_execution_event_as_provenance(
    approvals_pool,
) -> None:
    """Terminal action retention must not mutate or delete its longer-lived audit event."""
    executed_id = await _insert_old_action(
        approvals_pool,
        status="executed",
        execution_result={"success": True},
    )
    event_id = await approvals_pool.fetchval(
        """
        INSERT INTO approval_events (
            action_id, event_type, actor, reason, event_metadata, occurred_at
        )
        VALUES ($1, $2, $3, $4, $5, $6)
        RETURNING event_id
        """,
        executed_id,
        "action_execution_succeeded",
        "system:executor",
        "entity merge applied",
        {"result": "merged"},
        datetime.now(UTC) - timedelta(days=365),
    )

    counts = await cleanup_old_actions(
        approvals_pool,
        RetentionPolicy(pending_actions_retention_days=90),
    )

    assert counts == {"executed": 1}
    assert (
        await approvals_pool.fetchval("SELECT id FROM pending_actions WHERE id = $1", executed_id)
        is None
    )
    event = await approvals_pool.fetchrow(
        """
        SELECT action_id, event_type, actor, reason, event_metadata
        FROM approval_events
        WHERE event_id = $1
        """,
        event_id,
    )
    assert event is not None
    assert event["action_id"] == executed_id
    assert event["event_type"] == "action_execution_succeeded"
    assert event["actor"] == "system:executor"
    assert event["reason"] == "entity merge applied"
    assert event["event_metadata"] == {"result": "merged"}


async def test_new_action_event_requires_a_live_action(approvals_pool) -> None:
    """Dropping the deletion-blocking FK must not permit invalid new event references."""
    with pytest.raises(asyncpg.ForeignKeyViolationError, match="live pending action"):
        await approvals_pool.execute(
            """
            INSERT INTO approval_events (action_id, event_type, actor)
            VALUES ($1, $2, $3)
            """,
            uuid4(),
            "action_execution_succeeded",
            "system:executor",
        )


def _create_approvals_007_database(postgres_container) -> str:
    """Create the actual approvals schema immediately before the retention fix."""
    db_url = create_migration_db(postgres_container, migration_db_name())
    command.upgrade(
        _build_alembic_config(db_url, chains=["approvals"]),
        "approvals@approvals_007",
    )
    return db_url


def _upgrade_approvals_to_head(db_url: str) -> None:
    """Apply the retention migration as a production upgrade would."""
    command.upgrade(
        _build_alembic_config(db_url, chains=["approvals"]),
        "approvals@head",
    )


async def test_approvals_upgrade_keeps_existing_execution_event_for_terminal_retention(
    postgres_container,
) -> None:
    """Existing immutable events survive an approvals_007-to-head upgrade and cleanup."""
    db_url = await asyncio.to_thread(_create_approvals_007_database, postgres_container)
    pool = await asyncpg.create_pool(
        db_url,
        min_size=1,
        max_size=3,
        init=register_jsonb_codec,
    )
    try:
        executed_id = await _insert_old_action(
            pool,
            status="executed",
            execution_result={"success": True},
        )
        event_id = await pool.fetchval(
            """
            INSERT INTO approval_events (action_id, event_type, actor, occurred_at)
            VALUES ($1, $2, $3, $4)
            RETURNING event_id
            """,
            executed_id,
            "action_execution_succeeded",
            "system:executor",
            datetime.now(UTC) - timedelta(days=365),
        )
    finally:
        await pool.close()

    await asyncio.to_thread(_upgrade_approvals_to_head, db_url)

    upgraded_pool = await asyncpg.create_pool(
        db_url,
        min_size=1,
        max_size=3,
        init=register_jsonb_codec,
    )
    try:
        counts = await cleanup_old_actions(
            upgraded_pool,
            RetentionPolicy(pending_actions_retention_days=90),
        )

        assert counts == {"executed": 1}
        assert (
            await upgraded_pool.fetchval(
                "SELECT id FROM pending_actions WHERE id = $1", executed_id
            )
            is None
        )
        event = await upgraded_pool.fetchrow(
            """
            SELECT action_id, event_type, actor
            FROM approval_events
            WHERE event_id = $1
            """,
            event_id,
        )
        assert event is not None
        assert dict(event) == {
            "action_id": executed_id,
            "event_type": "action_execution_succeeded",
            "actor": "system:executor",
        }
    finally:
        await upgraded_pool.close()
