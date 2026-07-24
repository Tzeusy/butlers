"""Real-Postgres regression: ``dispatch_delegated_ask`` and origin-key dedup.

Complements ``tests/integration/test_delegation_ledger_roundtrip.py`` (which
covers ``record_ask``/``mark_dispatch_outcome``/``record_answer`` directly)
by exercising ``butlers.core_tools._delegation.dispatch_delegated_ask`` --
the record-then-dispatch-then-mark-outcome sequence factored out of the
``delegate_ask`` MCP tool closure so ``butlers.jobs.briefing``'s deterministic
Relationship-to-Finance birthday-gift seed (bu-27dxl.5.4) can reuse the same
Switchboard route path with an already-known target.

Runs against a fully migrated Postgres instance (not just mocked-pool unit
tests -- see ``tests/core_tools/test_delegation.py`` and
``tests/jobs/test_briefing.py`` for those) because the seed's dedup guard
depends on a raw ``metadata->>'origin_key'`` JSONB text-extraction query
that a mocked pool cannot validate.
"""

from __future__ import annotations

import shutil
from types import SimpleNamespace
from typing import Any

import asyncpg
import pytest

from butlers.core_tools._delegation import dispatch_delegated_ask
from butlers.testing.migration import create_migrated_test_db, migration_db_name

docker_available = shutil.which("docker") is not None
pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio(loop_scope="session"),
    pytest.mark.skipif(not docker_available, reason="Docker not available"),
]


@pytest.fixture(scope="module")
def migrated_db_url(postgres_container) -> str:
    return create_migrated_test_db(postgres_container, migration_db_name(), chains=["core"])


@pytest.fixture
async def pool(migrated_db_url: str) -> asyncpg.Pool:
    p = await asyncpg.create_pool(migrated_db_url, min_size=1, max_size=3)
    yield p
    await p.close()


def _origin_key_lookup(pool: asyncpg.Pool, asking_butler: str, origin_key: str) -> Any:
    """The exact dedup query used by butlers.jobs.briefing._relationship_finance_birthday_gift_ask."""
    return pool.fetchval(
        """
        SELECT id FROM public.delegation_ledger
        WHERE asking_butler = $1
          AND metadata->>'origin_key' = $2
        LIMIT 1
        """,
        asking_butler,
        origin_key,
    )


class _OkClient:
    """Stub switchboard_client whose call_tool() reports a successful route()."""

    async def call_tool(self, tool_name: str, args: dict[str, Any]) -> Any:
        assert tool_name == "route"
        assert args["tool_name"] == "delegate_receive"
        return SimpleNamespace(is_error=False, data={"status": "scheduled"})


async def test_successful_dispatch_records_routed_row_with_origin_key(pool: asyncpg.Pool) -> None:
    origin_key = "relationship-birthday-gift-ask:v1:2026-08-01"

    result = await dispatch_delegated_ask(
        pool,
        _OkClient(),
        asking_butler="relationship",
        target_butler="finance",
        question="What is the household's typical gift budget for a birthday in 3 days?",
        metadata={"origin_key": origin_key, "seed": "birthday_gift_budget_ask"},
    )

    assert result["status"] == "routed"
    ledger_id = result["ledger_id"]

    row = await pool.fetchrow(
        "SELECT status, asking_butler, target_butler, metadata "
        "FROM public.delegation_ledger WHERE id = $1",
        ledger_id,
    )
    assert row is not None
    assert row["status"] == "routed"
    assert row["asking_butler"] == "relationship"
    assert row["target_butler"] == "finance"

    # The exact dedup lookup the briefing seed performs finds this row.
    found_id = await _origin_key_lookup(pool, "relationship", origin_key)
    assert str(found_id) == ledger_id


async def test_dedup_lookup_ignores_a_different_origin_key(pool: asyncpg.Pool) -> None:
    origin_key = "relationship-birthday-gift-ask:v1:2026-08-02"
    await dispatch_delegated_ask(
        pool,
        _OkClient(),
        asking_butler="relationship",
        target_butler="finance",
        question="Birthday gift budget context, day 2.",
        metadata={"origin_key": origin_key},
    )

    miss = await _origin_key_lookup(
        pool, "relationship", "relationship-birthday-gift-ask:v1:2026-08-03"
    )
    assert miss is None


async def test_route_failure_records_failed_row_not_routed(pool: asyncpg.Pool) -> None:
    origin_key = "relationship-birthday-gift-ask:v1:2026-08-04"

    # client=None and asking_butler != "switchboard" -> the standing
    # "Switchboard is not connected" retryable failure path.
    result = await dispatch_delegated_ask(
        pool,
        None,
        asking_butler="relationship",
        target_butler="finance",
        question="Birthday gift budget context, day 4.",
        metadata={"origin_key": origin_key},
    )

    assert result["status"] == "failed"
    assert result["retryable"] is True

    row = await pool.fetchrow(
        "SELECT status FROM public.delegation_ledger WHERE id = $1", result["ledger_id"]
    )
    assert row["status"] == "failed"

    # A failed dispatch must never satisfy the dedup lookup as if it had
    # succeeded -- the row exists (so a raw existence check would be wrong),
    # but the seed's job-level "already_asked" short circuit still applies
    # per-origin-key regardless of terminal outcome (AC2: no duplicate ASK
    # attempts on a duplicate run, not "retry until success").
    found_id = await _origin_key_lookup(pool, "relationship", origin_key)
    assert str(found_id) == result["ledger_id"]
