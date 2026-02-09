"""Tests for butlers.tools.relationship — personal CRM tools."""

from __future__ import annotations

import shutil
import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest

# Skip all tests in this module if Docker is not available
docker_available = shutil.which("docker") is not None
pytestmark = pytest.mark.skipif(not docker_available, reason="Docker not available")


def _unique_db_name() -> str:
    return f"test_{uuid.uuid4().hex[:12]}"


@pytest.fixture(scope="module")
def postgres_container():
    """Start a PostgreSQL container for the test module."""
    from testcontainers.postgres import PostgresContainer

    with PostgresContainer("postgres:16") as pg:
        yield pg


@pytest.fixture
async def pool(postgres_container):
    """Provision a fresh database with relationship tables and return a pool."""
    from butlers.db import Database

    db = Database(
        db_name=_unique_db_name(),
        host=postgres_container.get_container_host_ip(),
        port=int(postgres_container.get_exposed_port(5432)),
        user=postgres_container.username,
        password=postgres_container.password,
        min_pool_size=1,
        max_pool_size=3,
    )
    await db.provision()
    p = await db.connect()

    # Create relationship tables (mirrors Alembic relationship migration)
    await p.execute("""
        CREATE TABLE IF NOT EXISTS contacts (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name TEXT NOT NULL,
            details JSONB DEFAULT '{}',
            archived_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ DEFAULT now(),
            updated_at TIMESTAMPTZ DEFAULT now()
        )
    """)
    await p.execute("""
        CREATE INDEX IF NOT EXISTS idx_contacts_name ON contacts (name)
    """)
    await p.execute("""
        CREATE TABLE IF NOT EXISTS relationships (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            contact_a UUID NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
            contact_b UUID NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
            type TEXT NOT NULL,
            notes TEXT,
            created_at TIMESTAMPTZ DEFAULT now()
        )
    """)
    await p.execute("""
        CREATE TABLE IF NOT EXISTS important_dates (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            contact_id UUID NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
            label TEXT NOT NULL,
            month INT NOT NULL,
            day INT NOT NULL,
            year INT,
            created_at TIMESTAMPTZ DEFAULT now()
        )
    """)
    await p.execute("""
        CREATE TABLE IF NOT EXISTS notes (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            contact_id UUID NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
            content TEXT NOT NULL,
            emotion TEXT,
            created_at TIMESTAMPTZ DEFAULT now()
        )
    """)
    await p.execute("""
        CREATE TABLE IF NOT EXISTS interactions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            contact_id UUID NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
            type TEXT NOT NULL,
            summary TEXT,
            occurred_at TIMESTAMPTZ DEFAULT now(),
            created_at TIMESTAMPTZ DEFAULT now()
        )
    """)
    await p.execute("""
        CREATE INDEX IF NOT EXISTS idx_interactions_contact_occurred
            ON interactions (contact_id, occurred_at)
    """)
    await p.execute("""
        CREATE TABLE IF NOT EXISTS reminders (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            contact_id UUID NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
            message TEXT NOT NULL,
            reminder_type TEXT NOT NULL CHECK (reminder_type IN ('one_time', 'recurring')),
            cron TEXT,
            due_at TIMESTAMPTZ,
            dismissed BOOLEAN DEFAULT false,
            created_at TIMESTAMPTZ DEFAULT now()
        )
    """)
    await p.execute("""
        CREATE TABLE IF NOT EXISTS gifts (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            contact_id UUID NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
            description TEXT NOT NULL,
            occasion TEXT,
            status TEXT NOT NULL DEFAULT 'idea'
                CHECK (status IN ('idea', 'purchased', 'wrapped', 'given', 'thanked')),
            created_at TIMESTAMPTZ DEFAULT now(),
            updated_at TIMESTAMPTZ DEFAULT now()
        )
    """)
    await p.execute("""
        CREATE TABLE IF NOT EXISTS loans (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            contact_id UUID NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
            amount NUMERIC NOT NULL,
            direction TEXT NOT NULL CHECK (direction IN ('lent', 'borrowed')),
            description TEXT,
            settled BOOLEAN DEFAULT false,
            created_at TIMESTAMPTZ DEFAULT now(),
            settled_at TIMESTAMPTZ
        )
    """)
    await p.execute("""
        CREATE TABLE IF NOT EXISTS groups (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name TEXT NOT NULL UNIQUE,
            created_at TIMESTAMPTZ DEFAULT now()
        )
    """)
    await p.execute("""
        CREATE TABLE IF NOT EXISTS group_members (
            group_id UUID NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
            contact_id UUID NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
            PRIMARY KEY (group_id, contact_id)
        )
    """)
    await p.execute("""
        CREATE TABLE IF NOT EXISTS labels (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name TEXT NOT NULL UNIQUE,
            color TEXT,
            created_at TIMESTAMPTZ DEFAULT now()
        )
    """)
    await p.execute("""
        CREATE TABLE IF NOT EXISTS contact_labels (
            label_id UUID NOT NULL REFERENCES labels(id) ON DELETE CASCADE,
            contact_id UUID NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
            PRIMARY KEY (label_id, contact_id)
        )
    """)
    await p.execute("""
        CREATE TABLE IF NOT EXISTS quick_facts (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            contact_id UUID NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            created_at TIMESTAMPTZ DEFAULT now(),
            updated_at TIMESTAMPTZ DEFAULT now(),
            UNIQUE (contact_id, key)
        )
    """)
    await p.execute("""
        CREATE TABLE IF NOT EXISTS activity_feed (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            contact_id UUID NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
            type TEXT NOT NULL,
            description TEXT NOT NULL,
            created_at TIMESTAMPTZ DEFAULT now()
        )
    """)
    await p.execute("""
        CREATE INDEX IF NOT EXISTS idx_activity_feed_contact_created
            ON activity_feed (contact_id, created_at)
    """)

    await p.execute("""
        CREATE TABLE IF NOT EXISTS addresses (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            contact_id UUID NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
            label VARCHAR NOT NULL DEFAULT 'Home',
            line_1 TEXT NOT NULL,
            line_2 TEXT,
            city VARCHAR,
            province VARCHAR,
            postal_code VARCHAR,
            country VARCHAR(2),
            is_current BOOLEAN NOT NULL DEFAULT false,
            created_at TIMESTAMPTZ DEFAULT now(),
            updated_at TIMESTAMPTZ DEFAULT now()
        )
    """)
    await p.execute("""
        CREATE INDEX IF NOT EXISTS idx_addresses_contact_id
            ON addresses (contact_id)
    """)

    yield p
    await db.close()


# ------------------------------------------------------------------
# Contact CRUD
# ------------------------------------------------------------------


async def test_contact_create(pool):
    """contact_create inserts a new contact and returns its dict."""
    from butlers.tools.relationship import contact_create

    result = await contact_create(pool, "Alice", {"email": "alice@example.com"})
    assert result["name"] == "Alice"
    assert isinstance(result["id"], uuid.UUID)
    assert result["details"] == {"email": "alice@example.com"}


async def test_contact_create_default_details(pool):
    """contact_create uses empty dict for details when not provided."""
    from butlers.tools.relationship import contact_create

    result = await contact_create(pool, "Bob")
    assert result["details"] == {}


async def test_contact_update(pool):
    """contact_update changes fields on an existing contact."""
    from butlers.tools.relationship import contact_create, contact_update

    c = await contact_create(pool, "Carol")
    updated = await contact_update(pool, c["id"], name="Caroline", details={"age": 30})
    assert updated["name"] == "Caroline"
    assert updated["details"] == {"age": 30}


async def test_contact_update_not_found(pool):
    """contact_update raises ValueError for non-existent contact."""
    from butlers.tools.relationship import contact_update

    with pytest.raises(ValueError, match="not found"):
        await contact_update(pool, uuid.uuid4(), name="Nobody")


async def test_contact_get(pool):
    """contact_get returns the contact by ID."""
    from butlers.tools.relationship import contact_create, contact_get

    c = await contact_create(pool, "Dave")
    fetched = await contact_get(pool, c["id"])
    assert fetched["name"] == "Dave"
    assert fetched["id"] == c["id"]


async def test_contact_get_not_found(pool):
    """contact_get raises ValueError for non-existent contact."""
    from butlers.tools.relationship import contact_get

    with pytest.raises(ValueError, match="not found"):
        await contact_get(pool, uuid.uuid4())


async def test_contact_search(pool):
    """contact_search finds contacts by name ILIKE."""
    from butlers.tools.relationship import contact_create, contact_search

    await contact_create(pool, "Eve Johnson")
    await contact_create(pool, "Frank Miller")

    results = await contact_search(pool, "john")
    names = [r["name"] for r in results]
    assert "Eve Johnson" in names
    assert "Frank Miller" not in names


async def test_contact_search_by_details(pool):
    """contact_search finds contacts by details JSONB text match."""
    from butlers.tools.relationship import contact_create, contact_search

    await contact_create(pool, "Grace", {"company": "Acme Corp"})

    results = await contact_search(pool, "Acme")
    names = [r["name"] for r in results]
    assert "Grace" in names


async def test_contact_archive(pool):
    """contact_archive sets archived_at and excludes from search."""
    from butlers.tools.relationship import contact_archive, contact_create, contact_search

    c = await contact_create(pool, "Hank Archived")
    archived = await contact_archive(pool, c["id"])
    assert archived["archived_at"] is not None

    # Should not appear in search
    results = await contact_search(pool, "Hank Archived")
    assert len(results) == 0


async def test_contact_archive_not_found(pool):
    """contact_archive raises ValueError for non-existent contact."""
    from butlers.tools.relationship import contact_archive

    with pytest.raises(ValueError, match="not found"):
        await contact_archive(pool, uuid.uuid4())


# ------------------------------------------------------------------
# Bidirectional relationships
# ------------------------------------------------------------------


async def test_relationship_add_creates_two_rows(pool):
    """relationship_add creates two rows for bidirectional link."""
    from butlers.tools.relationship import contact_create, relationship_add

    a = await contact_create(pool, "Rel-A")
    b = await contact_create(pool, "Rel-B")

    result = await relationship_add(pool, a["id"], b["id"], "friend", notes="college")
    assert result["type"] == "friend"

    # Check two rows exist
    count = await pool.fetchval(
        """
        SELECT count(*) FROM relationships
        WHERE (contact_a = $1 AND contact_b = $2)
           OR (contact_a = $2 AND contact_b = $1)
        """,
        a["id"],
        b["id"],
    )
    assert count == 2


async def test_relationship_list_both_directions(pool):
    """relationship_list returns relationships from both sides."""
    from butlers.tools.relationship import contact_create, relationship_add, relationship_list

    a = await contact_create(pool, "Dir-A")
    b = await contact_create(pool, "Dir-B")
    await relationship_add(pool, a["id"], b["id"], "sibling")

    list_a = await relationship_list(pool, a["id"])
    list_b = await relationship_list(pool, b["id"])

    assert len(list_a) >= 1
    assert len(list_b) >= 1
    assert any(r["contact_b"] == b["id"] for r in list_a)
    assert any(r["contact_b"] == a["id"] for r in list_b)


async def test_relationship_remove(pool):
    """relationship_remove deletes both directions."""
    from butlers.tools.relationship import (
        contact_create,
        relationship_add,
        relationship_list,
        relationship_remove,
    )

    a = await contact_create(pool, "Rem-A")
    b = await contact_create(pool, "Rem-B")
    await relationship_add(pool, a["id"], b["id"], "colleague")

    await relationship_remove(pool, a["id"], b["id"])

    list_a = await relationship_list(pool, a["id"])
    list_b = await relationship_list(pool, b["id"])
    assert not any(r["contact_b"] == b["id"] for r in list_a)
    assert not any(r["contact_b"] == a["id"] for r in list_b)


# ------------------------------------------------------------------
# Dates
# ------------------------------------------------------------------


async def test_date_add(pool):
    """date_add creates an important date."""
    from butlers.tools.relationship import contact_create, date_add

    c = await contact_create(pool, "Date-Person")
    d = await date_add(pool, c["id"], "birthday", 3, 15, 1990)
    assert d["label"] == "birthday"
    assert d["month"] == 3
    assert d["day"] == 15
    assert d["year"] == 1990


async def test_date_add_partial(pool):
    """date_add works without a year (partial date)."""
    from butlers.tools.relationship import contact_create, date_add

    c = await contact_create(pool, "Partial-Date")
    d = await date_add(pool, c["id"], "anniversary", 7, 4)
    assert d["year"] is None
    assert d["month"] == 7
    assert d["day"] == 4


async def test_date_list(pool):
    """date_list returns dates ordered by month/day."""
    from butlers.tools.relationship import contact_create, date_add, date_list

    c = await contact_create(pool, "Multi-Date")
    await date_add(pool, c["id"], "birthday", 12, 25)
    await date_add(pool, c["id"], "anniversary", 1, 1)

    dates = await date_list(pool, c["id"])
    assert len(dates) == 2
    assert dates[0]["month"] <= dates[1]["month"]


async def test_upcoming_dates(pool):
    """upcoming_dates returns dates within the specified window."""
    from butlers.tools.relationship import contact_create, date_add, upcoming_dates

    c = await contact_create(pool, "Upcoming-Person")
    now = datetime.now(UTC)

    # Add a date that's tomorrow (should be upcoming)
    from datetime import timedelta

    tomorrow = now + timedelta(days=1)
    await date_add(pool, c["id"], "test-date", tomorrow.month, tomorrow.day)

    results = await upcoming_dates(pool, days_ahead=7)
    assert any(r["contact_id"] == c["id"] for r in results)


# ------------------------------------------------------------------
# Notes
# ------------------------------------------------------------------


async def test_note_create(pool):
    """note_create stores a note with optional emotion."""
    from butlers.tools.relationship import contact_create, note_create

    c = await contact_create(pool, "Note-Person")
    n = await note_create(pool, c["id"], "Met at conference", emotion="happy")
    assert n["content"] == "Met at conference"
    assert n["emotion"] == "happy"


async def test_note_create_no_emotion(pool):
    """note_create works without emotion."""
    from butlers.tools.relationship import contact_create, note_create

    c = await contact_create(pool, "Note-NoEmo")
    n = await note_create(pool, c["id"], "Just a regular note")
    assert n["emotion"] is None


async def test_note_list(pool):
    """note_list returns notes for a contact."""
    from butlers.tools.relationship import contact_create, note_create, note_list

    c = await contact_create(pool, "Note-List")
    await note_create(pool, c["id"], "First note")
    await note_create(pool, c["id"], "Second note")

    notes = await note_list(pool, c["id"])
    assert len(notes) == 2


async def test_note_search(pool):
    """note_search finds notes by content ILIKE."""
    from butlers.tools.relationship import contact_create, note_create, note_search

    c = await contact_create(pool, "Note-Search")
    await note_create(pool, c["id"], "Loves playing tennis on weekends")
    await note_create(pool, c["id"], "Allergic to peanuts")

    results = await note_search(pool, "tennis")
    assert len(results) >= 1
    assert any("tennis" in r["content"] for r in results)


# ------------------------------------------------------------------
# Interactions
# ------------------------------------------------------------------


async def test_interaction_log(pool):
    """interaction_log creates an interaction record."""
    from butlers.tools.relationship import contact_create, interaction_log

    c = await contact_create(pool, "Inter-Person")
    i = await interaction_log(pool, c["id"], "call", summary="Caught up on the phone")
    assert i["type"] == "call"
    assert i["summary"] == "Caught up on the phone"


async def test_interaction_log_custom_time(pool):
    """interaction_log accepts a custom occurred_at."""
    from butlers.tools.relationship import contact_create, interaction_log

    c = await contact_create(pool, "Inter-Custom")
    ts = datetime(2024, 6, 15, 10, 0, 0, tzinfo=UTC)
    i = await interaction_log(pool, c["id"], "meeting", occurred_at=ts)
    assert i["occurred_at"] == ts


async def test_interaction_list_with_limit(pool):
    """interaction_list respects the limit parameter."""
    from butlers.tools.relationship import contact_create, interaction_list, interaction_log

    c = await contact_create(pool, "Inter-Limit")
    for idx in range(5):
        await interaction_log(pool, c["id"], "chat", summary=f"Chat {idx}")

    results = await interaction_list(pool, c["id"], limit=3)
    assert len(results) == 3


# ------------------------------------------------------------------
# Reminders
# ------------------------------------------------------------------


async def test_reminder_create_one_time(pool):
    """reminder_create stores a one_time reminder."""
    from butlers.tools.relationship import contact_create, reminder_create

    c = await contact_create(pool, "Remind-Once")
    due = datetime(2025, 12, 25, 0, 0, 0, tzinfo=UTC)
    r = await reminder_create(pool, c["id"], "Buy gift", "one_time", due_at=due)
    assert r["reminder_type"] == "one_time"
    assert r["due_at"] == due
    assert r["dismissed"] is False


async def test_reminder_create_recurring(pool):
    """reminder_create stores a recurring reminder with cron."""
    from butlers.tools.relationship import contact_create, reminder_create

    c = await contact_create(pool, "Remind-Recur")
    r = await reminder_create(pool, c["id"], "Weekly check-in", "recurring", cron="0 9 * * 1")
    assert r["reminder_type"] == "recurring"
    assert r["cron"] == "0 9 * * 1"


async def test_reminder_list(pool):
    """reminder_list returns reminders for a contact."""
    from butlers.tools.relationship import contact_create, reminder_create, reminder_list

    c = await contact_create(pool, "Remind-List")
    await reminder_create(pool, c["id"], "Reminder 1", "one_time")
    await reminder_create(pool, c["id"], "Reminder 2", "one_time")

    reminders = await reminder_list(pool, c["id"])
    assert len(reminders) == 2


async def test_reminder_dismiss(pool):
    """reminder_dismiss sets dismissed=True."""
    from butlers.tools.relationship import contact_create, reminder_create, reminder_dismiss

    c = await contact_create(pool, "Remind-Dismiss")
    r = await reminder_create(pool, c["id"], "Do something", "one_time")
    assert r["dismissed"] is False

    dismissed = await reminder_dismiss(pool, r["id"])
    assert dismissed["dismissed"] is True


async def test_reminder_dismiss_not_found(pool):
    """reminder_dismiss raises ValueError for non-existent reminder."""
    from butlers.tools.relationship import reminder_dismiss

    with pytest.raises(ValueError, match="not found"):
        await reminder_dismiss(pool, uuid.uuid4())


# ------------------------------------------------------------------
# Gifts (pipeline validation)
# ------------------------------------------------------------------


async def test_gift_add(pool):
    """gift_add creates a gift idea."""
    from butlers.tools.relationship import contact_create, gift_add

    c = await contact_create(pool, "Gift-Person")
    g = await gift_add(pool, c["id"], "Fancy pen", occasion="birthday")
    assert g["description"] == "Fancy pen"
    assert g["occasion"] == "birthday"
    assert g["status"] == "idea"


async def test_gift_update_status_pipeline(pool):
    """gift_update_status follows the pipeline order."""
    from butlers.tools.relationship import contact_create, gift_add, gift_update_status

    c = await contact_create(pool, "Gift-Pipeline")
    g = await gift_add(pool, c["id"], "Book")

    g = await gift_update_status(pool, g["id"], "purchased")
    assert g["status"] == "purchased"

    g = await gift_update_status(pool, g["id"], "wrapped")
    assert g["status"] == "wrapped"

    g = await gift_update_status(pool, g["id"], "given")
    assert g["status"] == "given"

    g = await gift_update_status(pool, g["id"], "thanked")
    assert g["status"] == "thanked"


async def test_gift_update_status_rejects_backward(pool):
    """gift_update_status rejects backward transitions."""
    from butlers.tools.relationship import contact_create, gift_add, gift_update_status

    c = await contact_create(pool, "Gift-Backward")
    g = await gift_add(pool, c["id"], "Watch")
    await gift_update_status(pool, g["id"], "purchased")

    with pytest.raises(ValueError, match="Cannot move"):
        await gift_update_status(pool, g["id"], "idea")


async def test_gift_update_status_rejects_same(pool):
    """gift_update_status rejects same status transition."""
    from butlers.tools.relationship import contact_create, gift_add, gift_update_status

    c = await contact_create(pool, "Gift-Same")
    g = await gift_add(pool, c["id"], "Scarf")

    with pytest.raises(ValueError, match="Cannot move"):
        await gift_update_status(pool, g["id"], "idea")


async def test_gift_update_status_invalid(pool):
    """gift_update_status rejects invalid status values."""
    from butlers.tools.relationship import contact_create, gift_add, gift_update_status

    c = await contact_create(pool, "Gift-Invalid")
    g = await gift_add(pool, c["id"], "Mug")

    with pytest.raises(ValueError, match="Invalid status"):
        await gift_update_status(pool, g["id"], "destroyed")


async def test_gift_update_status_not_found(pool):
    """gift_update_status raises ValueError for non-existent gift."""
    from butlers.tools.relationship import gift_update_status

    with pytest.raises(ValueError, match="not found"):
        await gift_update_status(pool, uuid.uuid4(), "purchased")


async def test_gift_list(pool):
    """gift_list returns gifts for a contact."""
    from butlers.tools.relationship import contact_create, gift_add, gift_list

    c = await contact_create(pool, "Gift-List")
    await gift_add(pool, c["id"], "Gift A")
    await gift_add(pool, c["id"], "Gift B")

    gifts = await gift_list(pool, c["id"])
    assert len(gifts) == 2


async def test_gift_list_filtered_by_status(pool):
    """gift_list filters by status when provided."""
    from butlers.tools.relationship import contact_create, gift_add, gift_list, gift_update_status

    c = await contact_create(pool, "Gift-Filter")
    g1 = await gift_add(pool, c["id"], "Filter Gift A")
    await gift_add(pool, c["id"], "Filter Gift B")
    await gift_update_status(pool, g1["id"], "purchased")

    ideas = await gift_list(pool, c["id"], status="idea")
    assert len(ideas) == 1
    assert ideas[0]["description"] == "Filter Gift B"

    purchased = await gift_list(pool, c["id"], status="purchased")
    assert len(purchased) == 1
    assert purchased[0]["description"] == "Filter Gift A"


# ------------------------------------------------------------------
# Loans
# ------------------------------------------------------------------


async def test_loan_create(pool):
    """loan_create stores a loan record."""
    from butlers.tools.relationship import contact_create, loan_create

    c = await contact_create(pool, "Loan-Person")
    loan = await loan_create(pool, c["id"], Decimal("50.00"), "lent", "Lunch money")
    assert loan["amount"] == Decimal("50.00")
    assert loan["direction"] == "lent"
    assert loan["description"] == "Lunch money"
    assert loan["settled"] is False


async def test_loan_settle(pool):
    """loan_settle marks a loan as settled."""
    from butlers.tools.relationship import contact_create, loan_create, loan_settle

    c = await contact_create(pool, "Loan-Settle")
    loan = await loan_create(pool, c["id"], Decimal("100.00"), "borrowed")
    settled = await loan_settle(pool, loan["id"])
    assert settled["settled"] is True
    assert settled["settled_at"] is not None


async def test_loan_settle_not_found(pool):
    """loan_settle raises ValueError for non-existent loan."""
    from butlers.tools.relationship import loan_settle

    with pytest.raises(ValueError, match="not found"):
        await loan_settle(pool, uuid.uuid4())


async def test_loan_list(pool):
    """loan_list returns loans for a contact."""
    from butlers.tools.relationship import contact_create, loan_create, loan_list

    c = await contact_create(pool, "Loan-List")
    await loan_create(pool, c["id"], Decimal("25.00"), "lent")
    await loan_create(pool, c["id"], Decimal("75.00"), "borrowed")

    loans = await loan_list(pool, c["id"])
    assert len(loans) == 2


# ------------------------------------------------------------------
# Groups
# ------------------------------------------------------------------


async def test_group_create(pool):
    """group_create creates a named group."""
    from butlers.tools.relationship import group_create

    g = await group_create(pool, "Family")
    assert g["name"] == "Family"
    assert isinstance(g["id"], uuid.UUID)


async def test_group_add_member(pool):
    """group_add_member adds a contact to a group."""
    from butlers.tools.relationship import contact_create, group_add_member, group_create

    g = await group_create(pool, "Work Team")
    c = await contact_create(pool, "Group-Member")
    result = await group_add_member(pool, g["id"], c["id"])
    assert result["group_id"] == g["id"]
    assert result["contact_id"] == c["id"]


async def test_group_list(pool):
    """group_list returns all groups."""
    from butlers.tools.relationship import group_create, group_list

    await group_create(pool, "Sports")
    groups = await group_list(pool)
    names = [g["name"] for g in groups]
    assert "Sports" in names


async def test_group_members(pool):
    """group_members returns contacts in a group."""
    from butlers.tools.relationship import (
        contact_create,
        group_add_member,
        group_create,
        group_members,
    )

    g = await group_create(pool, "Book Club")
    c1 = await contact_create(pool, "Member-A")
    c2 = await contact_create(pool, "Member-B")
    await group_add_member(pool, g["id"], c1["id"])
    await group_add_member(pool, g["id"], c2["id"])

    members = await group_members(pool, g["id"])
    member_names = [m["name"] for m in members]
    assert "Member-A" in member_names
    assert "Member-B" in member_names


# ------------------------------------------------------------------
# Labels
# ------------------------------------------------------------------


async def test_label_create(pool):
    """label_create creates a label with optional color."""
    from butlers.tools.relationship import label_create

    lbl = await label_create(pool, "vip", color="#ff0000")
    assert lbl["name"] == "vip"
    assert lbl["color"] == "#ff0000"


async def test_label_create_no_color(pool):
    """label_create works without a color."""
    from butlers.tools.relationship import label_create

    lbl = await label_create(pool, "casual")
    assert lbl["color"] is None


async def test_label_assign(pool):
    """label_assign assigns a label to a contact."""
    from butlers.tools.relationship import contact_create, label_assign, label_create

    lbl = await label_create(pool, "important")
    c = await contact_create(pool, "Label-Person")
    result = await label_assign(pool, lbl["id"], c["id"])
    assert result["label_id"] == lbl["id"]
    assert result["contact_id"] == c["id"]


async def test_contact_search_by_label(pool):
    """contact_search_by_label finds contacts with a specific label."""
    from butlers.tools.relationship import (
        contact_create,
        contact_search_by_label,
        label_assign,
        label_create,
    )

    lbl = await label_create(pool, "priority")
    c1 = await contact_create(pool, "Priority-A")
    c2 = await contact_create(pool, "Priority-B")
    await contact_create(pool, "Normal-C")
    await label_assign(pool, lbl["id"], c1["id"])
    await label_assign(pool, lbl["id"], c2["id"])

    results = await contact_search_by_label(pool, "priority")
    names = [r["name"] for r in results]
    assert "Priority-A" in names
    assert "Priority-B" in names
    assert "Normal-C" not in names


# ------------------------------------------------------------------
# Quick facts
# ------------------------------------------------------------------


async def test_fact_set(pool):
    """fact_set stores a key-value fact."""
    from butlers.tools.relationship import contact_create, fact_set

    c = await contact_create(pool, "Fact-Person")
    f = await fact_set(pool, c["id"], "favorite_color", "blue")
    assert f["key"] == "favorite_color"
    assert f["value"] == "blue"


async def test_fact_set_upsert(pool):
    """fact_set updates an existing fact (UPSERT)."""
    from butlers.tools.relationship import contact_create, fact_list, fact_set

    c = await contact_create(pool, "Fact-Upsert")
    await fact_set(pool, c["id"], "pet", "dog")
    await fact_set(pool, c["id"], "pet", "cat")

    facts = await fact_list(pool, c["id"])
    pet_facts = [f for f in facts if f["key"] == "pet"]
    assert len(pet_facts) == 1
    assert pet_facts[0]["value"] == "cat"


async def test_fact_list(pool):
    """fact_list returns all facts for a contact ordered by key."""
    from butlers.tools.relationship import contact_create, fact_list, fact_set

    c = await contact_create(pool, "Fact-List")
    await fact_set(pool, c["id"], "zodiac", "leo")
    await fact_set(pool, c["id"], "allergy", "gluten")

    facts = await fact_list(pool, c["id"])
    keys = [f["key"] for f in facts]
    assert "allergy" in keys
    assert "zodiac" in keys
    # Should be alphabetically ordered
    assert keys.index("allergy") < keys.index("zodiac")


# ------------------------------------------------------------------
# Activity feed
# ------------------------------------------------------------------


async def test_activity_feed_auto_populated(pool):
    """Mutating tools automatically populate the activity feed."""
    from butlers.tools.relationship import contact_create, feed_get, note_create

    c = await contact_create(pool, "Feed-Person")
    await note_create(pool, c["id"], "Test note for feed")

    feed = await feed_get(pool, contact_id=c["id"])
    types = [f["type"] for f in feed]
    assert "contact_created" in types
    assert "note_created" in types


async def test_activity_feed_filter_by_contact(pool):
    """feed_get filters by contact_id."""
    from butlers.tools.relationship import contact_create, feed_get, note_create

    c1 = await contact_create(pool, "Feed-A")
    c2 = await contact_create(pool, "Feed-B")
    await note_create(pool, c1["id"], "Note for A")
    await note_create(pool, c2["id"], "Note for B")

    feed_a = await feed_get(pool, contact_id=c1["id"])
    feed_b = await feed_get(pool, contact_id=c2["id"])

    # All entries in feed_a should be for c1
    assert all(f["contact_id"] == c1["id"] for f in feed_a)
    assert all(f["contact_id"] == c2["id"] for f in feed_b)


async def test_activity_feed_global(pool):
    """feed_get without contact_id returns all entries."""
    from butlers.tools.relationship import contact_create, feed_get

    await contact_create(pool, "Feed-Global")

    feed = await feed_get(pool)
    assert isinstance(feed, list)
    assert len(feed) > 0


async def test_activity_feed_limit(pool):
    """feed_get respects the limit parameter."""
    from butlers.tools.relationship import contact_create, feed_get, note_create

    c = await contact_create(pool, "Feed-Limit")
    for i in range(5):
        await note_create(pool, c["id"], f"Note {i}")

    feed = await feed_get(pool, contact_id=c["id"], limit=3)
    assert len(feed) <= 3


# ------------------------------------------------------------------
# Addresses
# ------------------------------------------------------------------


async def test_address_add(pool):
    """address_add creates an address for a contact."""
    from butlers.tools.relationship import address_add, contact_create

    c = await contact_create(pool, "Address-Person")
    addr = await address_add(
        pool,
        c["id"],
        line_1="123 Main St",
        label="Home",
        city="Springfield",
        province="IL",
        postal_code="62704",
        country="US",
    )
    assert addr["contact_id"] == c["id"]
    assert addr["line_1"] == "123 Main St"
    assert addr["label"] == "Home"
    assert addr["city"] == "Springfield"
    assert addr["province"] == "IL"
    assert addr["postal_code"] == "62704"
    assert addr["country"] == "US"
    assert addr["is_current"] is False
    assert addr["id"] is not None


async def test_address_add_minimal(pool):
    """address_add works with only required fields."""
    from butlers.tools.relationship import address_add, contact_create

    c = await contact_create(pool, "Address-Minimal")
    addr = await address_add(pool, c["id"], line_1="PO Box 42")
    assert addr["line_1"] == "PO Box 42"
    assert addr["label"] == "Home"  # default
    assert addr["city"] is None
    assert addr["country"] is None
    assert addr["is_current"] is False


async def test_address_add_with_line_2(pool):
    """address_add stores line_2 (apartment/suite)."""
    from butlers.tools.relationship import address_add, contact_create

    c = await contact_create(pool, "Address-Line2")
    addr = await address_add(pool, c["id"], line_1="456 Oak Ave", line_2="Apt 7B")
    assert addr["line_2"] == "Apt 7B"


async def test_address_add_is_current(pool):
    """address_add with is_current=True sets the flag."""
    from butlers.tools.relationship import address_add, contact_create

    c = await contact_create(pool, "Address-Current")
    addr = await address_add(pool, c["id"], line_1="1 Current Rd", is_current=True)
    assert addr["is_current"] is True


async def test_address_add_current_clears_others(pool):
    """Adding a new current address clears is_current on existing addresses."""
    from butlers.tools.relationship import address_add, address_list, contact_create

    c = await contact_create(pool, "Address-ClearCurrent")
    await address_add(pool, c["id"], line_1="Old Current", is_current=True)
    addr2 = await address_add(pool, c["id"], line_1="New Current", is_current=True)

    addrs = await address_list(pool, c["id"])
    current_addrs = [a for a in addrs if a["is_current"]]
    assert len(current_addrs) == 1
    assert current_addrs[0]["id"] == addr2["id"]


async def test_address_add_invalid_country(pool):
    """address_add rejects country codes that are not 2 characters."""
    from butlers.tools.relationship import address_add, contact_create

    c = await contact_create(pool, "Address-BadCountry")
    with pytest.raises(ValueError, match="2-letter ISO 3166-1"):
        await address_add(pool, c["id"], line_1="1 Bad St", country="USA")


async def test_address_list(pool):
    """address_list returns all addresses for a contact."""
    from butlers.tools.relationship import address_add, address_list, contact_create

    c = await contact_create(pool, "Address-ListPerson")
    await address_add(pool, c["id"], line_1="Home Address", label="Home")
    await address_add(pool, c["id"], line_1="Work Address", label="Work")

    addrs = await address_list(pool, c["id"])
    assert len(addrs) == 2
    lines = [a["line_1"] for a in addrs]
    assert "Home Address" in lines
    assert "Work Address" in lines


async def test_address_list_current_first(pool):
    """address_list returns the current address first."""
    from butlers.tools.relationship import address_add, address_list, contact_create

    c = await contact_create(pool, "Address-OrderPerson")
    await address_add(pool, c["id"], line_1="Not Current", label="Other")
    await address_add(pool, c["id"], line_1="Is Current", label="Home", is_current=True)

    addrs = await address_list(pool, c["id"])
    assert addrs[0]["line_1"] == "Is Current"
    assert addrs[0]["is_current"] is True


async def test_address_list_empty(pool):
    """address_list returns empty list for contact with no addresses."""
    from butlers.tools.relationship import address_list, contact_create

    c = await contact_create(pool, "Address-NoneYet")
    addrs = await address_list(pool, c["id"])
    assert addrs == []


async def test_address_update(pool):
    """address_update modifies address fields."""
    from butlers.tools.relationship import address_add, address_update, contact_create

    c = await contact_create(pool, "Address-UpdatePerson")
    addr = await address_add(pool, c["id"], line_1="Old Street", city="OldCity")

    updated = await address_update(
        pool, addr["id"], line_1="New Street", city="NewCity", province="CA"
    )
    assert updated["line_1"] == "New Street"
    assert updated["city"] == "NewCity"
    assert updated["province"] == "CA"
    assert updated["id"] == addr["id"]


async def test_address_update_set_current(pool):
    """address_update with is_current=True clears other current addresses."""
    from butlers.tools.relationship import (
        address_add,
        address_list,
        address_update,
        contact_create,
    )

    c = await contact_create(pool, "Address-UpdateCurrent")
    await address_add(pool, c["id"], line_1="First", is_current=True)
    addr2 = await address_add(pool, c["id"], line_1="Second")

    await address_update(pool, addr2["id"], is_current=True)

    addrs = await address_list(pool, c["id"])
    current_addrs = [a for a in addrs if a["is_current"]]
    assert len(current_addrs) == 1
    assert current_addrs[0]["id"] == addr2["id"]


async def test_address_update_not_found(pool):
    """address_update raises ValueError for nonexistent address."""
    from butlers.tools.relationship import address_update

    fake_id = uuid.uuid4()
    with pytest.raises(ValueError, match="not found"):
        await address_update(pool, fake_id, line_1="Nope")


async def test_address_update_invalid_country(pool):
    """address_update rejects invalid country code."""
    from butlers.tools.relationship import address_add, address_update, contact_create

    c = await contact_create(pool, "Address-UpdateBadCountry")
    addr = await address_add(pool, c["id"], line_1="1 Good St", country="US")

    with pytest.raises(ValueError, match="2-letter ISO 3166-1"):
        await address_update(pool, addr["id"], country="United States")


async def test_address_remove(pool):
    """address_remove deletes the address."""
    from butlers.tools.relationship import (
        address_add,
        address_list,
        address_remove,
        contact_create,
    )

    c = await contact_create(pool, "Address-RemovePerson")
    addr = await address_add(pool, c["id"], line_1="Temporary St")

    await address_remove(pool, addr["id"])

    addrs = await address_list(pool, c["id"])
    assert len(addrs) == 0


async def test_address_remove_not_found(pool):
    """address_remove raises ValueError for nonexistent address."""
    from butlers.tools.relationship import address_remove

    fake_id = uuid.uuid4()
    with pytest.raises(ValueError, match="not found"):
        await address_remove(pool, fake_id)


async def test_address_multiple_per_contact(pool):
    """A contact can have multiple addresses with different labels."""
    from butlers.tools.relationship import address_add, address_list, contact_create

    c = await contact_create(pool, "Address-Multi")
    await address_add(pool, c["id"], line_1="Home St", label="Home")
    await address_add(pool, c["id"], line_1="Work Blvd", label="Work")
    await address_add(pool, c["id"], line_1="Other Ln", label="Other")

    addrs = await address_list(pool, c["id"])
    assert len(addrs) == 3
    labels = {a["label"] for a in addrs}
    assert labels == {"Home", "Work", "Other"}


async def test_address_activity_feed_add(pool):
    """address_add logs to the activity feed."""
    from butlers.tools.relationship import address_add, contact_create, feed_get

    c = await contact_create(pool, "Address-FeedAdd")
    await address_add(pool, c["id"], line_1="Feed St", city="FeedCity", country="US")

    feed = await feed_get(pool, contact_id=c["id"])
    types = [f["type"] for f in feed]
    assert "address_added" in types
    addr_entry = next(f for f in feed if f["type"] == "address_added")
    assert "Feed St" in addr_entry["description"]
    assert "FeedCity" in addr_entry["description"]


async def test_address_activity_feed_update(pool):
    """address_update logs to the activity feed."""
    from butlers.tools.relationship import (
        address_add,
        address_update,
        contact_create,
        feed_get,
    )

    c = await contact_create(pool, "Address-FeedUpdate")
    addr = await address_add(pool, c["id"], line_1="Before St")
    await address_update(pool, addr["id"], line_1="After St")

    feed = await feed_get(pool, contact_id=c["id"])
    types = [f["type"] for f in feed]
    assert "address_updated" in types


async def test_address_activity_feed_remove(pool):
    """address_remove logs to the activity feed."""
    from butlers.tools.relationship import (
        address_add,
        address_remove,
        contact_create,
        feed_get,
    )

    c = await contact_create(pool, "Address-FeedRemove")
    addr = await address_add(pool, c["id"], line_1="Gone St", label="Work")
    await address_remove(pool, addr["id"])

    feed = await feed_get(pool, contact_id=c["id"])
    types = [f["type"] for f in feed]
    assert "address_removed" in types
    remove_entry = next(f for f in feed if f["type"] == "address_removed")
    assert "Work" in remove_entry["description"]


async def test_address_cascade_on_contact_delete(pool):
    """Addresses are deleted when the parent contact is deleted."""
    from butlers.tools.relationship import address_add, contact_create

    c = await contact_create(pool, "Address-Cascade")
    await address_add(pool, c["id"], line_1="Cascade St")

    # Direct delete (not using archive, which is soft-delete)
    await pool.execute("DELETE FROM contacts WHERE id = $1", c["id"])

    count = await pool.fetchval("SELECT COUNT(*) FROM addresses WHERE contact_id = $1", c["id"])
    assert count == 0
