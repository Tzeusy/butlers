"""Tests for relationship/CRM API endpoints.

Verifies the API contract (status codes, response shapes) for relationship
endpoints.  These tests work against both the current placeholder endpoints
(which return empty collections) and future real implementations.
"""

from __future__ import annotations

import httpx
import pytest

from butlers.api.app import create_app

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _app():
    """Create a fresh FastAPI app with the relationship router included."""
    return create_app()


# ---------------------------------------------------------------------------
# GET /api/relationship/contacts
# ---------------------------------------------------------------------------


class TestListContacts:
    async def test_returns_contact_list_response_structure(self):
        """Response must have 'contacts' array and 'total' integer."""
        app = _app()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/relationship/contacts")

        assert resp.status_code == 200
        body = resp.json()
        assert "contacts" in body
        assert "total" in body
        assert isinstance(body["contacts"], list)
        assert isinstance(body["total"], int)

    async def test_search_param_accepted(self):
        """The ?q= query parameter must not cause an error."""
        app = _app()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/relationship/contacts", params={"q": "alice"})

        assert resp.status_code == 200

    async def test_label_filter_accepted(self):
        """The ?label= query parameter must not cause an error."""
        app = _app()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/relationship/contacts", params={"label": "family"})

        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# GET /api/relationship/contacts/{contact_id}
# ---------------------------------------------------------------------------


class TestGetContact:
    async def test_missing_contact_returns_404_or_empty(self):
        """A non-existent contact should return 404 or empty placeholder dict."""
        app = _app()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/relationship/contacts/00000000-0000-0000-0000-000000000000"
            )

        # Placeholder returns 200 with {}; real impl should return 404.
        assert resp.status_code in (200, 404)


# ---------------------------------------------------------------------------
# GET /api/relationship/groups
# ---------------------------------------------------------------------------


class TestListGroups:
    async def test_returns_group_list_response_structure(self):
        """Response must have 'groups' array and 'total' integer."""
        app = _app()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/relationship/groups")

        assert resp.status_code == 200
        body = resp.json()
        assert "groups" in body
        assert "total" in body
        assert isinstance(body["groups"], list)
        assert isinstance(body["total"], int)


# ---------------------------------------------------------------------------
# GET /api/relationship/labels
# ---------------------------------------------------------------------------


class TestListLabels:
    async def test_returns_list_of_labels(self):
        """Response must be a JSON array (each element a Label object)."""
        app = _app()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/relationship/labels")

        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)


# ---------------------------------------------------------------------------
# GET /api/relationship/upcoming-dates
# ---------------------------------------------------------------------------


class TestListUpcomingDates:
    async def test_returns_list_of_upcoming_dates(self):
        """Response must be a JSON array of UpcomingDate objects."""
        app = _app()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/relationship/upcoming-dates")

        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)

    async def test_days_param_accepted(self):
        """The ?days= query parameter must not cause an error."""
        app = _app()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/relationship/upcoming-dates", params={"days": 30}
            )

        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# GET /api/relationship/contacts/{contact_id}/notes
# ---------------------------------------------------------------------------


class TestListContactNotes:
    async def test_returns_list_of_notes(self):
        """Response must be a JSON array of Note objects (or 404 if not yet implemented)."""
        app = _app()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/relationship/contacts/00000000-0000-0000-0000-000000000000/notes"
            )

        # 404 acceptable when endpoint is not yet implemented; 200 with list when it is.
        if resp.status_code == 200:
            assert isinstance(resp.json(), list)
        else:
            assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/relationship/contacts/{contact_id}/interactions
# ---------------------------------------------------------------------------


class TestListContactInteractions:
    async def test_returns_list_of_interactions(self):
        """Response must be a JSON array of Interaction objects (or 404)."""
        app = _app()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/relationship/contacts/00000000-0000-0000-0000-000000000000/interactions"
            )

        if resp.status_code == 200:
            assert isinstance(resp.json(), list)
        else:
            assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/relationship/contacts/{contact_id}/gifts
# ---------------------------------------------------------------------------


class TestListContactGifts:
    async def test_returns_list_of_gifts(self):
        """Response must be a JSON array of Gift objects (or 404)."""
        app = _app()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/relationship/contacts/00000000-0000-0000-0000-000000000000/gifts"
            )

        if resp.status_code == 200:
            assert isinstance(resp.json(), list)
        else:
            assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/relationship/contacts/{contact_id}/loans
# ---------------------------------------------------------------------------


class TestListContactLoans:
    async def test_returns_list_of_loans(self):
        """Response must be a JSON array of Loan objects (or 404)."""
        app = _app()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/relationship/contacts/00000000-0000-0000-0000-000000000000/loans"
            )

        if resp.status_code == 200:
            assert isinstance(resp.json(), list)
        else:
            assert resp.status_code == 404
