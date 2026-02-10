"""Tests for skill directory name validation (kebab-case)."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from butlers.core.skills import list_valid_skills

pytestmark = pytest.mark.unit


def test_list_valid_skills_empty_directory(tmp_path: Path) -> None:
    """When skills directory is empty, returns empty list."""
    skills = tmp_path / "skills"
    skills.mkdir()

    result = list_valid_skills(skills)
    assert result == []


def test_list_valid_skills_valid_kebab_case(tmp_path: Path) -> None:
    """Valid kebab-case skill names are returned."""
    skills = tmp_path / "skills"
    skills.mkdir()

    (skills / "email-send").mkdir()
    (skills / "calendar-check").mkdir()
    (skills / "simple").mkdir()
    (skills / "multi-word-skill").mkdir()

    result = list_valid_skills(skills)
    result_names = sorted([p.name for p in result])

    assert result_names == ["calendar-check", "email-send", "multi-word-skill", "simple"]


def test_list_valid_skills_invalid_names_skipped(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Invalid skill names are skipped and logged as warnings."""
    skills = tmp_path / "skills"
    skills.mkdir()

    # Valid names
    (skills / "valid-skill").mkdir()
    (skills / "another-valid").mkdir()

    # Invalid names
    (skills / "Invalid_Name").mkdir()  # Underscore
    (skills / "CamelCase").mkdir()  # Capital letters
    (skills / "123-starts-with-number").mkdir()  # Starts with number
    (skills / "has spaces").mkdir()  # Spaces
    (skills / "-starts-with-dash").mkdir()  # Starts with dash
    (skills / "ends-with-dash-").mkdir()  # Ends with dash
    (skills / "double--dash").mkdir()  # Double dash

    with caplog.at_level(logging.WARNING):
        result = list_valid_skills(skills)

    result_names = sorted([p.name for p in result])
    assert result_names == ["another-valid", "valid-skill"]

    # Check that warnings were logged for invalid names
    assert "Invalid_Name" in caplog.text
    assert "CamelCase" in caplog.text
    assert "123-starts-with-number" in caplog.text
    assert "has spaces" in caplog.text
    assert "-starts-with-dash" in caplog.text
    assert "ends-with-dash-" in caplog.text
    assert "double--dash" in caplog.text


def test_list_valid_skills_ignores_files(tmp_path: Path) -> None:
    """Files in the skills directory are ignored (not just directories)."""
    skills = tmp_path / "skills"
    skills.mkdir()

    (skills / "valid-skill").mkdir()
    (skills / "README.md").write_text("Some readme", encoding="utf-8")
    (skills / "another-file.txt").write_text("Content", encoding="utf-8")

    result = list_valid_skills(skills)
    result_names = [p.name for p in result]

    assert result_names == ["valid-skill"]


def test_list_valid_skills_edge_cases(tmp_path: Path) -> None:
    """Test edge cases for kebab-case validation."""
    skills = tmp_path / "skills"
    skills.mkdir()

    # Valid edge cases
    (skills / "a").mkdir()  # Single letter
    (skills / "a1").mkdir()  # Letter then number
    (skills / "skill-123").mkdir()  # Ends with numbers
    (skills / "a-b-c-d").mkdir()  # Multiple dashes

    result = list_valid_skills(skills)
    result_names = sorted([p.name for p in result])

    assert result_names == ["a", "a-b-c-d", "a1", "skill-123"]


def test_list_valid_skills_pattern_validation(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Verify the exact regex pattern: ^[a-z][a-z0-9]*(-[a-z0-9]+)*$"""
    skills = tmp_path / "skills"
    skills.mkdir()

    # These should be valid
    (skills / "a").mkdir()  # Single lowercase letter
    (skills / "abc").mkdir()  # Multiple lowercase letters
    (skills / "a123").mkdir()  # Letters then numbers
    (skills / "ab-cd").mkdir()  # Hyphen between segments
    (skills / "a-b-c").mkdir()  # Multiple hyphens
    (skills / "skill-123-test").mkdir()  # Numbers in segments

    # These should be invalid
    (skills / "A").mkdir()  # Uppercase
    (skills / "1").mkdir()  # Starts with number
    (skills / "-a").mkdir()  # Starts with hyphen
    (skills / "a-").mkdir()  # Ends with hyphen
    (skills / "a--b").mkdir()  # Double hyphen

    with caplog.at_level(logging.WARNING):
        result = list_valid_skills(skills)

    result_names = sorted([p.name for p in result])
    assert result_names == ["a", "a-b-c", "a123", "ab-cd", "abc", "skill-123-test"]
