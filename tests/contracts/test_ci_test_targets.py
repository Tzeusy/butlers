"""Keep local CI lanes and their isolated hosted coverage handoff aligned."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

pytestmark = [
    pytest.mark.unit,
    pytest.mark.skipif(shutil.which("make") is None, reason="requires make"),
]

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    ("target", "fragments"),
    [
        (
            "test-ci-unit",
            (
                "scripts/pytest_gate.py run",
                "git status --porcelain",
                "git rev-parse HEAD",
                "clean=true",
                "tests/ roster/",
                "-q",
                "--maxfail=1",
                "--tb=short",
                "--ignore=tests/e2e",
                "not integration and not e2e and not nightly and not bench and not perf",
                "--cov=src/butlers",
                "--cov-report=json:coverage.json",
                "--cov-report=term-missing",
            ),
        ),
        (
            "test-ci-integration",
            (
                "scripts/pytest_gate.py run",
                "git status --porcelain",
                "git rev-parse HEAD",
                "clean=true",
                "tests/ roster/",
                "-q",
                "--maxfail=5",
                "--tb=short",
                "integration and not nightly and not bench and not perf",
                "-n auto --dist loadfile",
                "--cov=src/butlers",
                "--cov-append",
                "--cov-report=json:coverage.json",
                "--cov-report=term-missing",
            ),
        ),
    ],
)
def test_ci_test_targets_are_receipt_producing_and_keep_ci_pytest_scope(
    target: str, fragments: tuple[str, ...]
) -> None:
    dry_run = subprocess.run(
        ["make", "-n", target],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout

    for fragment in fragments:
        assert fragment in dry_run, f"`make {target}` lost CI fragment {fragment!r}:\n{dry_run}"


def _workflow_step(*, job: dict, name: str) -> dict:
    for step in job["steps"]:
        if step.get("name") == name:
            return step
    raise AssertionError(f"Missing {name!r} step")


def test_ci_workflow_keeps_the_same_pytest_scope_and_combines_isolated_coverage() -> None:
    workflow = yaml.safe_load((REPO_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"))
    jobs = workflow["jobs"]
    unit_job = jobs["check-unit"]
    integration_job = jobs["check-integration"]
    check_job = jobs["check"]

    assert check_job["needs"] == ["check-unit", "check-integration"]
    assert check_job["if"] == "${{ always() && !cancelled() }}"
    for step_name in (
        "Check lock file is up to date",
        "Install dependencies",
        "Lint",
        "Format check",
        "SQL safety check (FOR UPDATE + outer join)",
        "Smoke tests (fast gate + release evidence)",
    ):
        _workflow_step(job=unit_job, name=step_name)
    _workflow_step(job=integration_job, name="Integration test path coverage guard")

    for job in (unit_job, integration_job):
        assert job["services"]["postgres"]["image"] == "postgres:16"
        assert job["env"]["DATABASE_URL"] == "postgresql://postgres:test@localhost:5432/postgres"

    unit_step = _workflow_step(job=unit_job, name="Unit tests")
    integration_step = _workflow_step(
        job=integration_job, name="Integration tests (testcontainers)"
    )
    unit_run = unit_step["run"]
    integration_run = integration_step["run"]

    for fragment in (
        "tests/ roster/ -q --maxfail=1 --tb=short --ignore=tests/e2e",
        "not integration and not e2e and not nightly and not bench and not perf",
        "--cov=src/butlers",
        "--cov-report=term-missing",
        "--junitxml=",
    ):
        assert fragment in unit_run

    for fragment in (
        "tests/ roster/ -q --maxfail=5 --tb=short",
        "integration and not nightly and not bench and not perf",
        "--cov=src/butlers",
        "--cov-report=term-missing",
        "--junitxml=",
    ):
        assert fragment in integration_run

    # Local targets intentionally use --cov-append because they run on one
    # machine. Hosted lanes cannot share a filesystem, so CI must combine
    # independently named artifacts and never pretend append crosses jobs.
    assert "--cov-append" not in unit_run
    assert "--cov-append" not in integration_run
    assert "--durations" not in unit_run
    assert "--durations" not in integration_run
    assert unit_step["env"]["COVERAGE_FILE"].endswith("coverage-unit.data")
    assert integration_step["env"]["COVERAGE_FILE"].endswith("coverage-integration.data")

    combine_step = _workflow_step(
        job=check_job, name="Combine coverage from independent test lanes"
    )
    combine_run = combine_step["run"]
    assert "coverage combine --data-file=" in combine_run
    assert combine_step["env"]["UNIT_COVERAGE"].endswith("coverage-unit.data")
    assert combine_step["env"]["INTEGRATION_COVERAGE"].endswith("coverage-integration.data")

    fan_in_gate = _workflow_step(job=check_job, name="Require unit and integration lanes to pass")
    assert "UNIT_RESULT" in fan_in_gate["run"]
    assert "INTEGRATION_RESULT" in fan_in_gate["run"]
    badge_step = _workflow_step(job=check_job, name="Update coverage badge")
    assert badge_step["if"] == "github.ref == 'refs/heads/main' && github.event_name == 'push'"

    artifact_steps = {
        step["with"]["name"]: step
        for job in (unit_job, integration_job, check_job)
        for step in job["steps"]
        if step.get("uses") == "actions/upload-artifact@v4"
    }
    assert {
        "ci-unit-test-evidence",
        "ci-unit-coverage-data",
        "ci-smoke-test-evidence",
        "ci-integration-test-evidence",
        "ci-integration-coverage-data",
        "ci-combined-coverage-report",
    } <= artifact_steps.keys()
    for artifact_name in (
        "ci-unit-test-evidence",
        "ci-unit-coverage-data",
        "smoke-release-evidence",
        "ci-smoke-test-evidence",
        "ci-integration-test-evidence",
        "ci-integration-coverage-data",
        "ci-combined-coverage-report",
    ):
        assert artifact_steps[artifact_name]["with"]["overwrite"] is True

    for job, artifact_name in (
        (unit_job, "ci-unit-test-evidence"),
        (integration_job, "ci-integration-test-evidence"),
    ):
        evidence_step = next(
            step
            for step in job["steps"]
            if step.get("uses") == "actions/upload-artifact@v4"
            and step["with"]["name"] == artifact_name
        )
        assert evidence_step["if"] == "always()"
        assert evidence_step["with"]["retention-days"] == 14
        assert ".tmp" not in evidence_step["with"]["path"]
        assert "raw-junit.xml" not in evidence_step["with"]["path"]

    for source_job, artifact_name, suffix, download_step_name, download_suffix in (
        (
            unit_job,
            "ci-unit-coverage-data",
            "ci-coverage/coverage-unit.data",
            "Download unit coverage data",
            "ci-coverage/unit",
        ),
        (
            integration_job,
            "ci-integration-coverage-data",
            "ci-coverage/coverage-integration.data",
            "Download integration coverage data",
            "ci-coverage/integration",
        ),
    ):
        coverage_upload = next(
            step
            for step in source_job["steps"]
            if step.get("uses") == "actions/upload-artifact@v4"
            and step["with"]["name"] == artifact_name
        )
        assert coverage_upload["if"] == "always()"
        assert coverage_upload["with"]["path"].endswith(suffix)
        assert coverage_upload["with"]["if-no-files-found"] == "error"

        coverage_download = _workflow_step(job=check_job, name=download_step_name)
        assert coverage_download["uses"] == "actions/download-artifact@v4"
        assert coverage_download["with"]["name"] == artifact_name
        assert coverage_download["with"]["path"].endswith(download_suffix)

    smoke_step = _workflow_step(job=unit_job, name="Smoke tests (fast gate + release evidence)")
    assert smoke_step["env"]["TESTCONTAINERS_RYUK_DISABLED"] == "true"
    assert smoke_step["env"]["SMOKE_EVIDENCE_DIR"].endswith("ci-artifacts/smoke")
    assert "--durations" not in smoke_step["run"]
    assert "except (ET.ParseError, OSError) as exc:" in smoke_step["run"]
    assert "print(exc, file=sys.stderr)" in smoke_step["run"]

    smoke_artifact = _workflow_step(job=unit_job, name="Upload smoke release evidence")
    assert smoke_artifact["with"]["name"] == "smoke-release-evidence"
    assert ".tmp" not in smoke_artifact["with"]["path"]
