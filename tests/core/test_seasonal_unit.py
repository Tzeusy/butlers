"""Pure unit tests for butlers.core.seasonal (no DB required) — condensed.

Covers:
- validate_month_day: boundary validation
- _is_date_in_range: same-year, cross-year, boundaries
- SEASONAL_PRESETS: preset definitions and year-boundary correctness
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# validate_month_day
# ---------------------------------------------------------------------------


def test_validate_month_day_valid_dates():
    from butlers.core.seasonal import validate_month_day

    for m, d in [(1, 1), (1, 31), (2, 28), (4, 30), (12, 31), (11, 30)]:
        validate_month_day(m, d)  # should not raise


@pytest.mark.parametrize(
    "month,day,match",
    [
        (2, 30, "February"),
        (2, 29, "February"),
        (4, 31, "April"),
        (11, 31, "November"),
        (0, 1, "month"),
        (13, 1, "month"),
        (3, 0, "day"),
        (5, -1, "day"),
    ],
)
def test_validate_month_day_invalid(month, day, match):
    from butlers.core.seasonal import validate_month_day

    with pytest.raises(ValueError, match=match):
        validate_month_day(month, day)


# ---------------------------------------------------------------------------
# _is_date_in_range
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "month,day,active",
    [
        (3, 15, True),  # mid tax season
        (1, 1, True),  # start boundary
        (4, 15, True),  # end boundary
        (6, 1, False),  # outside
        (12, 31, False),  # before start (same-year ordering)
    ],
)
def test_is_date_in_range_same_year(month, day, active):
    from butlers.core.seasonal import _is_date_in_range

    assert _is_date_in_range(month, day, 1, 1, 4, 15) == active


@pytest.mark.parametrize(
    "month,day,active",
    [
        (12, 20, True),  # active in December
        (1, 5, True),  # active in January
        (11, 15, True),  # start boundary
        (1, 10, True),  # end boundary
        (6, 15, False),  # mid-year, outside
        (1, 11, False),  # just past end
        (11, 14, False),  # just before start
    ],
)
def test_is_date_in_range_cross_year(month, day, active):
    from butlers.core.seasonal import _is_date_in_range

    assert _is_date_in_range(month, day, 11, 15, 1, 10) == active


# ---------------------------------------------------------------------------
# SEASONAL_PRESETS
# ---------------------------------------------------------------------------


def test_all_presets_present_with_valid_dates_and_context_hints():
    from butlers.core.seasonal import SEASONAL_PRESETS, validate_month_day

    expected = {
        "us-tax-season",
        "year-end-holidays",
        "back-to-school",
        "spring-semester",
        "fall-semester",
    }
    assert set(SEASONAL_PRESETS.keys()) == expected

    for name, preset in SEASONAL_PRESETS.items():
        validate_month_day(preset["start_month"], preset["start_day"])
        validate_month_day(preset["end_month"], preset["end_day"])
        hint = preset.get("metadata", {}).get("context_hint", "").strip()
        assert hint, f"Preset {name!r} missing context_hint"


def test_us_tax_season_dates():
    from butlers.core.seasonal import SEASONAL_PRESETS

    p = SEASONAL_PRESETS["us-tax-season"]
    assert (p["start_month"], p["start_day"]) == (1, 1)
    assert (p["end_month"], p["end_day"]) == (4, 15)


def test_year_end_holidays_wraps_year():
    from butlers.core.seasonal import SEASONAL_PRESETS, _is_date_in_range

    p = SEASONAL_PRESETS["year-end-holidays"]
    assert p["start_month"] == 12 and p["end_month"] == 1
    assert _is_date_in_range(12, 25, p["start_month"], p["start_day"], p["end_month"], p["end_day"])
    assert not _is_date_in_range(
        3, 1, p["start_month"], p["start_day"], p["end_month"], p["end_day"]
    )
