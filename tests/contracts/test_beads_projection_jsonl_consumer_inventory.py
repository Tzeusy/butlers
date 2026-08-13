"""Static contracts for the planning-only Beads projection retirement boundary.

RFC 0007 Amendment 2 ships an allowlisted JSONL-backed Bead detail route.
The Decisions-only projection packet must not silently make that distinct
consumer eligible for JSONL retirement.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.contract

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _read(relative_path: str) -> str:
    return (_REPO_ROOT / relative_path).read_text(encoding="utf-8")


def _normalise(text: str) -> str:
    return " ".join(text.split())


def _requirement_preamble(text: str, title: str) -> str:
    """Return one requirement's prose through its first scenario heading."""
    match = re.search(rf"^### Requirement: {re.escape(title)}$", text, re.MULTILINE)
    assert match is not None, f"missing requirement: {title}"

    next_requirement = text.find("\n### Requirement:", match.end())
    requirement = text[match.end() : next_requirement if next_requirement != -1 else None]
    first_scenario = requirement.find("\n#### Scenario:")
    assert first_scenario != -1, f"{title}: no scenario"
    return requirement[:first_scenario].rstrip()


def _assert_contiguous_traceability(
    text: str,
    *,
    title: str,
    requirement_id: str,
    source: str,
) -> None:
    """Require ID/Source/Scope directly between normative prose and scenarios."""
    expected = f"ID: {requirement_id}\nSource: {source}\nScope: v1-mandatory"
    assert _requirement_preamble(text, title).endswith(expected), (
        f"{title}: require contiguous ID, Source, Scope metadata before scenarios"
    )


def test_current_bead_detail_is_a_distinct_jsonl_consumer() -> None:
    """REQ-beads-projection-005: retain detail until it has its own safe migration."""
    route = _read("src/butlers/api/routers/beads.py")
    reader = _read("src/butlers/beads_snapshot.py")
    detail_contract = _read("docs/frontend/backend-api-contract.md")
    projection_spec = _read(
        "openspec/changes/beads-projection-exporter/specs/beads-projection/spec.md"
    )

    assert "BeadSnapshotReader" in route
    assert "return BeadSnapshotReader()" in route
    assert "design=record.design" in reader
    assert "acceptance_criteria=record.acceptance_criteria" in reader
    assert "`GET /api/beads/{id}`" in detail_contract
    assert "`design`" in detail_contract
    assert "`acceptance_criteria`" in detail_contract
    assert "source description only for an eligible non-epic" in projection_spec


def test_retirement_packet_requires_a_complete_jsonl_consumer_inventory() -> None:
    """REQ-beads-projection-005: every JSONL consumer has a proven disposition."""
    required_contract = (
        "complete JSONL consumer inventory",
        "migrated with contract and regression proof",
        "explicitly retained",
        "separately scoped security review",
    )
    planning_artifacts = (
        "about/legends-and-lore/rfcs/0023-tracker-host-beads-projection-exporter.md",
        "docs/architecture/beads-runtime-data-bridge.md",
        "docs/superpowers/plans/2026-08-13-beads-projection-exporter.md",
        "openspec/changes/beads-projection-exporter/design.md",
        "openspec/changes/beads-projection-exporter/specs/beads-projection/spec.md",
        "openspec/changes/beads-projection-exporter/tasks.md",
    )

    for relative_path in planning_artifacts:
        text = " ".join(_read(relative_path).split())
        assert "`GET /api/beads/{id}`" in text, relative_path
        assert "BeadSnapshotReader" in text, relative_path
        for required_text in required_contract:
            assert required_text in text, f"{relative_path}: {required_text}"


def test_projection_requirement_traceability_is_contiguous() -> None:
    """REQ-beads-projection-001 through -006 remain mechanically traceable."""
    projection_spec = _read(
        "openspec/changes/beads-projection-exporter/specs/beads-projection/spec.md"
    )
    requirements = (
        (
            "Tracker-Host Export Boundary and Minimal Active Projection",
            "REQ-beads-projection-001",
            "RFC 0023 §§1-2, 10",
        ),
        (
            "Atomic Complete Snapshot Publication and Retention",
            "REQ-beads-projection-002",
            "RFC 0023 §§3-4",
        ),
        (
            "Bounded Atomic BeadReadProvider and Freshness Classification",
            "REQ-beads-projection-003",
            "RFC 0023 §§5-6",
        ),
        (
            "Preserved Decision Lint and Dependency Semantics",
            "REQ-beads-projection-004",
            "RFC 0023 §7",
        ),
        (
            "Shadow Parity, Explicit Cutover, and Explicit JSONL Rollback",
            "REQ-beads-projection-006",
            "RFC 0023 §8",
        ),
        (
            "JSONL Consumer Inventory Gates Retirement",
            "REQ-beads-projection-005",
            "RFC 0023 §9; RFC 0007 Amendment 2",
        ),
    )

    for title, requirement_id, source in requirements:
        _assert_contiguous_traceability(
            projection_spec,
            title=title,
            requirement_id=requirement_id,
            source=source,
        )


def test_modified_dashboard_requirements_have_contiguous_traceability() -> None:
    """REQ-dashboard-api-001 and REQ-dashboard-decisions-001 remain traceable."""
    _assert_contiguous_traceability(
        _read("openspec/changes/beads-projection-exporter/specs/dashboard-api/spec.md"),
        title="Decisions Digest Endpoint",
        requirement_id="REQ-dashboard-api-001",
        source="RFC 0023 §§5-8; RFC 0007",
    )
    _assert_contiguous_traceability(
        _read("openspec/changes/beads-projection-exporter/specs/dashboard-decisions/spec.md"),
        title="Export As-Of Plaque",
        requirement_id="REQ-dashboard-decisions-001",
        source="RFC 0023 §§5-8; RFC 0007",
    )


def test_projection_contract_keeps_tracker_authority_and_derived_jsonl_role() -> None:
    """REQ-beads-projection-001: only Beads/Dolt is tracker authority."""
    rfc = _read("about/legends-and-lore/rfcs/0023-tracker-host-beads-projection-exporter.md")
    projection_spec = _read(
        "openspec/changes/beads-projection-exporter/specs/beads-projection/spec.md"
    )
    proposal = _read("openspec/changes/beads-projection-exporter/proposal.md")

    required = (
        "sole authoritative tracker",
        "derived compatibility and rollback path",
    )
    for text in map(_normalise, (rfc, projection_spec, proposal)):
        for phrase in required:
            assert phrase in text


def test_projection_tls_policy_and_bounds_fail_closed_in_the_plan() -> None:
    """REQ-beads-projection-001: verified transport and bounded candidates are planned."""
    rfc = _read("about/legends-and-lore/rfcs/0023-tracker-host-beads-projection-exporter.md")
    projection_spec = _read(
        "openspec/changes/beads-projection-exporter/specs/beads-projection/spec.md"
    )
    tasks = _read("openspec/changes/beads-projection-exporter/tasks.md")

    bounds = (
        "MAX_BEAD_ID_CHARS = 128",
        "MAX_ISSUE_TITLE_CHARS = 512",
        "MAX_STATUS_CHARS = 16",
        "MAX_ISSUE_TYPE_CHARS = 64",
        "MAX_TIMESTAMP_CHARS = 64",
        "MAX_LABELS_PER_ISSUE = 32",
        "MAX_LABEL_CHARS = 128",
        "MAX_DECISION_DESCRIPTION_CHARS = 16_384",
        "MAX_OPTIONS_PER_DECISION = 16",
        "MAX_DECISION_OPTION_CHARS = 512",
        "MAX_DEPENDENCY_TYPE_CHARS = 64",
        "MAX_LINT_CATEGORY_CODE_CHARS = 64",
        "MAX_CATEGORICAL_REASON_CHARS = 128",
        "MAX_PRODUCER_VERSION_CHARS = 64",
        "MAX_SNAPSHOT_ISSUES = 10_000",
        "MAX_SNAPSHOT_DEPENDENCY_EDGES = 25_000",
        "MAX_SNAPSHOT_LINT_VIOLATIONS = 1_000",
    )
    for text in map(_normalise, (rfc, projection_spec)):
        for bound in bounds:
            assert bound in text
        assert "reject the entire candidate snapshot" in text
        assert "field_bound_exceeded" in text
        assert "active pointer unchanged" in text

    tls_requirements = (
        "sslmode=verify-full",
        "trusted CA bundle",
        "hostname verification",
        "TLS 1.2 or newer",
        "fails closed",
    )
    for text in map(_normalise, (rfc, projection_spec, tasks)):
        for requirement in tls_requirements:
            assert requirement in text

    assert "at-limit acceptance and bound-plus-one rejection" in tasks
    assert "migrated-PostgreSQL integration tests" in tasks
    assert "planning regression tests for each rejection" in tasks
    assert "unverified TLS mode" in tasks
