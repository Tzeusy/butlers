"""Pydantic models for the secrets CRUD API.

These models enforce the no-value-in-response security contract: secret values
are accepted as input (PUT body) but never returned in any response.  Responses
carry only metadata plus an ``is_set`` boolean that indicates whether the secret
currently has a non-empty value.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Response models — values NEVER included
# ---------------------------------------------------------------------------


class SecretEntry(BaseModel):
    """Metadata for a single secret.  Raw values are never exposed.

    Attributes
    ----------
    key:
        The unique secret name (e.g. ``"BUTLER_TELEGRAM_TOKEN"``).
    category:
        Grouping label used by the dashboard (e.g. ``"telegram"``).
    description:
        Optional human-readable label for display in the dashboard.
    is_sensitive:
        When ``True``, the raw value must be masked in UI and log output.
    is_set:
        ``True`` if the secret has a non-empty value stored.  The raw value
        is never included — callers can only learn *whether* it is set.
    created_at:
        When the secret was first stored.
    updated_at:
        When the secret was last updated.
    expires_at:
        Optional expiry timestamp.  ``None`` means the secret never expires.
    source:
        Where the value was resolved from: ``"database"`` or ``"environment"``.
    """

    key: str
    category: str = "general"
    description: str | None = None
    is_sensitive: bool = True
    is_set: bool
    created_at: datetime
    updated_at: datetime
    expires_at: datetime | None = None
    source: str = "database"


# ---------------------------------------------------------------------------
# Request models — value accepted on write, never echoed back
# ---------------------------------------------------------------------------


class SecretUpsertRequest(BaseModel):
    """Request body for creating or updating a secret (PUT).

    The ``value`` field is required for creating/updating a secret.  It is
    write-only: it is accepted here but never included in any response model.

    All other fields are optional and default to existing values on update.
    """

    value: str = Field(
        ...,
        description="The secret value.  Write-only — never returned in responses.",
        min_length=1,
    )
    category: str = Field(default="general", description="Grouping label for dashboard display.")
    description: str | None = Field(default=None, description="Human-readable label.")
    is_sensitive: bool = Field(
        default=True,
        description="When true, mask the value in UI and logs.",
    )
    expires_at: datetime | None = Field(
        default=None,
        description="Optional expiry time.  None means the secret never expires.",
    )
