"""State-specific Pydantic models.

Provides ``StateEntry`` for state read responses and ``StateSetRequest``
for the state write (PUT) endpoint.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class StateEntry(BaseModel):
    """A single key-value entry from the butler's state store."""

    key: str
    value: dict[str, Any]
    updated_at: datetime


class StateSetRequest(BaseModel):
    """Request body for setting a state value."""

    value: dict[str, Any]
