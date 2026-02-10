"""Smoke tests to verify the project skeleton is wired up correctly."""

import pytest

from tests.conftest import MockSpawner, SpawnerResult

pytestmark = pytest.mark.unit


def test_version():
    """Package exposes a version string."""
    import butlers

    assert butlers.__version__ == "0.1.0"


def test_spawner_result_defaults():
    """SpawnerResult has sensible defaults."""
    r = SpawnerResult()
    assert r.output is None
    assert r.success is False
    assert r.tool_calls == []
    assert r.error is None
    assert r.duration_ms == 0


async def test_mock_spawner_records_invocations(mock_spawner: MockSpawner):
    """MockSpawner records invocations and returns the default result."""
    result = await mock_spawner.spawn(prompt="hello")
    assert result.output is None
    assert len(mock_spawner.invocations) == 1
    assert mock_spawner.invocations[0] == {"prompt": "hello"}


async def test_mock_spawner_enqueued_results(mock_spawner: MockSpawner):
    """MockSpawner returns enqueued results in FIFO order."""
    mock_spawner.enqueue_result(SpawnerResult(output="first", success=True))
    mock_spawner.enqueue_result(SpawnerResult(output="second", success=True))

    r1 = await mock_spawner.spawn()
    r2 = await mock_spawner.spawn()
    r3 = await mock_spawner.spawn()

    assert r1.output == "first"
    assert r2.output == "second"
    assert r3.output is None  # falls back to default
