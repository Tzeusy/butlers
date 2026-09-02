"""Executable planning contract for Finance recurrence producer authority.

Spec: REQ-finance-supporting-tables-001, REQ-butler-finance-001, and
REQ-finance-alerts-001.

The specification lane executes the landed RFC 0029 evaluator against its machine-readable source
matrix. Runtime Finance wiring remains in the active change tasks.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest

from butlers.core.expected_signals import ExpectedSignalState, evaluate_expected_signal

pytestmark = pytest.mark.contract

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DESIGN = _REPO_ROOT / "openspec/changes/finance-recurrence-producer-mapping/design.md"
_START = "<!-- finance-recurrence-producer-map:start -->"
_END = "<!-- finance-recurrence-producer-map:end -->"
_NOW = datetime(2026, 9, 3, 12, tzinfo=UTC)


def _source_rows() -> list[dict[str, Any]]:
    text = _DESIGN.read_text(encoding="utf-8")
    block = text.split(_START, 1)[1].split(_END, 1)[0]
    match = re.search(r"```json\s*(\[.*\])\s*```", block, flags=re.DOTALL)
    assert match is not None, "design must carry the executable producer-map JSON block"
    rows = json.loads(match.group(1))
    assert isinstance(rows, list)
    return rows


def _absence_candidate(state: ExpectedSignalState) -> str | None:
    """No approved Finance policy currently consumes recurrence absence."""
    assert state in {
        ExpectedSignalState.PRESENT,
        ExpectedSignalState.ABSENT,
        ExpectedSignalState.UNMEASURABLE,
    }
    return None


def _resolve_contract_producer(rows: list[dict[str, Any]]) -> str:
    """Resolve exactly one mapped producer; every other source set fails closed."""
    if any(row["mapping"] != "mapped" for row in rows):
        return "unknown"
    producers = {row["producer"] for row in rows}
    if len(producers) != 1:
        return "unknown"
    producer = next(iter(producers))
    return producer if isinstance(producer, str) else "unknown"


@pytest.mark.parametrize(
    ("liveness_rows", "expected_reason"),
    [
        (
            [{"state": "healthy", "last_heartbeat_at": _NOW - timedelta(minutes=6)}],
            "producer_stale_or_offline",
        ),
        ([{"state": "offline", "last_heartbeat_at": _NOW}], "producer_stale_or_offline"),
        ([{"state": "error", "last_heartbeat_at": _NOW}], "producer_not_healthy"),
        ([{"state": "degraded", "last_heartbeat_at": _NOW}], "producer_not_healthy"),
        ([{"state": "paused", "last_heartbeat_at": _NOW}], "producer_not_healthy"),
        ([], "producer_unregistered"),
    ],
)
async def test_killed_gmail_past_expected_date_is_unmeasurable_without_candidate(
    liveness_rows: list[dict[str, Any]],
    expected_reason: str,
) -> None:
    """The mapped connector fails closed after its recurrence date elapses."""
    pool = AsyncMock()
    pool.fetch.return_value = liveness_rows

    result = await evaluate_expected_signal(
        pool,
        signal_key="finance:recurrence:group-1",
        producer="connector:gmail",
        expected_cadence=timedelta(days=30),
        last_observed_at=_NOW - timedelta(days=31),
        now=_NOW,
    )

    assert result.state is ExpectedSignalState.UNMEASURABLE
    assert result.unmeasurable_reason == expected_reason
    assert _absence_candidate(result.state) is None


async def test_unreadable_gmail_liveness_is_unmeasurable_without_candidate() -> None:
    """An unavailable liveness projection cannot become a missed-renewal claim."""
    pool = AsyncMock()
    pool.fetch.side_effect = RuntimeError("liveness unavailable")

    result = await evaluate_expected_signal(
        pool,
        signal_key="finance:subscription-renewal:sub-1",
        producer="connector:gmail",
        expected_cadence=timedelta(days=365),
        last_observed_at=_NOW - timedelta(days=366),
        now=_NOW,
    )

    assert result.state is ExpectedSignalState.UNMEASURABLE
    assert result.unmeasurable_reason == "liveness_unavailable"
    assert _absence_candidate(result.state) is None


async def test_healthy_elapsed_gmail_is_absent_without_inventing_alert_policy() -> None:
    """Healthy absence is state evidence only until an alert consumer is approved."""
    pool = AsyncMock()
    pool.fetch.return_value = [
        {"state": "healthy", "last_heartbeat_at": _NOW - timedelta(seconds=30)}
    ]

    result = await evaluate_expected_signal(
        pool,
        signal_key="finance:recurrence:group-1",
        producer="connector:gmail",
        expected_cadence=timedelta(days=30),
        last_observed_at=_NOW - timedelta(days=30),
        now=_NOW,
    )

    assert result.state is ExpectedSignalState.ABSENT
    assert _absence_candidate(result.state) is None


async def test_attested_owner_elapsed_is_absent_but_has_no_payment_wording() -> None:
    """Owner measurability stays bounded to the absence of an owner-recorded row."""
    pool = AsyncMock()

    result = await evaluate_expected_signal(
        pool,
        signal_key="finance:subscription-renewal:sub-1",
        producer="owner",
        expected_cadence=timedelta(days=365),
        last_observed_at=_NOW - timedelta(days=365),
        now=_NOW,
    )

    assert result.state is ExpectedSignalState.ABSENT
    assert _absence_candidate(result.state) is None
    pool.fetch.assert_not_awaited()


@pytest.mark.parametrize(
    "source_ids",
    [
        ["gmail_transaction_attested", "owner_transaction_attested"],
        ["simplefin_aggregator"],
        ["current_email_message_id"],
        ["mixed_recurring_group"],
        ["declared_renewal_date_only"],
    ],
)
async def test_mixed_or_unprovable_elapsed_source_is_unmeasurable_without_candidate(
    source_ids: list[str],
) -> None:
    """Source resolution feeds unknown to RFC 0029 instead of selecting a healthy peer."""
    all_rows = _source_rows()
    selected = [row for row in all_rows if row["source_id"] in source_ids]
    assert len(selected) == len(source_ids)
    pool = AsyncMock()

    result = await evaluate_expected_signal(
        pool,
        signal_key="finance:recurrence:group-1",
        producer=_resolve_contract_producer(selected),
        expected_cadence=timedelta(days=30),
        last_observed_at=_NOW - timedelta(days=31),
        now=_NOW,
    )

    assert result.state is ExpectedSignalState.UNMEASURABLE
    assert result.unmeasurable_reason == "producer_unknown"
    assert _absence_candidate(result.state) is None
    pool.fetch.assert_not_awaited()


def test_every_current_untrusted_or_unsupported_source_is_unmeasurable() -> None:
    """Current rows, SimpleFIN, mixed groups, and generic sources never guess a producer."""
    rows = _source_rows()
    unmeasurable = {row["source_id"] for row in rows if row["mapping"] == "unmeasurable"}

    assert unmeasurable == {
        "current_email_message_id",
        "current_manual_or_bulk",
        "simplefin_aggregator",
        "api_or_bank_sync",
        "legacy_backfill_or_split",
        "current_recurring_group",
        "mixed_recurring_group",
    }
    assert all(row["producer"] is None for row in rows if row["mapping"] != "mapped")


def test_mapping_has_only_supported_rfc_0029_producers() -> None:
    """The contract does not invent a SimpleFIN schedule producer or generic Finance connector."""
    mapped = {row["producer"] for row in _source_rows() if row["mapping"] == "mapped"}
    assert mapped == {"connector:gmail", "owner"}


def test_tracked_renewal_and_inferred_recurrence_policies_remain_bounded() -> None:
    """The packet preserves forward-looking policies and names no missed-renewal consumer."""
    design = " ".join(_DESIGN.read_text(encoding="utf-8").split())
    assert "active yearly tracked subscription within 14 days" in design
    assert "untracked regular payment predicted inside the next 30 days" in design
    assert "produces no new candidate or dashboard verdict" in design
    assert '"missed renewal"' in design
