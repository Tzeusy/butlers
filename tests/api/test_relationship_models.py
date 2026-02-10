"""Tests for relationship/CRM Pydantic models."""

from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import uuid4

import pytest

from butlers.api.models.relationship import (
    ContactDetail,
    ContactListResponse,
    ContactSummary,
    Gift,
    Group,
    GroupListResponse,
    Interaction,
    Label,
    Loan,
    Note,
    UpcomingDate,
)

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Label
# ---------------------------------------------------------------------------


class TestLabel:
    def test_full(self):
        lid = uuid4()
        label = Label(id=lid, name="Family", color="#ff0000")
        assert label.id == lid
        assert label.name == "Family"
        assert label.color == "#ff0000"

    def test_color_optional(self):
        label = Label(id=uuid4(), name="Work")
        assert label.color is None

    def test_json_round_trip(self):
        label = Label(id=uuid4(), name="VIP", color="#00ff00")
        restored = Label.model_validate_json(label.model_dump_json())
        assert restored.name == label.name
        assert restored.color == label.color
        assert restored.id == label.id


# ---------------------------------------------------------------------------
# ContactSummary
# ---------------------------------------------------------------------------


class TestContactSummary:
    def test_full(self):
        cid = uuid4()
        now = datetime.now(tz=UTC)
        label = Label(id=uuid4(), name="Friend", color="#0000ff")
        c = ContactSummary(
            id=cid,
            full_name="Jane Doe",
            nickname="Janie",
            email="jane@example.com",
            phone="+1234567890",
            labels=[label],
            last_interaction_at=now,
        )
        assert c.id == cid
        assert c.full_name == "Jane Doe"
        assert c.nickname == "Janie"
        assert c.email == "jane@example.com"
        assert c.phone == "+1234567890"
        assert len(c.labels) == 1
        assert c.labels[0].name == "Friend"
        assert c.last_interaction_at == now

    def test_minimal_with_defaults(self):
        c = ContactSummary(id=uuid4(), full_name="John Doe")
        assert c.nickname is None
        assert c.email is None
        assert c.phone is None
        assert c.labels == []
        assert c.last_interaction_at is None

    def test_json_round_trip(self):
        c = ContactSummary(
            id=uuid4(),
            full_name="Alice",
            email="alice@example.com",
        )
        restored = ContactSummary.model_validate_json(c.model_dump_json())
        assert restored.full_name == "Alice"
        assert restored.email == "alice@example.com"
        assert restored.id == c.id

    def test_rejects_missing_required(self):
        with pytest.raises(Exception):
            ContactSummary(id=uuid4())  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# ContactDetail
# ---------------------------------------------------------------------------


class TestContactDetail:
    def test_full(self):
        cid = uuid4()
        now = datetime.now(tz=UTC)
        c = ContactDetail(
            id=cid,
            full_name="Bob Smith",
            nickname="Bobby",
            email="bob@example.com",
            phone="+9876543210",
            notes="Met at conference",
            birthday=date(1990, 5, 15),
            company="Acme Corp",
            job_title="Engineer",
            address="123 Main St",
            metadata={"source": "linkedin"},
            created_at=now,
            updated_at=now,
        )
        assert c.full_name == "Bob Smith"
        assert c.birthday == date(1990, 5, 15)
        assert c.company == "Acme Corp"
        assert c.metadata == {"source": "linkedin"}
        assert c.created_at == now

    def test_inherits_summary_defaults(self):
        now = datetime.now(tz=UTC)
        c = ContactDetail(
            id=uuid4(),
            full_name="Minimal Contact",
            created_at=now,
            updated_at=now,
        )
        assert c.nickname is None
        assert c.email is None
        assert c.labels == []
        assert c.notes is None
        assert c.birthday is None
        assert c.metadata == {}

    def test_json_round_trip(self):
        now = datetime.now(tz=UTC)
        c = ContactDetail(
            id=uuid4(),
            full_name="Round Trip",
            birthday=date(1985, 12, 25),
            metadata={"key": "value"},
            created_at=now,
            updated_at=now,
        )
        restored = ContactDetail.model_validate_json(c.model_dump_json())
        assert restored.full_name == c.full_name
        assert restored.birthday == c.birthday
        assert restored.metadata == c.metadata

    def test_model_dump_keys(self):
        now = datetime.now(tz=UTC)
        c = ContactDetail(
            id=uuid4(),
            full_name="Keys Test",
            created_at=now,
            updated_at=now,
        )
        keys = set(c.model_dump().keys())
        assert "full_name" in keys
        assert "created_at" in keys
        assert "metadata" in keys
        assert "labels" in keys
        # Inherited from ContactSummary
        assert "email" in keys
        assert "phone" in keys


# ---------------------------------------------------------------------------
# Group
# ---------------------------------------------------------------------------


class TestGroup:
    def test_full(self):
        gid = uuid4()
        now = datetime.now(tz=UTC)
        label = Label(id=uuid4(), name="Work")
        g = Group(
            id=gid,
            name="College Friends",
            description="Friends from university",
            member_count=12,
            labels=[label],
            created_at=now,
            updated_at=now,
        )
        assert g.id == gid
        assert g.name == "College Friends"
        assert g.description == "Friends from university"
        assert g.member_count == 12
        assert len(g.labels) == 1
        assert g.created_at == now

    def test_defaults(self):
        now = datetime.now(tz=UTC)
        g = Group(id=uuid4(), name="Empty Group", created_at=now, updated_at=now)
        assert g.description is None
        assert g.member_count == 0
        assert g.labels == []

    def test_json_round_trip(self):
        now = datetime.now(tz=UTC)
        g = Group(id=uuid4(), name="RT Group", created_at=now, updated_at=now)
        restored = Group.model_validate_json(g.model_dump_json())
        assert restored.name == "RT Group"
        assert restored.id == g.id


# ---------------------------------------------------------------------------
# Note
# ---------------------------------------------------------------------------


class TestNote:
    def test_full(self):
        nid = uuid4()
        cid = uuid4()
        now = datetime.now(tz=UTC)
        n = Note(
            id=nid,
            contact_id=cid,
            content="Likes hiking and coffee",
            created_at=now,
            updated_at=now,
        )
        assert n.id == nid
        assert n.contact_id == cid
        assert n.content == "Likes hiking and coffee"
        assert n.created_at == now

    def test_json_round_trip(self):
        now = datetime.now(tz=UTC)
        n = Note(
            id=uuid4(),
            contact_id=uuid4(),
            content="Test note",
            created_at=now,
            updated_at=now,
        )
        restored = Note.model_validate_json(n.model_dump_json())
        assert restored.content == "Test note"

    def test_rejects_missing_content(self):
        with pytest.raises(Exception):
            Note(
                id=uuid4(),
                contact_id=uuid4(),
                created_at=datetime.now(tz=UTC),
                updated_at=datetime.now(tz=UTC),
            )  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# Interaction
# ---------------------------------------------------------------------------


class TestInteraction:
    def test_full(self):
        iid = uuid4()
        cid = uuid4()
        now = datetime.now(tz=UTC)
        i = Interaction(
            id=iid,
            contact_id=cid,
            type="meeting",
            summary="Lunch meeting",
            details="Discussed project proposal",
            occurred_at=now,
            created_at=now,
        )
        assert i.id == iid
        assert i.contact_id == cid
        assert i.type == "meeting"
        assert i.summary == "Lunch meeting"
        assert i.details == "Discussed project proposal"
        assert i.occurred_at == now

    def test_details_optional(self):
        now = datetime.now(tz=UTC)
        i = Interaction(
            id=uuid4(),
            contact_id=uuid4(),
            type="call",
            summary="Quick call",
            occurred_at=now,
            created_at=now,
        )
        assert i.details is None

    def test_json_round_trip(self):
        now = datetime.now(tz=UTC)
        i = Interaction(
            id=uuid4(),
            contact_id=uuid4(),
            type="email",
            summary="Follow-up email",
            occurred_at=now,
            created_at=now,
        )
        restored = Interaction.model_validate_json(i.model_dump_json())
        assert restored.type == "email"
        assert restored.summary == "Follow-up email"


# ---------------------------------------------------------------------------
# Gift
# ---------------------------------------------------------------------------


class TestGift:
    def test_full(self):
        gid = uuid4()
        cid = uuid4()
        now = datetime.now(tz=UTC)
        g = Gift(
            id=gid,
            contact_id=cid,
            description="Bottle of wine",
            direction="given",
            occasion="Birthday",
            date=date(2026, 1, 15),
            value=45.00,
            created_at=now,
        )
        assert g.id == gid
        assert g.contact_id == cid
        assert g.description == "Bottle of wine"
        assert g.direction == "given"
        assert g.occasion == "Birthday"
        assert g.date == date(2026, 1, 15)
        assert g.value == 45.00

    def test_optional_defaults(self):
        now = datetime.now(tz=UTC)
        g = Gift(
            id=uuid4(),
            contact_id=uuid4(),
            description="Book",
            direction="received",
            date=date(2026, 2, 1),
            created_at=now,
        )
        assert g.occasion is None
        assert g.value is None

    def test_json_round_trip(self):
        now = datetime.now(tz=UTC)
        g = Gift(
            id=uuid4(),
            contact_id=uuid4(),
            description="Watch",
            direction="given",
            date=date(2026, 3, 10),
            value=200.0,
            created_at=now,
        )
        restored = Gift.model_validate_json(g.model_dump_json())
        assert restored.description == "Watch"
        assert restored.value == 200.0


# ---------------------------------------------------------------------------
# Loan
# ---------------------------------------------------------------------------


class TestLoan:
    def test_full(self):
        lid = uuid4()
        cid = uuid4()
        now = datetime.now(tz=UTC)
        loan = Loan(
            id=lid,
            contact_id=cid,
            description="Moving truck rental",
            direction="lent",
            amount=150.00,
            currency="EUR",
            status="active",
            date=date(2026, 1, 10),
            due_date=date(2026, 2, 10),
            created_at=now,
        )
        assert loan.id == lid
        assert loan.direction == "lent"
        assert loan.amount == 150.00
        assert loan.currency == "EUR"
        assert loan.status == "active"
        assert loan.due_date == date(2026, 2, 10)

    def test_defaults(self):
        now = datetime.now(tz=UTC)
        loan = Loan(
            id=uuid4(),
            contact_id=uuid4(),
            description="Coffee money",
            direction="borrowed",
            amount=5.00,
            date=date(2026, 2, 5),
            created_at=now,
        )
        assert loan.currency == "USD"
        assert loan.status == "active"
        assert loan.due_date is None

    def test_json_round_trip(self):
        now = datetime.now(tz=UTC)
        loan = Loan(
            id=uuid4(),
            contact_id=uuid4(),
            description="Laptop",
            direction="lent",
            amount=1000.0,
            date=date(2026, 1, 1),
            created_at=now,
        )
        restored = Loan.model_validate_json(loan.model_dump_json())
        assert restored.description == "Laptop"
        assert restored.amount == 1000.0
        assert restored.currency == "USD"


# ---------------------------------------------------------------------------
# UpcomingDate
# ---------------------------------------------------------------------------


class TestUpcomingDate:
    def test_full(self):
        cid = uuid4()
        ud = UpcomingDate(
            contact_id=cid,
            contact_name="Jane Doe",
            date_type="birthday",
            date=date(2026, 3, 15),
            days_until=33,
        )
        assert ud.contact_id == cid
        assert ud.contact_name == "Jane Doe"
        assert ud.date_type == "birthday"
        assert ud.date == date(2026, 3, 15)
        assert ud.days_until == 33

    def test_json_round_trip(self):
        ud = UpcomingDate(
            contact_id=uuid4(),
            contact_name="Bob",
            date_type="anniversary",
            date=date(2026, 6, 1),
            days_until=111,
        )
        restored = UpcomingDate.model_validate_json(ud.model_dump_json())
        assert restored.contact_name == "Bob"
        assert restored.date_type == "anniversary"
        assert restored.days_until == 111


# ---------------------------------------------------------------------------
# ContactListResponse
# ---------------------------------------------------------------------------


class TestContactListResponse:
    def test_empty(self):
        r = ContactListResponse(contacts=[], total=0)
        assert r.contacts == []
        assert r.total == 0

    def test_with_contacts(self):
        c1 = ContactSummary(id=uuid4(), full_name="Alice")
        c2 = ContactSummary(id=uuid4(), full_name="Bob")
        r = ContactListResponse(contacts=[c1, c2], total=2)
        assert len(r.contacts) == 2
        assert r.total == 2

    def test_json_round_trip(self):
        c = ContactSummary(id=uuid4(), full_name="Charlie")
        r = ContactListResponse(contacts=[c], total=1)
        restored = ContactListResponse.model_validate_json(r.model_dump_json())
        assert len(restored.contacts) == 1
        assert restored.contacts[0].full_name == "Charlie"


# ---------------------------------------------------------------------------
# GroupListResponse
# ---------------------------------------------------------------------------


class TestGroupListResponse:
    def test_empty(self):
        r = GroupListResponse(groups=[], total=0)
        assert r.groups == []
        assert r.total == 0

    def test_with_groups(self):
        now = datetime.now(tz=UTC)
        g = Group(id=uuid4(), name="Team", created_at=now, updated_at=now)
        r = GroupListResponse(groups=[g], total=1)
        assert len(r.groups) == 1
        assert r.total == 1


# ---------------------------------------------------------------------------
# Re-exports from models package
# ---------------------------------------------------------------------------


class TestModelsReExport:
    def test_label_importable(self):
        from butlers.api.models import Label as L

        assert L is Label

    def test_contact_summary_importable(self):
        from butlers.api.models import ContactSummary as CS

        assert CS is ContactSummary

    def test_contact_detail_importable(self):
        from butlers.api.models import ContactDetail as CD

        assert CD is ContactDetail

    def test_group_importable(self):
        from butlers.api.models import Group as G

        assert G is Group

    def test_gift_importable(self):
        from butlers.api.models import Gift as Gi

        assert Gi is Gift

    def test_loan_importable(self):
        from butlers.api.models import Loan as Lo

        assert Lo is Loan

    def test_interaction_importable(self):
        from butlers.api.models import Interaction as I

        assert I is Interaction

    def test_note_importable(self):
        from butlers.api.models import Note as N

        assert N is Note

    def test_upcoming_date_importable(self):
        from butlers.api.models import UpcomingDate as UD

        assert UD is UpcomingDate
