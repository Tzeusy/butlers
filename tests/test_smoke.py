"""Smoke tests to verify the project skeleton is wired up correctly."""

from tests.conftest import MockSpawner, SpawnerResult


def test_version():
    """Package exposes a version string."""
    import butlers

    assert butlers.__version__ == "0.1.0"


def test_spawner_result_defaults():
    """SpawnerResult has sensible defaults."""
    r = SpawnerResult()
    assert r.result is None
    assert r.tool_calls == []
    assert r.error is None
    assert r.duration_ms == 0


async def test_mock_spawner_records_invocations(mock_spawner: MockSpawner):
    """MockSpawner records invocations and returns the default result."""
    result = await mock_spawner.spawn(prompt="hello")
    assert result.result is None
    assert len(mock_spawner.invocations) == 1
    assert mock_spawner.invocations[0] == {"prompt": "hello"}


async def test_mock_spawner_enqueued_results(mock_spawner: MockSpawner):
    """MockSpawner returns enqueued results in FIFO order."""
    mock_spawner.enqueue_result(SpawnerResult(result="first"))
    mock_spawner.enqueue_result(SpawnerResult(result="second"))

    r1 = await mock_spawner.spawn()
    r2 = await mock_spawner.spawn()
    r3 = await mock_spawner.spawn()

    assert r1.result == "first"
    assert r2.result == "second"
    assert r3.result is None  # falls back to default
