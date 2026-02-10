"""Relationship/CRM endpoints.

Provides placeholder endpoints for contacts, groups, labels, and
upcoming dates.  These will be wired to the relationship butler's
MCP server in butlers-26h.10.2.
"""

from __future__ import annotations

from fastapi import APIRouter

from butlers.api.models.relationship import (
    ContactListResponse,
    GroupListResponse,
    Label,
    UpcomingDate,
)

router = APIRouter(prefix="/api/relationship", tags=["relationship"])


@router.get("/contacts", response_model=ContactListResponse)
async def list_contacts() -> ContactListResponse:
    """List all contacts. Placeholder — will be implemented in butlers-26h.10.2."""
    return ContactListResponse(contacts=[], total=0)


@router.get("/contacts/{contact_id}")
async def get_contact(contact_id: str) -> dict:
    """Get contact detail. Placeholder."""
    return {}


@router.get("/groups", response_model=GroupListResponse)
async def list_groups() -> GroupListResponse:
    """List all groups. Placeholder."""
    return GroupListResponse(groups=[], total=0)


@router.get("/labels", response_model=list[Label])
async def list_labels() -> list[Label]:
    """List all labels. Placeholder."""
    return []


@router.get("/upcoming-dates", response_model=list[UpcomingDate])
async def list_upcoming_dates() -> list[UpcomingDate]:
    """List upcoming important dates. Placeholder."""
    return []
