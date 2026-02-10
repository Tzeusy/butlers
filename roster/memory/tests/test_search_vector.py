"""Unit tests for search vector generation helpers."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

# Load the module directly from disk so we do not need the roster package
# installed as a proper Python package.
_MODULE_PATH = Path(__file__).resolve().parent.parent / "search_vector.py"
_spec = importlib.util.spec_from_file_location("search_vector", _MODULE_PATH)
assert _spec is not None and _spec.loader is not None
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

preprocess_text = _mod.preprocess_text
tsvector_sql = _mod.tsvector_sql
tsquery_sql = _mod.tsquery_sql
websearch_tsquery_sql = _mod.websearch_tsquery_sql
preprocess_search_query = _mod.preprocess_search_query
MAX_TEXT_BYTES = _mod.MAX_TEXT_BYTES
TS_CONFIG = _mod.TS_CONFIG

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# preprocess_text
# ---------------------------------------------------------------------------


class TestPreprocessText:
    """Tests for preprocess_text()."""

    def test_normal_text(self) -> None:
        """Normal text passes through with minimal changes."""
        result = preprocess_text("Hello world, this is a test.")
        assert result == "Hello world, this is a test."

    def test_none_returns_empty(self) -> None:
        """None input returns an empty string."""
        assert preprocess_text(None) == ""

    def test_empty_string_returns_empty(self) -> None:
        """Empty string input returns an empty string."""
        assert preprocess_text("") == ""

    def test_whitespace_only_returns_empty(self) -> None:
        """Whitespace-only input returns an empty string after strip."""
        assert preprocess_text("   \t\n  ") == ""

    def test_collapses_whitespace(self) -> None:
        """Multiple spaces, tabs, newlines collapse to single space."""
        result = preprocess_text("hello   world\t\tfoo\n\nbar")
        assert result == "hello world foo bar"

    def test_strips_leading_trailing_whitespace(self) -> None:
        """Leading/trailing whitespace is removed."""
        result = preprocess_text("  hello world  ")
        assert result == "hello world"

    def test_removes_nul_bytes(self) -> None:
        """NUL bytes are stripped from the text."""
        result = preprocess_text("hello\x00world")
        assert result == "helloworld"

    def test_special_characters_preserved(self) -> None:
        """Special characters (quotes, parens, etc.) are preserved."""
        text = """He said "it's (not) a bug" & filed issue #42 — really?!"""
        result = preprocess_text(text)
        assert result == text

    def test_unicode_preserved(self) -> None:
        """Unicode characters are preserved after preprocessing."""
        text = "cafe\u0301 \u00fc\u00f1\u00ee\u00e7\u00f6\u00f0\u00e9"
        result = preprocess_text(text)
        assert result == text

    def test_long_text_truncated(self) -> None:
        """Text longer than MAX_TEXT_BYTES is truncated."""
        # Create text that is definitely over 1 MB in UTF-8
        long_text = "a" * (MAX_TEXT_BYTES + 1000)
        result = preprocess_text(long_text)
        assert len(result.encode("utf-8")) <= MAX_TEXT_BYTES

    def test_long_text_under_limit_not_truncated(self) -> None:
        """Text just under the limit is not truncated."""
        text = "a" * (MAX_TEXT_BYTES - 1)
        result = preprocess_text(text)
        assert result == text

    def test_truncation_respects_codepoint_boundary(self) -> None:
        """Truncation does not break multi-byte Unicode characters."""
        # Each emoji is 4 bytes in UTF-8.  Fill to just over limit.
        emoji = "\U0001f600"  # grinning face
        count = MAX_TEXT_BYTES // 4 + 10  # slightly over limit
        long_text = emoji * count
        result = preprocess_text(long_text)
        # Must be valid UTF-8 (would raise on decode if broken)
        result.encode("utf-8")
        assert len(result.encode("utf-8")) <= MAX_TEXT_BYTES

    def test_backslash_preserved(self) -> None:
        """Backslashes in text are preserved."""
        result = preprocess_text(r"path\to\file")
        assert result == r"path\to\file"


# ---------------------------------------------------------------------------
# SQL expression helpers
# ---------------------------------------------------------------------------


class TestTsvectorSql:
    """Tests for tsvector_sql()."""

    def test_default_param(self) -> None:
        """Default parameter is $1."""
        assert tsvector_sql() == f"to_tsvector('{TS_CONFIG}', $1)"

    def test_custom_param(self) -> None:
        """Custom parameter is respected."""
        assert tsvector_sql("$3") == f"to_tsvector('{TS_CONFIG}', $3)"

    def test_config_is_english(self) -> None:
        """The text-search config should be 'english'."""
        assert TS_CONFIG == "english"


class TestTsquerySql:
    """Tests for tsquery_sql()."""

    def test_default_param(self) -> None:
        """Default parameter is $1."""
        assert tsquery_sql() == f"plainto_tsquery('{TS_CONFIG}', $1)"

    def test_custom_param(self) -> None:
        """Custom parameter is respected."""
        assert tsquery_sql("$2") == f"plainto_tsquery('{TS_CONFIG}', $2)"


class TestWebsearchTsquerySql:
    """Tests for websearch_tsquery_sql()."""

    def test_default_param(self) -> None:
        """Default parameter is $1."""
        assert websearch_tsquery_sql() == f"websearch_to_tsquery('{TS_CONFIG}', $1)"

    def test_custom_param(self) -> None:
        """Custom parameter is respected."""
        assert websearch_tsquery_sql("$4") == f"websearch_to_tsquery('{TS_CONFIG}', $4)"


# ---------------------------------------------------------------------------
# preprocess_search_query
# ---------------------------------------------------------------------------


class TestPreprocessSearchQuery:
    """Tests for preprocess_search_query()."""

    def test_normal_query(self) -> None:
        """Normal query passes through."""
        assert preprocess_search_query("find memory facts") == "find memory facts"

    def test_none_returns_empty(self) -> None:
        """None input returns empty string."""
        assert preprocess_search_query(None) == ""

    def test_empty_string_returns_empty(self) -> None:
        """Empty string returns empty string."""
        assert preprocess_search_query("") == ""

    def test_collapses_whitespace(self) -> None:
        """Whitespace is collapsed."""
        assert preprocess_search_query("hello   world") == "hello world"

    def test_strips_whitespace(self) -> None:
        """Leading/trailing whitespace is stripped."""
        assert preprocess_search_query("  hello  ") == "hello"

    def test_removes_nul_bytes(self) -> None:
        """NUL bytes are removed."""
        assert preprocess_search_query("test\x00query") == "testquery"

    def test_special_chars_preserved(self) -> None:
        """Special characters are preserved (tsquery functions handle them)."""
        query = '"exact phrase" -exclude OR alternative'
        result = preprocess_search_query(query)
        assert result == query
