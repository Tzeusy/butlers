"""Root conftest.py — re-exports shared fixtures so they are available to tests
in both ``tests/`` and ``butlers/*/tests/`` directories.
"""

from tests.conftest import MockSpawner, SpawnerResult, mock_spawner  # noqa: F401

__all__ = ["MockSpawner", "SpawnerResult", "mock_spawner"]
