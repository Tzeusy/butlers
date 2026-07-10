"""Real-Postgres integration tests for the gap-interview answer path (bu-whhll.12).

The answer application is DB-heavy: it is the *first real tenant* of the
``chronicler.overrides`` table (0 rows had ever been written before this
feature) and it mutates ``chronicler.routines.confidence`` under the
``[0, 1]`` CHECK constraint added by ``chronicler_018``. Mocked-pool tests
cannot prove the JSONB-codec round-trip, the CHECK-constraint clamp, or that
the override row actually lands in the corrected view (see "Mocked-pool vs
integration test gap": PR #2598 class, ~8h main-red from SQL that passed
mocked-pool tests only). These run the real migration chain against a
migrated Postgres container.
"""

from __future__ import annotations

import shutil
from datetime import UTC, datetime, time
from zoneinfo import ZoneInfo

import asyncpg
import pytest

from butlers.chronicler.adapters.occupation import (
    EPISODE_TYPE_OCCUPATION,
)
from butlers.chronicler.adapters.occupation import (
    SOURCE_NAME as OCCUPATION_SOURCE_NAME,
)
from butlers.chronicler.contracts import INITIAL_SOURCES, seed_source_registry
from butlers.chronicler.gap_interview import (
    GapInterviewAnswer,
    apply_gap_interview_answer,
)
from butlers.chronicler.models import Confidence, Episode, Layer, OverrideTarget, Precision
from butlers.chronicler.storage import (
    adjust_routine_confidence,
    get_episode,
    get_routine,
    list_overrides_for,
    upsert_episode,
    upsert_mined_routine,
)
from butlers.db import register_jsonb_codec
from butlers.testing.migration import create_migrated_test_db, migration_db_name

docker_available = shutil.which("docker") is not None
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not docker_available, reason="Docker not available"),
    pytest.mark.asyncio(loop_scope="session"),
]

_TZ = ZoneInfo("Asia/Singapore")
_LOCAL_DATE = "2026-07-02"


@pytest.fixture(scope="module")
def migrated_db_url(postgres_container) -> str:
    return create_migrated_test_db(
        postgres_container,
        migration_db_name(),
        chains=["chronicler"],
    )


@pytest.fixture
async def pool(migrated_db_url: str):
    p = await asyncpg.create_pool(
        migrated_db_url, min_size=1, max_size=5, init=register_jsonb_codec
    )
    await p.execute("TRUNCATE TABLE routines CASCADE")
    await p.execute("TRUNCATE TABLE episodes, point_events, overrides CASCADE")
    await seed_source_registry(p, sources=INITIAL_SOURCES)
    yield p
    await p.close()


async def _make_occupation_episode(pool, *, routine_id) -> Episode:
    return await upsert_episode(
        pool,
        Episode(
            source_name=OCCUPATION_SOURCE_NAME,
            source_ref=f"chronicler.routines:{routine_id}:{_LOCAL_DATE}",
            episode_type=EPISODE_TYPE_OCCUPATION,
            start_at=datetime(2026, 7, 2, 9, tzinfo=_TZ).astimezone(UTC),
            end_at=datetime(2026, 7, 2, 18, tzinfo=_TZ).astimezone(UTC),
            precision=Precision.HOUR,
            title="Occupation (Weekdays)",
            payload={"routine_id": str(routine_id), "local_date": _LOCAL_DATE},
            layer=Layer.ACTIVITY,
            confidence=Confidence.LOW,
        ),
    )


async def _make_routine(pool, *, confidence: float = 0.5, support: int = 10):
    return await upsert_mined_routine(
        pool,
        dow_mask=0b0011111,  # Mon-Fri
        window_start_local=time(9, 30),
        window_end_local=time(19, 30),
        label="Weekdays",
        support_count=support,
        confidence=confidence,
        evidence_summary={"slots": [1, 2, 3]},  # JSONB dict, never json.dumps
    )


# ── confirm ─────────────────────────────────────────────────────────────────


async def test_confirm_writes_override_note_and_reinforces_routine(pool) -> None:
    routine = await _make_routine(pool, confidence=0.5, support=10)
    episode = await _make_occupation_episode(pool, routine_id=routine.id)

    result = await apply_gap_interview_answer(
        pool,
        answer=GapInterviewAnswer.CONFIRM,
        local_date=_LOCAL_DATE,
        occupation_episode_id=episode.id,
        routine_id=routine.id,
    )
    assert result["status"] == "applied"
    assert result["override_id"] is not None
    assert result["routine_updated"] is True

    # First real override row lands, targets the occupation episode, carries a note.
    overrides = await list_overrides_for(
        pool, target_kind=OverrideTarget.EPISODE, target_id=episode.id
    )
    assert len(overrides) == 1
    assert overrides[0].note is not None
    assert "confirmed" in overrides[0].note
    assert overrides[0].submitted_by == "owner:gap_interview"
    # Confirm keeps the block (no tombstone).
    assert overrides[0].corrected_tombstone_at is None

    # Routine reinforced: confidence up, support incremented.
    refreshed = await get_routine(pool, routine.id)
    assert refreshed.confidence == pytest.approx(0.60)
    assert refreshed.support_count == 11

    # The episode is still live (not tombstoned) in the corrected view.
    ep = await get_episode(pool, episode.id)
    assert ep is not None


# ── correct ─────────────────────────────────────────────────────────────────


async def test_correct_tombstones_block_and_decays_routine(pool) -> None:
    routine = await _make_routine(pool, confidence=0.5, support=10)
    episode = await _make_occupation_episode(pool, routine_id=routine.id)
    now = datetime(2026, 7, 3, 1, 0, tzinfo=UTC)

    result = await apply_gap_interview_answer(
        pool,
        answer=GapInterviewAnswer.CORRECT,
        local_date=_LOCAL_DATE,
        occupation_episode_id=episode.id,
        routine_id=routine.id,
        now=now,
    )
    assert result["routine_updated"] is True

    overrides = await list_overrides_for(
        pool, target_kind=OverrideTarget.EPISODE, target_id=episode.id
    )
    assert len(overrides) == 1
    # Correcting a wrong inference tombstones the block via the override.
    assert overrides[0].corrected_tombstone_at == now

    refreshed = await get_routine(pool, routine.id)
    assert refreshed.confidence == pytest.approx(0.35)
    assert refreshed.support_count == 10  # decay does not touch support

    # Tombstoned block drops out of the corrected view.
    ep = await get_episode(pool, episode.id)
    assert ep is None


# ── dismiss ─────────────────────────────────────────────────────────────────


async def test_dismiss_writes_note_only_leaves_routine(pool) -> None:
    routine = await _make_routine(pool, confidence=0.5, support=10)
    episode = await _make_occupation_episode(pool, routine_id=routine.id)

    result = await apply_gap_interview_answer(
        pool,
        answer=GapInterviewAnswer.DISMISS,
        local_date=_LOCAL_DATE,
        occupation_episode_id=episode.id,
        routine_id=routine.id,
    )
    assert result["routine_updated"] is False

    overrides = await list_overrides_for(
        pool, target_kind=OverrideTarget.EPISODE, target_id=episode.id
    )
    assert len(overrides) == 1
    assert overrides[0].corrected_tombstone_at is None

    refreshed = await get_routine(pool, routine.id)
    assert refreshed.confidence == pytest.approx(0.50)  # unchanged
    assert refreshed.support_count == 10


# ── unaccounted-only (no occupation block to target) ────────────────────────


async def test_confirm_without_occupation_reinforces_routine_no_override(pool) -> None:
    routine = await _make_routine(pool, confidence=0.5, support=10)
    result = await apply_gap_interview_answer(
        pool,
        answer=GapInterviewAnswer.CONFIRM,
        local_date=_LOCAL_DATE,
        occupation_episode_id=None,
        routine_id=routine.id,
    )
    assert result["override_id"] is None
    assert result["routine_updated"] is True
    refreshed = await get_routine(pool, routine.id)
    assert refreshed.confidence == pytest.approx(0.60)


# ── confidence clamp under the [0,1] CHECK constraint ───────────────────────


async def test_reinforce_confidence_clamped_at_one(pool) -> None:
    routine = await _make_routine(pool, confidence=0.95, support=10)
    updated = await adjust_routine_confidence(
        pool, routine.id, confidence_delta=0.10, support_delta=1
    )
    assert updated is not None
    assert updated.confidence == pytest.approx(1.0)  # clamped, no CHECK violation


async def test_decay_confidence_clamped_at_zero(pool) -> None:
    routine = await _make_routine(pool, confidence=0.05, support=10)
    updated = await adjust_routine_confidence(pool, routine.id, confidence_delta=-0.5)
    assert updated is not None
    assert updated.confidence == pytest.approx(0.0)  # clamped, no CHECK violation


async def test_adjust_missing_routine_returns_none(pool) -> None:
    from uuid import uuid4

    updated = await adjust_routine_confidence(pool, uuid4(), confidence_delta=0.1)
    assert updated is None


# ── MCP tool round-trip (state dedupe + resolve), needs the core `state` table ──


@pytest.fixture(scope="module")
def migrated_db_url_full(postgres_container) -> str:
    """core + chronicler chains, so the KV ``state`` table exists for dedupe."""
    return create_migrated_test_db(
        postgres_container,
        migration_db_name() + "_full",
        chains=["core", "chronicler"],
    )


@pytest.fixture
async def full_pool(migrated_db_url_full: str):
    p = await asyncpg.create_pool(
        migrated_db_url_full, min_size=1, max_size=5, init=register_jsonb_codec
    )
    await p.execute("TRUNCATE TABLE routines CASCADE")
    await p.execute("TRUNCATE TABLE episodes, point_events, overrides CASCADE")
    await p.execute("TRUNCATE TABLE state")
    await seed_source_registry(p, sources=INITIAL_SOURCES)
    yield p
    await p.close()


def _chronicler_tools(pool):
    """Register the chronicler module tools against a capturing MCP, return them."""
    import importlib
    from unittest.mock import MagicMock

    from butlers.modules.registry import default_registry

    default_registry()  # ensures roster modules are imported as synthetic modules
    mod = importlib.import_module("butlers.modules._roster_chronicler")

    registered: dict = {}
    mcp = MagicMock()
    mcp.tool.side_effect = lambda: lambda fn: registered.__setitem__(fn.__name__, fn) or fn

    class _DB:
        def __init__(self, p):
            self.pool = p

    module = mod.ChroniclerModule()
    return module, registered, mcp, _DB(pool)


async def _register(pool):
    module, registered, mcp, db = _chronicler_tools(pool)
    await module.register_tools(mcp=mcp, config=None, db=db, butler_name="chronicler")
    return registered


async def test_gap_interview_tool_dedupe_and_resolve_roundtrip(full_pool) -> None:
    routine = await _make_routine(full_pool, confidence=0.5, support=10)
    await _make_occupation_episode(full_pool, routine_id=routine.id)
    tools = await _register(full_pool)
    gap = tools["chronicler_gap_interview"]
    resolve = tools["chronicler_resolve_gap_interview"]

    # First call asks (low-confidence occupation block present).
    first = await gap(date_label=_LOCAL_DATE, timezone="Asia/Singapore")
    assert first["action"] == "send"
    assert "work day" in first["message"]
    assert first["options"] == ["confirm", "correct", "dismiss"]
    interview_id = first["interview_id"]

    # Second call the same day is deduped — never a second prompt.
    second = await gap(date_label=_LOCAL_DATE, timezone="Asia/Singapore")
    assert second == {"action": "skip", "reason": "already_asked"}

    # Resolve applies the answer: override row written, routine reinforced.
    applied = await resolve(interview_id=interview_id, answer="confirm")
    assert applied["status"] == "applied"
    assert applied["override_id"] is not None
    refreshed = await get_routine(full_pool, routine.id)
    assert refreshed.confidence == pytest.approx(0.60)

    # A second resolve is idempotent — the interview is already answered.
    again = await resolve(interview_id=interview_id, answer="confirm")
    assert again["status"] == "already_answered"


async def test_gap_interview_tool_skips_when_no_gap(full_pool) -> None:
    # A day with a fully-tracked waking window and no occupation block: no prompt.

    from butlers.chronicler.models import Precision

    await upsert_episode(
        full_pool,
        Episode(
            source_name="spotify.session_summary",
            source_ref="spotify:full-day",
            episode_type="listening_episode",
            start_at=datetime(2026, 7, 2, 6, tzinfo=_TZ).astimezone(UTC),
            end_at=datetime(2026, 7, 2, 22, tzinfo=_TZ).astimezone(UTC),
            precision=Precision.EXACT,
            layer=Layer.ACTIVITY,
            confidence=Confidence.MEDIUM,
        ),
    )
    tools = await _register(full_pool)
    gap = tools["chronicler_gap_interview"]
    result = await gap(date_label=_LOCAL_DATE, timezone="Asia/Singapore")
    assert result == {"action": "skip", "reason": "no_gap"}


async def test_resolve_unknown_interview_errors(full_pool) -> None:
    tools = await _register(full_pool)
    resolve = tools["chronicler_resolve_gap_interview"]
    result = await resolve(interview_id="nope:gap", answer="confirm")
    assert result["status"] == "error"
