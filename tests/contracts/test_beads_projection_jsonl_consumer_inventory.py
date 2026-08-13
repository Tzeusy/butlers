"""Static contracts for the planning-only Beads projection retirement boundary.

RFC 0007 Amendment 2 ships an allowlisted JSONL-backed Bead detail route.
The Decisions-only projection packet must not silently make that distinct
consumer eligible for JSONL retirement.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.contract

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _read(relative_path: str) -> str:
    return (_REPO_ROOT / relative_path).read_text(encoding="utf-8")


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
