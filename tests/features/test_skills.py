"""Tests for butler skills infrastructure (CLAUDE.md, AGENTS.md, skills dir)."""

from __future__ import annotations

from pathlib import Path

import pytest

from butlers.core.skills import (
    append_agents_md,
    get_skills_dir,
    read_agents_md,
    read_system_prompt,
    write_agents_md,
)

pytestmark = pytest.mark.unit

# ---------------------------------------------------------------------------
# 9.1 — read_system_prompt
# ---------------------------------------------------------------------------


def test_read_system_prompt_returns_file_content(tmp_path: Path) -> None:
    """When CLAUDE.md is present its content is returned as the system prompt."""
    (tmp_path / "CLAUDE.md").write_text("You are the mail butler.", encoding="utf-8")
    assert read_system_prompt(tmp_path, "mail") == "You are the mail butler."


def test_read_system_prompt_missing_file_returns_default(tmp_path: Path) -> None:
    """When CLAUDE.md does not exist, a default prompt containing the butler name is returned."""
    result = read_system_prompt(tmp_path, "jarvis")
    assert result == "You are the jarvis butler."


def test_read_system_prompt_empty_file_returns_default(tmp_path: Path) -> None:
    """When CLAUDE.md exists but is empty (or whitespace-only), the default prompt is returned."""
    (tmp_path / "CLAUDE.md").write_text("   \n  ", encoding="utf-8")
    result = read_system_prompt(tmp_path, "alfred")
    assert result == "You are the alfred butler."


# ---------------------------------------------------------------------------
# 9.1 — get_skills_dir
# ---------------------------------------------------------------------------


def test_get_skills_dir_exists(tmp_path: Path) -> None:
    """When skills/ exists, the path is returned."""
    skills = tmp_path / "skills"
    skills.mkdir()
    assert get_skills_dir(tmp_path) == skills


def test_get_skills_dir_missing(tmp_path: Path) -> None:
    """When skills/ does not exist, None is returned."""
    assert get_skills_dir(tmp_path) is None


def test_skills_directory_structure(tmp_path: Path) -> None:
    """Validates the expected skills/<name>/SKILL.md layout."""
    skills = tmp_path / "skills"
    skills.mkdir()
    (skills / "email-send").mkdir()
    (skills / "email-send" / "SKILL.md").write_text("# Email Send Skill", encoding="utf-8")
    (skills / "calendar-check").mkdir()
    (skills / "calendar-check" / "SKILL.md").write_text("# Calendar Check", encoding="utf-8")

    result = get_skills_dir(tmp_path)
    assert result is not None

    # Each subdirectory should contain a SKILL.md
    skill_dirs = sorted(p.name for p in result.iterdir() if p.is_dir())
    assert skill_dirs == ["calendar-check", "email-send"]
    for skill_name in skill_dirs:
        skill_md = result / skill_name / "SKILL.md"
        assert skill_md.is_file(), f"SKILL.md missing for skill {skill_name}"


# ---------------------------------------------------------------------------
# 9.2 — AGENTS.md read / write / append
# ---------------------------------------------------------------------------


def test_read_agents_md_present(tmp_path: Path) -> None:
    """When AGENTS.md exists, its content is returned."""
    (tmp_path / "AGENTS.md").write_text("# Agent Notes\nfoo", encoding="utf-8")
    assert read_agents_md(tmp_path) == "# Agent Notes\nfoo"


def test_read_agents_md_missing(tmp_path: Path) -> None:
    """When AGENTS.md is missing, an empty string is returned."""
    assert read_agents_md(tmp_path) == ""


def test_write_agents_md_creates_file(tmp_path: Path) -> None:
    """write_agents_md creates the file and persists content."""
    write_agents_md(tmp_path, "hello world")
    assert (tmp_path / "AGENTS.md").read_text(encoding="utf-8") == "hello world"


def test_write_agents_md_overwrites(tmp_path: Path) -> None:
    """write_agents_md replaces existing content entirely."""
    (tmp_path / "AGENTS.md").write_text("old stuff", encoding="utf-8")
    write_agents_md(tmp_path, "new stuff")
    assert (tmp_path / "AGENTS.md").read_text(encoding="utf-8") == "new stuff"


def test_append_agents_md_existing(tmp_path: Path) -> None:
    """append_agents_md adds to existing content without replacing it."""
    (tmp_path / "AGENTS.md").write_text("line1\n", encoding="utf-8")
    append_agents_md(tmp_path, "line2\n")
    assert (tmp_path / "AGENTS.md").read_text(encoding="utf-8") == "line1\nline2\n"


def test_append_agents_md_creates_file(tmp_path: Path) -> None:
    """append_agents_md creates the file when it does not exist."""
    append_agents_md(tmp_path, "first entry\n")
    assert (tmp_path / "AGENTS.md").read_text(encoding="utf-8") == "first entry\n"
