"""Tests for the scoped test runner."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from butlers.testing.changed_files import ChangedFiles
from butlers.testing.scoped_runner import (
    DEFAULT_IGNORES,
    ScopedTestPlan,
    build_pytest_command,
    plan_scoped_tests,
)
from butlers.testing.source_test_map import FULL_SUITE

# ---------------------------------------------------------------------------
# plan_scoped_tests
# ---------------------------------------------------------------------------


class TestPlanScopedTests:
    def test_no_changed_files(self):
        with patch(
            "butlers.testing.scoped_runner.get_changed_files",
            return_value=ChangedFiles(files=[], base_ref="origin/main", head_ref="feat"),
        ):
            plan = plan_scoped_tests("feat")
        assert plan.scope == "none"
        assert plan.reason == "No files changed"
        assert plan.test_paths == []
        assert plan.changed_files == []

    def test_non_testable_files_only(self):
        with patch(
            "butlers.testing.scoped_runner.get_changed_files",
            return_value=ChangedFiles(
                files=["frontend/src/App.tsx", "docs/README.md"],
                base_ref="origin/main",
                head_ref="feat",
            ),
        ):
            plan = plan_scoped_tests("feat")
        assert plan.scope == "none"
        assert plan.changed_files == ["frontend/src/App.tsx", "docs/README.md"]

    def test_scoped_to_module(self):
        with patch(
            "butlers.testing.scoped_runner.get_changed_files",
            return_value=ChangedFiles(
                files=["src/butlers/modules/memory/tools/search.py"],
                base_ref="origin/main",
                head_ref="feat",
            ),
        ):
            plan = plan_scoped_tests("feat")
        assert plan.scope == "scoped"
        assert plan.test_paths == ["tests/modules/memory/"]
        assert plan.changed_files == ["src/butlers/modules/memory/tools/search.py"]

    def test_full_suite_trigger(self):
        with patch(
            "butlers.testing.scoped_runner.get_changed_files",
            return_value=ChangedFiles(
                files=["conftest.py", "src/butlers/api/routers/search.py"],
                base_ref="origin/main",
                head_ref="feat",
            ),
        ):
            plan = plan_scoped_tests("feat")
        assert plan.scope == "full"
        assert plan.test_paths == FULL_SUITE

    def test_multiple_modules_scoped(self):
        with patch(
            "butlers.testing.scoped_runner.get_changed_files",
            return_value=ChangedFiles(
                files=[
                    "src/butlers/modules/memory/tools/search.py",
                    "src/butlers/api/routers/memory.py",
                ],
                base_ref="origin/main",
                head_ref="feat",
            ),
        ):
            plan = plan_scoped_tests("feat")
        assert plan.scope == "scoped"
        assert "tests/modules/memory/" in plan.test_paths
        assert "tests/api/" in plan.test_paths

    def test_passes_base_and_repo_dir(self):
        with patch(
            "butlers.testing.scoped_runner.get_changed_files",
            return_value=ChangedFiles(files=[], base_ref="origin/dev", head_ref="feat"),
        ) as mock_gcf:
            plan_scoped_tests("feat", base="origin/dev", repo_dir="/tmp/repo")
        mock_gcf.assert_called_once_with("feat", "origin/dev", repo_dir="/tmp/repo")

    def test_frozen_dataclass(self):
        plan = ScopedTestPlan(scope="none", reason="test")
        with pytest.raises(AttributeError):
            plan.scope = "full"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# build_pytest_command
# ---------------------------------------------------------------------------


class TestBuildPytestCommand:
    def test_scoped_command(self):
        plan = ScopedTestPlan(
            scope="scoped",
            test_paths=["tests/api/", "tests/modules/memory/"],
            changed_files=["src/butlers/api/app.py"],
            reason="Scoped",
        )
        cmd = build_pytest_command(plan)
        assert cmd[:3] == ["uv", "run", "pytest"]
        assert "tests/api/" in cmd
        assert "tests/modules/memory/" in cmd
        for ignore in DEFAULT_IGNORES:
            assert ignore in cmd

    def test_full_suite_command(self):
        plan = ScopedTestPlan(
            scope="full",
            test_paths=["tests/"],
            changed_files=["conftest.py"],
            reason="Full suite",
        )
        cmd = build_pytest_command(plan)
        assert cmd[:3] == ["uv", "run", "pytest"]
        assert "tests/" in cmd

    def test_none_scope_raises(self):
        plan = ScopedTestPlan(scope="none", reason="No tests needed")
        with pytest.raises(ValueError, match="No tests to run"):
            build_pytest_command(plan)

    def test_custom_ignores(self):
        plan = ScopedTestPlan(
            scope="scoped",
            test_paths=["tests/api/"],
            changed_files=[],
            reason="test",
        )
        cmd = build_pytest_command(plan, ignores=["tests/slow/"])
        assert "--ignore" in cmd
        idx = cmd.index("--ignore")
        assert cmd[idx + 1] == "tests/slow/"
        # Default ignores should NOT be present
        assert "tests/test_db.py" not in cmd

    def test_extra_args(self):
        plan = ScopedTestPlan(
            scope="scoped",
            test_paths=["tests/api/"],
            changed_files=[],
            reason="test",
        )
        cmd = build_pytest_command(plan, extra_args=["-q", "--tb=short", "--maxfail=1"])
        assert "-q" in cmd
        assert "--tb=short" in cmd
        assert "--maxfail=1" in cmd

    def test_default_ignores_included(self):
        plan = ScopedTestPlan(
            scope="scoped",
            test_paths=["tests/api/"],
            changed_files=[],
            reason="test",
        )
        cmd = build_pytest_command(plan)
        for ignore in DEFAULT_IGNORES:
            assert ignore in cmd

    def test_command_order(self):
        """Test paths come before ignores, ignores before extra args."""
        plan = ScopedTestPlan(
            scope="scoped",
            test_paths=["tests/api/"],
            changed_files=[],
            reason="test",
        )
        cmd = build_pytest_command(plan, extra_args=["-v"])
        # uv run pytest <paths> --ignore <x> --ignore <y> -v
        path_idx = cmd.index("tests/api/")
        ignore_idx = cmd.index("--ignore")
        v_idx = cmd.index("-v")
        assert path_idx < ignore_idx < v_idx


# ---------------------------------------------------------------------------
# Report formatting
# ---------------------------------------------------------------------------


class TestReportFormatting:
    def test_scoped_report_content(self):
        plan = ScopedTestPlan(
            scope="scoped",
            test_paths=["tests/api/", "tests/modules/memory/"],
            changed_files=["src/butlers/api/app.py", "src/butlers/modules/memory/tools/search.py"],
            reason="Scoped to 2 test path(s) from 2 changed file(s)",
        )
        report = plan.report()
        assert "SCOPED" in report
        assert "tests/api/" in report
        assert "tests/modules/memory/" in report
        assert "src/butlers/api/app.py" in report

    def test_full_suite_report(self):
        plan = ScopedTestPlan(
            scope="full",
            test_paths=["tests/"],
            changed_files=["conftest.py"],
            reason="Cross-cutting change detected",
        )
        report = plan.report()
        assert "FULL SUITE" in report

    def test_none_report(self):
        plan = ScopedTestPlan(scope="none", reason="No files changed")
        report = plan.report()
        assert "NO TESTS" in report
