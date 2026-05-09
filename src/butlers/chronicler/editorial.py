"""Editorial briefing computation for the Chronicles dashboard.

Pure-deterministic helpers that compute the briefing payload (attention
items, KPI snapshot, recent-days index, headline, and templated voice
paragraph) for a single day window. Reads only from the chronicler
schema. NEVER invokes an LLM. The voice paragraph that this module
produces is the templated fallback; the live ``llm·cached`` path reads
from ``chronicler.tier2_cache`` and is wired in the API router itself.

Voice rules (per ``about/heart-and-soul/design-language.md``):
- Sentence case.
- No exclamation marks.
- No em-dashes (use comma, colon, parentheses).
- No "please".
- Past tense for events, present tense for state.
"""

from __future__ import annotations

import zoneinfo
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

import asyncpg

# ── Tunables ────────────────────────────────────────────────────────────────

# Sleep anomaly threshold: today's sleep falls below this fraction of the
# 7-day median to be flagged.
SLEEP_ANOMALY_FRACTION = 0.7

# Waking-gap anomaly threshold (minutes).
WAKING_GAP_ANOMALY_MINUTES = 6 * 60

# Waking hours used for gap detection (owner-tz local time).
WAKING_HOUR_START = 6
WAKING_HOUR_END = 22

# Source-health: how recently a last_error counts as "live".
SOURCE_LAST_ERROR_WINDOW_HOURS = 24

# Sleep streak: a day "counts" toward the streak if any sleep_episode
# overlaps it. The day window is computed in owner-tz.
STREAK_LOOKBACK_DAYS = 30


# ── Public dataclass shapes ────────────────────────────────────────────────


@dataclass
class AttentionItem:
    kind: str
    severity: str
    title: str
    detail: str | None = None
    action_href: str | None = None


@dataclass
class LaneHours:
    lane: str
    hours: float


@dataclass
class Streaks:
    sleep: int = 0
    exercise: int = 0


@dataclass
class KpiSnapshot:
    hours_by_top_lanes: list[LaneHours]
    longest_episode_minutes: int
    longest_episode_title: str | None
    longest_gap_minutes: int
    sleep_minutes: int
    streaks: Streaks


@dataclass
class RecentDay:
    date: str
    total_minutes: int
    top_lane: str | None
    episode_count: int


@dataclass
class BriefingPayload:
    """Everything a briefing endpoint composes minus the voice paragraph."""

    state_class: str
    headline: str
    kpi: KpiSnapshot
    attention_items: list[AttentionItem]
    recent_days: list[RecentDay]


# ── State classification ───────────────────────────────────────────────────


def classify_state(items: Sequence[AttentionItem]) -> str:
    """Deterministic state classification.

    `urgent` if any high-severity item; otherwise count buckets:
    `busy` for >= 3, `mild` for 1-2, `quiet` for 0.
    """
    if not items:
        return "quiet"
    if any(it.severity == "high" for it in items):
        return "urgent"
    if len(items) >= 3:
        return "busy"
    return "mild"


def headline_for(state_class: str, n_items: int) -> str:
    """Templated headline. Sentence case, no exclamation, no em-dash."""
    if state_class == "urgent":
        if n_items == 1:
            return "One thing needs attention."
        return f"{n_items} things need attention."
    if state_class == "busy":
        return f"A full day, with {n_items} items waiting."
    if state_class == "mild":
        return "Mostly quiet, with one note." if n_items == 1 else "Mostly quiet, with two notes."
    return "Quiet day."


def templated_voice_paragraph(payload: BriefingPayload) -> str:
    """Produce a deterministic Voice paragraph when no LLM cache exists.

    Past tense for events; present tense for state. Sentence case. No
    em-dashes, no exclamation, no "please".
    """
    parts: list[str] = []
    top = payload.kpi.hours_by_top_lanes[:2]
    if top:
        if len(top) == 1:
            parts.append(f"The day was led by {top[0].lane} at {top[0].hours:.1f} hours.")
        else:
            parts.append(
                f"The day was led by {top[0].lane} ({top[0].hours:.1f}h) and "
                f"{top[1].lane} ({top[1].hours:.1f}h)."
            )
    else:
        parts.append("The day produced no projected episodes.")

    if payload.kpi.sleep_minutes > 0:
        h = payload.kpi.sleep_minutes // 60
        m = payload.kpi.sleep_minutes % 60
        parts.append(f"Sleep was logged at {h}h {m:02d}m.")

    if payload.kpi.longest_gap_minutes >= WAKING_GAP_ANOMALY_MINUTES:
        gap_h = payload.kpi.longest_gap_minutes // 60
        parts.append(f"The longest waking gap reached {gap_h} hours.")

    if not payload.attention_items:
        parts.append("Nothing needs attention.")
    return " ".join(parts).strip()


# ── Time-window helpers ────────────────────────────────────────────────────


def day_window_utc(target: date, tz_name: str) -> tuple[datetime, datetime]:
    """Return [start, end) in UTC for ``target`` interpreted in ``tz_name``."""
    try:
        tz = zoneinfo.ZoneInfo(tz_name)
    except Exception:
        tz = UTC
    start_local = datetime.combine(target, time.min, tzinfo=tz)
    end_local = start_local + timedelta(days=1)
    return start_local.astimezone(UTC), end_local.astimezone(UTC)


# ── Database queries (single round-trip per concern) ───────────────────────


_LANE_TOTALS_SQL = """
WITH winsel AS (
    SELECT
        e.id,
        e.title,
        COALESCE(o.corrected_start_at, e.start_at) AS s_at,
        COALESCE(o.corrected_end_at, e.end_at)     AS e_at,
        e.source_name,
        e.episode_type,
        e.payload->>'trigger_source' AS trigger_source
    FROM episodes e
    LEFT JOIN LATERAL (
        SELECT corrected_start_at, corrected_end_at, corrected_tombstone_at
        FROM overrides
        WHERE target_kind = 'episode'
          AND target_id   = e.id
        ORDER BY created_at DESC
        LIMIT 1
    ) o ON TRUE
    WHERE e.tombstone_at IS NULL
      AND COALESCE(o.corrected_tombstone_at, NULL) IS NULL
      AND COALESCE(o.corrected_start_at, e.start_at) < $2
      AND (
          COALESCE(o.corrected_end_at, e.end_at) IS NULL
          OR COALESCE(o.corrected_end_at, e.end_at) > $1
      )
)
SELECT
    id,
    title,
    s_at,
    e_at,
    source_name,
    episode_type,
    trigger_source
FROM winsel
ORDER BY s_at
"""


async def _fetch_window_episodes(
    pool: asyncpg.Pool, start_utc: datetime, end_utc: datetime
) -> list[asyncpg.Record]:
    async with pool.acquire() as conn:
        return list(await conn.fetch(_LANE_TOTALS_SQL, start_utc, end_utc))


async def _fetch_sleep_minutes_for_day(
    pool: asyncpg.Pool, start_utc: datetime, end_utc: datetime
) -> int:
    sql = """
    SELECT COALESCE(SUM(
        EXTRACT(EPOCH FROM (
            LEAST(COALESCE(end_at, $2), $2)
            - GREATEST(start_at, $1)
        ))
    ), 0)::bigint AS seconds
    FROM episodes
    WHERE tombstone_at IS NULL
      AND source_name = 'google_health.measurements'
      AND episode_type = 'sleep_episode'
      AND start_at < $2
      AND (end_at IS NULL OR end_at > $1)
    """
    async with pool.acquire() as conn:
        seconds = await conn.fetchval(sql, start_utc, end_utc) or 0
    return int(seconds) // 60


async def _fetch_recent_days(
    pool: asyncpg.Pool, end_utc: datetime, days: int, tz_name: str
) -> list[RecentDay]:
    """Return up to ``days`` recent calendar days ending at ``end_utc``."""
    out: list[RecentDay] = []
    try:
        tz = zoneinfo.ZoneInfo(tz_name)
    except Exception:
        tz = UTC
    end_local_date = end_utc.astimezone(tz).date()
    for offset in range(days):
        d = end_local_date - timedelta(days=offset + 1)  # skip "today"; recent_days = prior days
        d_start_utc, d_end_utc = day_window_utc(d, tz_name)
        episodes = await _fetch_window_episodes(pool, d_start_utc, d_end_utc)
        if not episodes:
            out.append(
                RecentDay(date=d.isoformat(), total_minutes=0, top_lane=None, episode_count=0)
            )
            continue
        # Compute totals per lane and overall episode count.
        from butlers.chronicler.aggregations import category_for

        lane_seconds: dict[str, float] = {}
        total_seconds = 0.0
        for r in episodes:
            cat = category_for(
                r["source_name"],
                r["episode_type"],
                trigger_source=r["trigger_source"],
            )
            s_at = r["s_at"]
            e_at = r["e_at"] or d_end_utc
            clipped_start = max(s_at, d_start_utc)
            clipped_end = min(e_at, d_end_utc)
            secs = max(0.0, (clipped_end - clipped_start).total_seconds())
            lane_seconds[cat] = lane_seconds.get(cat, 0.0) + secs
            total_seconds += secs
        top_lane = max(lane_seconds.items(), key=lambda kv: kv[1])[0] if lane_seconds else None
        out.append(
            RecentDay(
                date=d.isoformat(),
                total_minutes=int(total_seconds // 60),
                top_lane=top_lane,
                episode_count=len(episodes),
            )
        )
    return out


async def _compute_streaks(pool: asyncpg.Pool, end_utc: datetime, tz_name: str) -> Streaks:
    """Compute consecutive-day streaks for sleep and workout episodes."""
    try:
        tz = zoneinfo.ZoneInfo(tz_name)
    except Exception:
        tz = UTC
    today_local_date = end_utc.astimezone(tz).date()
    sleep_streak = 0
    workout_streak = 0
    sleep_broken = False
    workout_broken = False
    for offset in range(STREAK_LOOKBACK_DAYS):
        d = today_local_date - timedelta(days=offset + 1)
        d_start, d_end = day_window_utc(d, tz_name)
        if not sleep_broken:
            sql = """
            SELECT EXISTS (
                SELECT 1 FROM episodes
                WHERE tombstone_at IS NULL
                  AND source_name = 'google_health.measurements'
                  AND episode_type = 'sleep_episode'
                  AND start_at < $2
                  AND (end_at IS NULL OR end_at > $1)
            )
            """
            async with pool.acquire() as conn:
                hit = await conn.fetchval(sql, d_start, d_end)
            if hit:
                sleep_streak += 1
            else:
                sleep_broken = True
        if not workout_broken:
            sql_w = """
            SELECT EXISTS (
                SELECT 1 FROM episodes
                WHERE tombstone_at IS NULL
                  AND source_name = 'google_health.measurements'
                  AND episode_type = 'workout_episode'
                  AND start_at < $2
                  AND (end_at IS NULL OR end_at > $1)
            )
            """
            async with pool.acquire() as conn:
                hit_w = await conn.fetchval(sql_w, d_start, d_end)
            if hit_w:
                workout_streak += 1
            else:
                workout_broken = True
        if sleep_broken and workout_broken:
            break
    return Streaks(sleep=sleep_streak, exercise=workout_streak)


async def _fetch_source_health_items(pool: asyncpg.Pool) -> list[AttentionItem]:
    """Read source-state and produce one attention item per degraded row.

    Source state is split across two tables in the chronicler schema:
    ``source_adapter_state`` (active flag + inactive_reason) and
    ``projection_checkpoints`` (last_run_at + last_error). We join them to
    produce one attention row per source where either the adapter is
    inactive or the most recent run errored within the cutoff window.
    """
    items: list[AttentionItem] = []
    cutoff = datetime.now(UTC) - timedelta(hours=SOURCE_LAST_ERROR_WINDOW_HOURS)
    sql = """
    SELECT
        sas.source_name,
        sas.active,
        sas.inactive_reason,
        cp.last_run_at,
        cp.last_error
    FROM source_adapter_state sas
    LEFT JOIN LATERAL (
        SELECT last_run_at, last_error
        FROM projection_checkpoints pc
        WHERE pc.source_name = sas.source_name
        ORDER BY pc.last_run_at DESC NULLS LAST
        LIMIT 1
    ) cp ON TRUE
    """
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(sql)
    except (asyncpg.UndefinedTableError, asyncpg.PostgresError):
        return items
    for r in rows:
        last_error = r["last_error"]
        last_run_at = r["last_run_at"]
        inactive_reason = r["inactive_reason"]
        if last_error and last_run_at and last_run_at >= cutoff:
            items.append(
                AttentionItem(
                    kind="source_health",
                    severity="high",
                    title=f"{r['source_name']} projection error",
                    detail=str(last_error)[:140],
                    action_href=None,
                )
            )
        elif inactive_reason:
            items.append(
                AttentionItem(
                    kind="source_health",
                    severity="medium",
                    title=f"{r['source_name']} inactive",
                    detail=str(inactive_reason)[:140],
                    action_href=None,
                )
            )
    return items


async def _fetch_open_corrections(
    pool: asyncpg.Pool, start_utc: datetime, end_utc: datetime
) -> int:
    sql = """
    SELECT COUNT(*) AS n
    FROM overrides o
    JOIN episodes e ON e.id = o.target_id AND o.target_kind = 'episode'
    WHERE o.corrected_tombstone_at IS NULL
      AND e.tombstone_at IS NULL
      AND e.start_at < $2
      AND (e.end_at IS NULL OR e.end_at > $1)
    """
    async with pool.acquire() as conn:
        return int(await conn.fetchval(sql, start_utc, end_utc) or 0)


# ── Anomaly detection helpers ──────────────────────────────────────────────


async def _fetch_sleep_median_prior_week(
    pool: asyncpg.Pool, end_utc: datetime, tz_name: str
) -> int:
    """Return median sleep_minutes across the seven calendar days preceding."""
    try:
        tz = zoneinfo.ZoneInfo(tz_name)
    except Exception:
        tz = UTC
    today_local = end_utc.astimezone(tz).date()
    minutes: list[int] = []
    for offset in range(1, 8):
        d = today_local - timedelta(days=offset)
        ds, de = day_window_utc(d, tz_name)
        m = await _fetch_sleep_minutes_for_day(pool, ds, de)
        minutes.append(m)
    if not minutes:
        return 0
    s = sorted(minutes)
    return s[len(s) // 2]


def _detect_waking_gaps(
    episodes: Iterable[asyncpg.Record],
    start_utc: datetime,
    end_utc: datetime,
    tz_name: str,
) -> list[int]:
    """Return list of gap minutes that exceed the waking-gap threshold."""
    try:
        tz = zoneinfo.ZoneInfo(tz_name)
    except Exception:
        tz = UTC
    spans: list[tuple[datetime, datetime]] = []
    for r in episodes:
        s = r["s_at"]
        e = r["e_at"] or end_utc
        if s < e:
            spans.append((s, e))
    if not spans:
        return []
    spans.sort()
    # Merge overlapping spans.
    merged: list[tuple[datetime, datetime]] = [spans[0]]
    for s, e in spans[1:]:
        ls, le = merged[-1]
        if s <= le:
            merged[-1] = (ls, max(le, e))
        else:
            merged.append((s, e))
    flagged: list[int] = []
    for i in range(1, len(merged)):
        prev_end = merged[i - 1][1]
        curr_start = merged[i][0]
        gap_seconds = (curr_start - prev_end).total_seconds()
        if gap_seconds < WAKING_GAP_ANOMALY_MINUTES * 60:
            continue
        # Confirm at least part of the gap intersects waking hours.
        local_prev_end = prev_end.astimezone(tz)
        local_curr_start = curr_start.astimezone(tz)
        if local_prev_end.hour < WAKING_HOUR_END or local_curr_start.hour >= WAKING_HOUR_START:
            flagged.append(int(gap_seconds // 60))
    return flagged


# ── KPI computation ───────────────────────────────────────────────────────


def _compute_kpi(
    episodes: Sequence[asyncpg.Record],
    start_utc: datetime,
    end_utc: datetime,
    sleep_minutes: int,
    streaks: Streaks,
    waking_gaps: Sequence[int],
) -> KpiSnapshot:
    from butlers.chronicler.aggregations import category_for

    lane_seconds: dict[str, float] = {}
    longest_minutes = 0
    longest_title: str | None = None
    for r in episodes:
        s = max(r["s_at"], start_utc)
        e = min(r["e_at"] or end_utc, end_utc)
        secs = max(0.0, (e - s).total_seconds())
        cat = category_for(
            r["source_name"],
            r["episode_type"],
            trigger_source=r["trigger_source"],
        )
        lane_seconds[cat] = lane_seconds.get(cat, 0.0) + secs
        mins = int(secs // 60)
        if mins > longest_minutes:
            longest_minutes = mins
            longest_title = r["title"]

    top = sorted(lane_seconds.items(), key=lambda kv: kv[1], reverse=True)[:3]
    longest_gap = max(waking_gaps) if waking_gaps else 0
    return KpiSnapshot(
        hours_by_top_lanes=[
            LaneHours(lane=lane, hours=round(secs / 3600.0, 1)) for lane, secs in top
        ],
        longest_episode_minutes=longest_minutes,
        longest_episode_title=longest_title,
        longest_gap_minutes=longest_gap,
        sleep_minutes=sleep_minutes,
        streaks=streaks,
    )


# ── Top-level orchestrator ────────────────────────────────────────────────


async def compose_briefing_payload(
    pool: asyncpg.Pool,
    target: date,
    tz_name: str,
) -> BriefingPayload:
    """Compose the full editorial briefing payload (without voice paragraph).

    Reads only from the chronicler schema. NEVER invokes an LLM.
    """
    start_utc, end_utc = day_window_utc(target, tz_name)

    episodes = await _fetch_window_episodes(pool, start_utc, end_utc)
    sleep_minutes = await _fetch_sleep_minutes_for_day(pool, start_utc, end_utc)
    streaks = await _compute_streaks(pool, end_utc, tz_name)
    waking_gaps = _detect_waking_gaps(episodes, start_utc, end_utc, tz_name)

    attention_items: list[AttentionItem] = []
    sleep_median = await _fetch_sleep_median_prior_week(pool, end_utc, tz_name)
    if (
        sleep_median > 0
        and sleep_minutes > 0
        and sleep_minutes < int(sleep_median * SLEEP_ANOMALY_FRACTION)
    ):
        attention_items.append(
            AttentionItem(
                kind="anomaly",
                severity="medium",
                title="Short sleep",
                detail=(
                    f"{sleep_minutes // 60}h {sleep_minutes % 60:02d}m, "
                    f"below 7-day median ({sleep_median // 60}h)"
                ),
            )
        )
    for gap_minutes in waking_gaps:
        gap_h = gap_minutes // 60
        attention_items.append(
            AttentionItem(
                kind="anomaly",
                severity="low",
                title="Long waking gap",
                detail=f"{gap_h} hours without a recorded episode",
            )
        )
    attention_items.extend(await _fetch_source_health_items(pool))
    open_corrections = await _fetch_open_corrections(pool, start_utc, end_utc)
    if open_corrections > 0:
        attention_items.append(
            AttentionItem(
                kind="open_correction",
                severity="low",
                title=(
                    "1 unresolved correction"
                    if open_corrections == 1
                    else f"{open_corrections} unresolved corrections"
                ),
            )
        )

    kpi = _compute_kpi(episodes, start_utc, end_utc, sleep_minutes, streaks, waking_gaps)
    state_class = classify_state(attention_items)
    headline = headline_for(state_class, len(attention_items))
    recent_days = await _fetch_recent_days(pool, end_utc, days=7, tz_name=tz_name)

    return BriefingPayload(
        state_class=state_class,
        headline=headline,
        kpi=kpi,
        attention_items=attention_items,
        recent_days=recent_days,
    )


__all__ = [
    "AttentionItem",
    "BriefingPayload",
    "KpiSnapshot",
    "LaneHours",
    "RecentDay",
    "STREAK_LOOKBACK_DAYS",
    "SLEEP_ANOMALY_FRACTION",
    "SOURCE_LAST_ERROR_WINDOW_HOURS",
    "Streaks",
    "WAKING_GAP_ANOMALY_MINUTES",
    "WAKING_HOUR_END",
    "WAKING_HOUR_START",
    "classify_state",
    "compose_briefing_payload",
    "day_window_utc",
    "headline_for",
    "templated_voice_paragraph",
]
