"""Tests for ``butlers.chronicler.editorial`` deterministic helpers.

DB-bound flows (``compose_briefing_payload``, ``_fetch_*``) are covered by
the briefing API integration tests. This file exercises the pure functions:
state classification, headline templates, templated voice paragraph,
day-window helper, and waking-gap detection.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from butlers.chronicler.editorial import (
    AttentionItem,
    BriefingPayload,
    KpiSnapshot,
    LaneHours,
    Streaks,
    _detect_waking_gaps,
    classify_state,
    day_window_utc,
    headline_for,
    templated_voice_paragraph,
)

# ── classify_state ────────────────────────────────────────────────────────


def test_classify_state_quiet_when_no_items() -> None:
    assert classify_state([]) == "quiet"


def test_classify_state_urgent_on_any_high_severity() -> None:
    items = [AttentionItem(kind="anomaly", severity="high", title="x")]
    assert classify_state(items) == "urgent"


def test_classify_state_urgent_dominates_over_count() -> None:
    items = [
        AttentionItem(kind="anomaly", severity="high", title="x"),
        AttentionItem(kind="anomaly", severity="low", title="x"),
    ]
    assert classify_state(items) == "urgent"


def test_classify_state_busy_at_three_or_more() -> None:
    items = [AttentionItem(kind="anomaly", severity="low", title="x") for _ in range(3)]
    assert classify_state(items) == "busy"


def test_classify_state_mild_for_one_or_two() -> None:
    items = [AttentionItem(kind="anomaly", severity="low", title="x")]
    assert classify_state(items) == "mild"
    items.append(AttentionItem(kind="anomaly", severity="low", title="y"))
    assert classify_state(items) == "mild"


# ── headline_for ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "state,n,expected",
    [
        ("urgent", 1, "One thing needs attention."),
        ("urgent", 2, "2 things need attention."),
        ("urgent", 5, "5 things need attention."),
        ("busy", 3, "A full day, with 3 items waiting."),
        ("mild", 1, "Mostly quiet, with one note."),
        ("mild", 2, "Mostly quiet, with two notes."),
        ("quiet", 0, "Quiet day."),
    ],
)
def test_headline_templates(state: str, n: int, expected: str) -> None:
    assert headline_for(state, n) == expected


def test_headline_no_em_dashes_no_exclamation() -> None:
    """Voice rules: no em-dashes, no exclamation marks."""
    for state in ("urgent", "busy", "mild", "quiet"):
        for n in (0, 1, 2, 3, 5):
            text = headline_for(state, n)
            assert "—" not in text, f"em-dash leaked into {state}/{n}: {text!r}"
            assert "!" not in text, f"exclamation leaked into {state}/{n}: {text!r}"


# ── templated_voice_paragraph ────────────────────────────────────────────


def _payload(
    *,
    top_lanes: list[LaneHours] | None = None,
    sleep_minutes: int = 0,
    longest_gap: int = 0,
    attention: list[AttentionItem] | None = None,
) -> BriefingPayload:
    return BriefingPayload(
        state_class="quiet",
        headline="x",
        kpi=KpiSnapshot(
            hours_by_top_lanes=top_lanes or [],
            longest_episode_minutes=0,
            longest_episode_title=None,
            longest_gap_minutes=longest_gap,
            sleep_minutes=sleep_minutes,
            streaks=Streaks(),
        ),
        attention_items=attention or [],
        recent_days=[],
    )


def test_voice_paragraph_describes_top_lane() -> None:
    payload = _payload(top_lanes=[LaneHours(lane="conversations", hours=2.4)])
    text = templated_voice_paragraph(payload)
    assert "conversations" in text
    assert "2.4" in text


def test_voice_paragraph_mentions_two_lanes() -> None:
    payload = _payload(
        top_lanes=[
            LaneHours(lane="conversations", hours=2.4),
            LaneHours(lane="calendar", hours=1.1),
        ]
    )
    text = templated_voice_paragraph(payload)
    assert "conversations" in text
    assert "calendar" in text


def test_voice_paragraph_handles_empty_day() -> None:
    payload = _payload()
    text = templated_voice_paragraph(payload)
    assert "no projected episodes" in text
    assert "Nothing needs attention" in text


def test_voice_paragraph_includes_sleep_when_present() -> None:
    payload = _payload(sleep_minutes=432)
    text = templated_voice_paragraph(payload)
    assert "Sleep" in text
    assert "7h" in text


def test_voice_paragraph_no_em_dashes_no_please_no_exclamation() -> None:
    cases = [
        _payload(),
        _payload(top_lanes=[LaneHours("conversations", 1.0)]),
        _payload(
            top_lanes=[LaneHours("a", 1.0), LaneHours("b", 0.5)],
            sleep_minutes=300,
            longest_gap=480,
        ),
    ]
    banned = ("—", "!", "please")
    for payload in cases:
        text = templated_voice_paragraph(payload)
        for token in banned:
            assert token not in text, f"banned token {token!r} in voice paragraph: {text!r}"


# ── day_window_utc ───────────────────────────────────────────────────────


def test_day_window_utc_singapore() -> None:
    start, end = day_window_utc(date(2026, 5, 8), "Asia/Singapore")
    # Singapore is UTC+8: 2026-05-08 00:00 SGT == 2026-05-07 16:00 UTC.
    assert start == datetime(2026, 5, 7, 16, 0, tzinfo=UTC)
    assert end == datetime(2026, 5, 8, 16, 0, tzinfo=UTC)


def test_day_window_utc_invalid_tz_falls_back_to_utc() -> None:
    start, end = day_window_utc(date(2026, 5, 8), "Not/A/Real/Zone")
    assert start == datetime(2026, 5, 8, 0, 0, tzinfo=UTC)
    assert end == datetime(2026, 5, 9, 0, 0, tzinfo=UTC)


# ── _detect_waking_gaps ──────────────────────────────────────────────────


class _FakeRow(dict):
    """Lightweight asyncpg.Record stand-in for unit tests."""

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)


def test_waking_gap_under_threshold_not_flagged() -> None:
    start = datetime(2026, 5, 8, 0, 0, tzinfo=UTC)
    end = datetime(2026, 5, 8, 23, 59, tzinfo=UTC)
    episodes = [
        _FakeRow(
            s_at=datetime(2026, 5, 8, 9, 0, tzinfo=UTC),
            e_at=datetime(2026, 5, 8, 10, 0, tzinfo=UTC),
        ),
        _FakeRow(
            s_at=datetime(2026, 5, 8, 13, 0, tzinfo=UTC),  # 3h gap
            e_at=datetime(2026, 5, 8, 14, 0, tzinfo=UTC),
        ),
    ]
    assert _detect_waking_gaps(episodes, start, end, "UTC") == []


def test_waking_gap_over_threshold_flagged() -> None:
    start = datetime(2026, 5, 8, 0, 0, tzinfo=UTC)
    end = datetime(2026, 5, 8, 23, 59, tzinfo=UTC)
    episodes = [
        _FakeRow(
            s_at=datetime(2026, 5, 8, 9, 0, tzinfo=UTC),
            e_at=datetime(2026, 5, 8, 10, 0, tzinfo=UTC),
        ),
        _FakeRow(
            s_at=datetime(2026, 5, 8, 17, 0, tzinfo=UTC),  # 7h gap
            e_at=datetime(2026, 5, 8, 18, 0, tzinfo=UTC),
        ),
    ]
    gaps = _detect_waking_gaps(episodes, start, end, "UTC")
    assert len(gaps) == 1
    assert 6 * 60 <= gaps[0] <= 8 * 60


def test_waking_gap_no_episodes() -> None:
    start = datetime(2026, 5, 8, 0, 0, tzinfo=UTC)
    end = datetime(2026, 5, 8, 23, 59, tzinfo=UTC)
    assert _detect_waking_gaps([], start, end, "UTC") == []


def test_waking_gap_overlapping_episodes_merged() -> None:
    start = datetime(2026, 5, 8, 0, 0, tzinfo=UTC)
    end = datetime(2026, 5, 8, 23, 59, tzinfo=UTC)
    # Two overlapping episodes that together span 9-12; gap to next is 6h.
    episodes = [
        _FakeRow(
            s_at=datetime(2026, 5, 8, 9, 0, tzinfo=UTC),
            e_at=datetime(2026, 5, 8, 11, 0, tzinfo=UTC),
        ),
        _FakeRow(
            s_at=datetime(2026, 5, 8, 10, 30, tzinfo=UTC),
            e_at=datetime(2026, 5, 8, 12, 0, tzinfo=UTC),
        ),
        _FakeRow(
            s_at=datetime(2026, 5, 8, 18, 0, tzinfo=UTC),
            e_at=datetime(2026, 5, 8, 19, 0, tzinfo=UTC),
        ),
    ]
    gaps = _detect_waking_gaps(episodes, start, end, "UTC")
    assert len(gaps) == 1
