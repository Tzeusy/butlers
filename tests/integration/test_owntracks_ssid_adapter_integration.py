"""Real-Postgres coverage for OwnTracks SSID presence projection."""

from __future__ import annotations

import shutil
from datetime import UTC, datetime, timedelta

import asyncpg
import pytest

from butlers.chronicler.adapters.owntracks import OwnTracksPointAdapter
from butlers.chronicler.adapters.owntracks_ssid import (
    EPISODE_TYPE_WORK_PRESENCE,
    SOURCE_NAME,
    SSID_PLACE_STATE_KEY,
)
from butlers.chronicler.contracts import INITIAL_SOURCES, seed_source_registry
from butlers.chronicler.jobs import run_project_owntracks_ssid
from butlers.core.state import state_set
from butlers.db import register_jsonb_codec
from butlers.testing.migration import create_migrated_test_db, migration_db_name

docker_available = shutil.which("docker") is not None
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not docker_available, reason="Docker not available"),
    pytest.mark.asyncio(loop_scope="session"),
]

_NOW = datetime(2026, 7, 15, 1, 0, tzinfo=UTC)
_ENDPOINT = "owntracks:alice"


@pytest.fixture(scope="module")
def migrated_db_url(postgres_container) -> str:
    return create_migrated_test_db(
        postgres_container,
        migration_db_name(),
        chains=["core", "chronicler"],
    )


@pytest.fixture
async def pool(migrated_db_url: str):
    p = await asyncpg.create_pool(
        migrated_db_url, min_size=1, max_size=5, init=register_jsonb_codec
    )
    await p.execute("TRUNCATE TABLE connectors.owntracks_points CASCADE")
    await p.execute("TRUNCATE TABLE episodes, point_events, projection_checkpoints CASCADE")
    await p.execute("DELETE FROM state WHERE key = $1", SSID_PLACE_STATE_KEY)
    await seed_source_registry(p, sources=INITIAL_SOURCES)
    yield p
    await p.close()


async def _insert_point(pool: asyncpg.Pool, minute: int, ssid: str | None) -> None:
    ts = _NOW + timedelta(minutes=minute)
    raw_payload: dict[str, object] = {"_type": "location", "lat": 1.3, "lon": 103.8}
    if ssid is not None:
        raw_payload["SSID"] = ssid
    await pool.execute(
        """
        INSERT INTO connectors.owntracks_points
            (idempotency_key, ts, lat, lon, accuracy, trigger, event,
             endpoint_identity, raw_payload, recorded_at)
        VALUES ($1, $2, 1.3, 103.8, 10.0, 'p', NULL, $3, $4, $2)
        """,
        f"ssid-test:{minute}",
        ts,
        _ENDPOINT,
        raw_payload,
    )


async def test_state_mapping_projects_gapped_runs_and_skips_unlabelled_ssid(
    pool: asyncpg.Pool,
) -> None:
    await state_set(pool, SSID_PLACE_STATE_KEY, {"Corp WiFi": "work"})

    # First mapped run, an unlabelled SSID boundary, then another mapped run.
    # The unlabelled point is within max_gap of both runs but must never bridge them.
    for minute, ssid in [
        (0, "Corp WiFi"),
        (10, "Corp WiFi"),
        (20, "Cafe WiFi"),
        (30, "Corp WiFi"),
        (40, "Corp WiFi"),
    ]:
        await _insert_point(pool, minute, ssid)

    await OwnTracksPointAdapter().project(pool, chronicler_pool=pool, since=None)
    result = await run_project_owntracks_ssid(pool, None)

    assert result["source_name"] == SOURCE_NAME
    assert result["episodes_closed"] == 2
    rows = await pool.fetch(
        """
        SELECT * FROM episodes
        WHERE source_name = $1 AND episode_type = $2
        ORDER BY start_at
        """,
        SOURCE_NAME,
        EPISODE_TYPE_WORK_PRESENCE,
    )
    assert [(row["start_at"], row["end_at"]) for row in rows] == [
        (_NOW, _NOW + timedelta(minutes=10)),
        (_NOW + timedelta(minutes=30), _NOW + timedelta(minutes=40)),
    ]
    assert all(row["precision"] == "minute" for row in rows)
    assert all(row["layer"] == "activity" for row in rows)
    assert all(row["confidence"] == "medium" for row in rows)
    assert all(row["payload"]["place"] == "work" for row in rows)
    assert all("Cafe WiFi" not in str(row["payload"]) for row in rows)
    assert all(row["evidence_refs"] for row in rows)
