"""Unit coverage for finance transaction account-label resolution."""

from __future__ import annotations

import uuid

import pytest

from butlers.tools.finance.transactions import _unique_account_match


def _account_row(
    *,
    institution: str = "Example Bank",
    account_type: str = "credit",
    name: str = "Example Rewards",
    last_four: str = "4321",
) -> dict[str, object]:
    return {
        "id": uuid.uuid4(),
        "institution": institution,
        "type": account_type,
        "name": name,
        "last_four": last_four,
    }


def test_slugged_composite_label_matches_account_columns() -> None:
    """The MCP-documented slug form resolves across separately stored fields."""
    row = _account_row()

    result = _unique_account_match([row], "example-bank-card-4321")

    assert result == str(row["id"])


def test_composite_label_without_last_four_matches_unique_account() -> None:
    """The short institution/type example advertised by the MCP tool remains valid."""
    row = _account_row(account_type="checking", last_four="9876")

    result = _unique_account_match([row], "example-bank-checking")

    assert result == str(row["id"])


def test_composite_label_rejects_ambiguous_accounts() -> None:
    """A shared institution/type label never selects an arbitrary account."""
    rows = [_account_row(last_four="1111"), _account_row(last_four="2222")]

    with pytest.raises(ValueError, match="ambiguous"):
        _unique_account_match(rows, "example-bank-card")
