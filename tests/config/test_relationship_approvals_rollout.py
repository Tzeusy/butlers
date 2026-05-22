"""Relationship roster wiring for owner-gated approval actions."""

from __future__ import annotations

from pathlib import Path

from butlers.config import load_config

REPO_ROOT = Path(__file__).resolve().parents[2]
RELATIONSHIP_DIR = REPO_ROOT / "roster" / "relationship"


def test_relationship_butler_loads_with_approvals_module() -> None:
    """The relationship config must load with approvals enabled as a module."""
    cfg = load_config(RELATIONSHIP_DIR)

    assert "approvals" in cfg.modules


def test_relationship_approvals_module_exposes_action_queue_tools() -> None:
    """Owner-gated relationship writes depend on the pending_actions queue."""
    cfg = load_config(RELATIONSHIP_DIR)
    approvals = cfg.modules.get("approvals")

    assert isinstance(approvals, dict), (
        "relationship owner-gated tools write pending_actions, so the approvals "
        "module must be present to run the pending_actions migration"
    )
    assert "actions" in approvals.get("groups", []), (
        "relationship approvals should expose action queue tools so parked "
        "owner mutations can be reviewed"
    )
