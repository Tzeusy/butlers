"""Keep synchronous core guards out of session-scoped asyncio marking."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).resolve().parents[2]
_TARGETS = (
    "tests/core/test_core_state.py",
    "tests/core/test_core_sessions.py",
)


def test_session_asyncio_marker_is_explicit_on_async_core_tests_only() -> None:
    """Module marks must not warn on static guards that execute synchronously."""
    for relative_path in _TARGETS:
        tree = ast.parse((_REPO_ROOT / relative_path).read_text(encoding="utf-8"))
        module_marks = [
            assignment.value
            for assignment in tree.body
            if isinstance(assignment, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == "pytestmark"
                for target in assignment.targets
            )
        ]
        assert all("asyncio" not in ast.unparse(mark) for mark in module_marks)

        tests = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
            and node.name.startswith("test_")
        ]
        assert tests
        for test in tests:
            decorators = {ast.unparse(decorator) for decorator in test.decorator_list}
            if isinstance(test, ast.AsyncFunctionDef):
                assert "_asyncio_session" in decorators, (relative_path, test.name)
            else:
                assert "_asyncio_session" not in decorators, (relative_path, test.name)
