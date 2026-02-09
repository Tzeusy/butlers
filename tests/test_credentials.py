"""Tests for credential validation with aggregated error reporting."""

from __future__ import annotations

import logging

import pytest

from butlers.credentials import CredentialError, validate_credentials

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Env vars used across tests.  Every test that isn't specifically testing for
# the absence of ANTHROPIC_API_KEY must set it via monkeypatch.
_ANTHROPIC_KEY = "ANTHROPIC_API_KEY"


def _set_anthropic_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure ANTHROPIC_API_KEY is present so it doesn't cause spurious failures."""
    monkeypatch.setenv(_ANTHROPIC_KEY, "sk-test-key")


# ---------------------------------------------------------------------------
# Happy-path
# ---------------------------------------------------------------------------


def test_all_present(monkeypatch: pytest.MonkeyPatch):
    """No error when every required variable is set."""
    _set_anthropic_key(monkeypatch)
    monkeypatch.setenv("PG_DSN", "postgres://localhost/test")
    monkeypatch.setenv("EMAIL_PASS", "secret")

    # Should not raise
    validate_credentials(
        env_required=["PG_DSN"],
        env_optional=[],
        module_credentials={"email": ["EMAIL_PASS"]},
    )


# ---------------------------------------------------------------------------
# Missing core credential
# ---------------------------------------------------------------------------


def test_missing_anthropic_key(monkeypatch: pytest.MonkeyPatch):
    """Missing ANTHROPIC_API_KEY raises CredentialError."""
    monkeypatch.delenv(_ANTHROPIC_KEY, raising=False)

    with pytest.raises(CredentialError, match="ANTHROPIC_API_KEY"):
        validate_credentials(env_required=[], env_optional=[])


# ---------------------------------------------------------------------------
# Missing butler.env required
# ---------------------------------------------------------------------------


def test_missing_butler_env_required(monkeypatch: pytest.MonkeyPatch):
    """Missing butler.env required var raises CredentialError."""
    _set_anthropic_key(monkeypatch)
    monkeypatch.delenv("PG_DSN", raising=False)

    with pytest.raises(CredentialError, match="PG_DSN"):
        validate_credentials(env_required=["PG_DSN"], env_optional=[])


# ---------------------------------------------------------------------------
# Missing module credentials
# ---------------------------------------------------------------------------


def test_missing_module_credentials(monkeypatch: pytest.MonkeyPatch):
    """Missing module credential raises CredentialError."""
    _set_anthropic_key(monkeypatch)
    monkeypatch.delenv("TG_BOT_TOKEN", raising=False)

    with pytest.raises(CredentialError, match="TG_BOT_TOKEN"):
        validate_credentials(
            env_required=[],
            env_optional=[],
            module_credentials={"telegram": ["TG_BOT_TOKEN"]},
        )


# ---------------------------------------------------------------------------
# Multiple missing — aggregated report
# ---------------------------------------------------------------------------


def test_multiple_missing_aggregated(monkeypatch: pytest.MonkeyPatch):
    """All missing vars are reported in a single CredentialError."""
    monkeypatch.delenv(_ANTHROPIC_KEY, raising=False)
    monkeypatch.delenv("PG_DSN", raising=False)
    monkeypatch.delenv("EMAIL_PASS", raising=False)

    with pytest.raises(CredentialError) as exc_info:
        validate_credentials(
            env_required=["PG_DSN"],
            env_optional=[],
            module_credentials={"email": ["EMAIL_PASS"]},
        )

    msg = str(exc_info.value)
    assert "ANTHROPIC_API_KEY" in msg
    assert "PG_DSN" in msg
    assert "EMAIL_PASS" in msg


# ---------------------------------------------------------------------------
# Optional vars
# ---------------------------------------------------------------------------


def test_optional_missing_warns(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture):
    """Missing optional var produces a warning but no error."""
    _set_anthropic_key(monkeypatch)
    monkeypatch.delenv("SLACK_TOKEN", raising=False)

    with caplog.at_level(logging.WARNING, logger="butlers.credentials"):
        validate_credentials(env_required=[], env_optional=["SLACK_TOKEN"])

    assert any("SLACK_TOKEN" in record.message for record in caplog.records)


def test_optional_present_no_warning(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    """Present optional var produces no warning."""
    _set_anthropic_key(monkeypatch)
    monkeypatch.setenv("SLACK_TOKEN", "xoxb-test")

    with caplog.at_level(logging.WARNING, logger="butlers.credentials"):
        validate_credentials(env_required=[], env_optional=["SLACK_TOKEN"])

    assert not any("SLACK_TOKEN" in record.message for record in caplog.records)


# ---------------------------------------------------------------------------
# Error message identifies sources
# ---------------------------------------------------------------------------


def test_error_message_identifies_sources(monkeypatch: pytest.MonkeyPatch):
    """Error message names the source component for each missing variable."""
    monkeypatch.delenv(_ANTHROPIC_KEY, raising=False)
    monkeypatch.delenv("PG_DSN", raising=False)
    monkeypatch.delenv("TG_TOKEN", raising=False)

    with pytest.raises(CredentialError) as exc_info:
        validate_credentials(
            env_required=["PG_DSN"],
            env_optional=[],
            module_credentials={"telegram": ["TG_TOKEN"]},
        )

    msg = str(exc_info.value)
    assert "required by core" in msg
    assert "required by butler.env" in msg
    assert "required by module:telegram" in msg
