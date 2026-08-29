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


def _assigned_value(tree: ast.Module, name: str, relative_path: str) -> ast.expr:
    values = [
        assignment.value
        for assignment in tree.body
        if isinstance(assignment, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == name for target in assignment.targets)
    ]
    assert len(values) == 1, (relative_path, name)
    return values[0]


def _is_pytest_mark(node: ast.expr, name: str) -> bool:
    return (
        isinstance(node, ast.Attribute)
        and node.attr == name
        and isinstance(node.value, ast.Attribute)
        and node.value.attr == "mark"
        and isinstance(node.value.value, ast.Name)
        and node.value.value.id == "pytest"
    )


def _is_asyncio_decorator(decorator: ast.expr) -> bool:
    marker = decorator.func if isinstance(decorator, ast.Call) else decorator
    return (isinstance(marker, ast.Name) and marker.id == "_asyncio_session") or _is_pytest_mark(
        marker, "asyncio"
    )


def _assert_marker_topology(tree: ast.Module, relative_path: str) -> None:
    """Verify session-loop, integration, and Docker marker semantics structurally."""
    module_marks = _assigned_value(tree, "pytestmark", relative_path)
    assert isinstance(module_marks, ast.List | ast.Tuple), (relative_path, "module pytestmark")
    assert any(_is_pytest_mark(mark, "integration") for mark in module_marks.elts), (
        relative_path,
        "integration marker",
    )

    docker_skip = next(
        (
            mark
            for mark in module_marks.elts
            if isinstance(mark, ast.Call) and _is_pytest_mark(mark.func, "skipif")
        ),
        None,
    )
    assert docker_skip is not None, (relative_path, "Docker skip marker")
    assert len(docker_skip.args) == 1
    condition = docker_skip.args[0]
    assert (
        isinstance(condition, ast.UnaryOp)
        and isinstance(condition.op, ast.Not)
        and isinstance(condition.operand, ast.Name)
        and condition.operand.id == "docker_available"
    ), (relative_path, "Docker skip marker")
    assert not any(
        _is_pytest_mark(mark.func if isinstance(mark, ast.Call) else mark, "asyncio")
        for mark in module_marks.elts
    ), (relative_path, "module asyncio marker")

    asyncio_marker = _assigned_value(tree, "_asyncio_session", relative_path)
    assert isinstance(asyncio_marker, ast.Call) and _is_pytest_mark(
        asyncio_marker.func, "asyncio"
    ), (relative_path, "session-loop alias")
    assert not asyncio_marker.args
    assert len(asyncio_marker.keywords) == 1
    loop_scope = asyncio_marker.keywords[0]
    assert (
        loop_scope.arg == "loop_scope"
        and isinstance(loop_scope.value, ast.Constant)
        and loop_scope.value.value == "session"
    ), (relative_path, "session-loop alias")

    tests = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        and node.name.startswith("test_")
    ]
    assert tests
    for test in tests:
        has_session_alias = any(
            isinstance(decorator, ast.Name) and decorator.id == "_asyncio_session"
            for decorator in test.decorator_list
        )
        has_asyncio_marker = any(
            _is_asyncio_decorator(decorator) for decorator in test.decorator_list
        )
        if isinstance(test, ast.AsyncFunctionDef):
            assert has_session_alias, (relative_path, test.name, "session-loop alias")
        else:
            assert not has_asyncio_marker, (relative_path, test.name, "asyncio marker on sync test")


def test_session_asyncio_marker_is_explicit_on_async_core_tests_only() -> None:
    """Module marks must not warn on static guards that execute synchronously."""
    for relative_path in _TARGETS:
        tree = ast.parse((_REPO_ROOT / relative_path).read_text(encoding="utf-8"))
        _assert_marker_topology(tree, relative_path)


def test_marker_topology_rejects_alias_and_module_mark_regressions() -> None:
    """The guard must reject weakened loop or integration/Docker semantics."""
    relative_path = _TARGETS[0]
    source = (_REPO_ROOT / relative_path).read_text(encoding="utf-8")

    weakened_alias = source.replace(
        '_asyncio_session = pytest.mark.asyncio(loop_scope="session")',
        "_asyncio_session = pytest.mark.unit",
        1,
    )
    with pytest.raises(AssertionError, match="session-loop alias"):
        _assert_marker_topology(ast.parse(weakened_alias), relative_path)

    removed_module_marks = source.replace(
        "pytestmark = [\n"
        "    pytest.mark.integration,\n"
        '    pytest.mark.skipif(not docker_available, reason="Docker not available"),\n'
        "]",
        "pytestmark = []",
        1,
    )
    with pytest.raises(AssertionError, match="integration marker"):
        _assert_marker_topology(ast.parse(removed_module_marks), relative_path)


def test_marker_topology_rejects_direct_asyncio_marker_on_sync_test() -> None:
    """A direct asyncio decorator must not evade the synchronous-test guard."""
    relative_path = _TARGETS[1]
    source = (_REPO_ROOT / relative_path).read_text(encoding="utf-8")
    direct_sync_marker = source.replace(
        "def test_no_delete_or_truncate_in_sessions_module():",
        '@pytest.mark.asyncio(loop_scope="session")\n'
        "def test_no_delete_or_truncate_in_sessions_module():",
        1,
    )

    with pytest.raises(AssertionError, match="asyncio marker on sync test"):
        _assert_marker_topology(ast.parse(direct_sync_marker), relative_path)
