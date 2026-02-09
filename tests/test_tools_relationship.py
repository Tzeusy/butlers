"""Tests for butlers.tools.relationship — personal CRM tools aligned with spec."""

from __future__ import annotations

import shutil
import uuid
from datetime import UTC, datetime, timedelta

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

    # Create tables matching spec schema
    await p.execute("""
        CREATE TABLE IF NOT EXISTS contacts (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            first_name TEXT,
            last_name TEXT,
            nickname TEXT,
            company TEXT,
            job_title TEXT,
            gender TEXT,
            pronouns TEXT,
            avatar_url TEXT,
            listed BOOLEAN NOT NULL DEFAULT true,
            metadata JSONB NOT NULL DEFAULT '{}',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    await p.execute("""
        CREATE INDEX IF NOT EXISTS idx_contacts_name ON contacts (first_name, last_name)
    """)
    await p.execute("""
        CREATE TABLE IF NOT EXISTS contact_info (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            contact_id UUID NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
            type TEXT NOT NULL,
            value TEXT NOT NULL,
            label TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    await p.execute("""
        CREATE INDEX IF NOT EXISTS idx_contact_info_type ON contact_info (contact_id, type)
    """)
    await p.execute("""
        CREATE TABLE IF NOT EXISTS relationships (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            contact_id UUID NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
            related_contact_id UUID NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
            group_type TEXT NOT NULL,
            type TEXT NOT NULL,
            reverse_type TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE(contact_id, related_contact_id, type)
        )
    """)
    await p.execute("""
        CREATE TABLE IF NOT EXISTS important_dates (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            contact_id UUID NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
            label TEXT NOT NULL,
            day INT,
            month INT,
            year INT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    await p.execute("""
        CREATE INDEX IF NOT EXISTS idx_important_dates_month ON important_dates (month, day)
    """)
    await p.execute("""
        CREATE TABLE IF NOT EXISTS notes (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            contact_id UUID NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
            title TEXT,
            body TEXT NOT NULL,
            emotion TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    await p.execute("""
        CREATE INDEX IF NOT EXISTS idx_notes_contact ON notes (contact_id, created_at DESC)
    """)
    await p.execute("""
        CREATE TABLE IF NOT EXISTS interactions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            contact_id UUID NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
            type TEXT NOT NULL,
            direction TEXT,
            summary TEXT,
            duration_minutes INT,
            occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            metadata JSONB NOT NULL DEFAULT '{}'
        )
    """)
    await p.execute("""
        CREATE INDEX IF NOT EXISTS idx_interactions_contact
            ON interactions (contact_id, occurred_at DESC)
    """)
    await p.execute("""
        CREATE TABLE IF NOT EXISTS reminders (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            contact_id UUID REFERENCES contacts(id) ON DELETE CASCADE,
            label TEXT NOT NULL,
            type TEXT NOT NULL DEFAULT 'one_time',
            next_trigger_at TIMESTAMPTZ,
            last_triggered_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    await p.execute("""
        CREATE TABLE IF NOT EXISTS gifts (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            contact_id UUID NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            description TEXT,
            status TEXT NOT NULL DEFAULT 'idea'
                CHECK (status IN ('idea', 'searched', 'found', 'bought', 'given')),
            occasion TEXT,
            estimated_price_cents INT,
            url TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    await p.execute("""
        CREATE TABLE IF NOT EXISTS loans (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            lender_contact_id UUID NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
            borrower_contact_id UUID NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            amount_cents INT NOT NULL,
            currency TEXT NOT NULL DEFAULT 'USD',
            loaned_at TIMESTAMPTZ,
            settled BOOLEAN NOT NULL DEFAULT false,
            settled_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    await p.execute("""
        CREATE TABLE IF NOT EXISTS groups (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name TEXT NOT NULL,
            type TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    await p.execute("""
        CREATE TABLE IF NOT EXISTS group_members (
            group_id UUID NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
            contact_id UUID NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
            role TEXT,
            PRIMARY KEY (group_id, contact_id)
        )
    """)
    await p.execute("""
        CREATE TABLE IF NOT EXISTS labels (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name TEXT UNIQUE NOT NULL,
            color TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    await p.execute("""
        CREATE TABLE IF NOT EXISTS contact_labels (
            contact_id UUID NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
            label_id UUID NOT NULL REFERENCES labels(id) ON DELETE CASCADE,
            PRIMARY KEY (contact_id, label_id)
        )
    """)
    await p.execute("""
        CREATE TABLE IF NOT EXISTS quick_facts (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            contact_id UUID NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
            category TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    await p.execute("""
        CREATE TABLE IF NOT EXISTS addresses (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            contact_id UUID NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
            type TEXT,
            line_1 TEXT,
            line_2 TEXT,
            city TEXT,
            province TEXT,
            postal_code TEXT,
            country TEXT,
            is_current BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    await p.execute("""
        CREATE TABLE IF NOT EXISTS contact_feed (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            contact_id UUID NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
            action TEXT NOT NULL,
            entity_type TEXT,
            entity_id UUID,
            summary TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    await p.execute("""
        CREATE INDEX IF NOT EXISTS idx_contact_feed_contact
            ON contact_feed (contact_id, created_at DESC)
    """)

    yield p
    await db.close()


# ------------------------------------------------------------------
# Contact CRUD
# ------------------------------------------------------------------


async def test_contact_create_basic(pool):
    """contact_create inserts a contact with proper columns per spec."""
    from butlers.tools.relationship import contact_create

    result = await contact_create(pool, first_name="Alice", last_name="Smith", company="Acme")
    assert result["first_name"] == "Alice"
    assert result["last_name"] == "Smith"
    assert result["company"] == "Acme"
    assert result["listed"] is True
    assert isinstance(result["id"], uuid.UUID)
    assert result["metadata"] == {}


async def test_contact_create_minimal(pool):
    """contact_create works with only first_name."""
    from butlers.tools.relationship import contact_create

    result = await contact_create(pool, first_name="Bob")
    assert result["first_name"] == "Bob"
    assert result["last_name"] is None
    assert result["listed"] is True


async def test_contact_create_all_fields(pool):
    """contact_create accepts all spec fields."""
    from butlers.tools.relationship import contact_create

    result = await contact_create(
        pool,
        first_name="Carol",
        last_name="Davis",
        nickname="CD",
        company="TechCo",
        job_title="Engineer",
        gender="female",
        pronouns="she/her",
        avatar_url="https://example.com/avatar.jpg",
        metadata={"source": "linkedin"},
    )
    assert result["nickname"] == "CD"
    assert result["job_title"] == "Engineer"
    assert result["gender"] == "female"
    assert result["pronouns"] == "she/her"
    assert result["avatar_url"] == "https://example.com/avatar.jpg"
    assert result["metadata"] == {"source": "linkedin"}


async def test_contact_create_populates_feed(pool):
    """contact_create writes to the contact_feed table."""
    from butlers.tools.relationship import contact_create, feed_get

    c = await contact_create(pool, first_name="FeedTest")
    feed = await feed_get(pool, contact_id=c["id"])
    actions = [f["action"] for f in feed]
    assert "contact_created" in actions
    assert any(f["entity_type"] == "contact" for f in feed)


async def test_contact_update(pool):
    """contact_update changes fields on an existing contact."""
    from butlers.tools.relationship import contact_create, contact_update

    c = await contact_create(pool, first_name="Dan")
    updated = await contact_update(pool, c["id"], company="NewCorp", job_title="CTO")
    assert updated["company"] == "NewCorp"
    assert updated["job_title"] == "CTO"
    assert updated["first_name"] == "Dan"  # unchanged


async def test_contact_update_not_found(pool):
    """contact_update raises ValueError for non-existent contact."""
    from butlers.tools.relationship import contact_update

    with pytest.raises(ValueError, match="not found"):
        await contact_update(pool, uuid.uuid4(), first_name="Nobody")


async def test_contact_get(pool):
    """contact_get returns the contact by ID."""
    from butlers.tools.relationship import contact_create, contact_get

    c = await contact_create(pool, first_name="Eve")
    fetched = await contact_get(pool, c["id"])
    assert fetched["first_name"] == "Eve"
    assert fetched["id"] == c["id"]


async def test_contact_get_not_found(pool):
    """contact_get returns None for non-existent contact (per spec)."""
    from butlers.tools.relationship import contact_get

    result = await contact_get(pool, uuid.uuid4())
    assert result is None


async def test_contact_search_by_first_name(pool):
    """contact_search finds contacts by first_name ILIKE."""
    from butlers.tools.relationship import contact_create, contact_search

    await contact_create(pool, first_name="SearchAlice", last_name="Johnson")
    await contact_create(pool, first_name="SearchFrank", last_name="Miller")

    results = await contact_search(pool, "SearchAlice")
    names = [r["first_name"] for r in results]
    assert "SearchAlice" in names
    assert "SearchFrank" not in names


async def test_contact_search_by_company(pool):
    """contact_search finds contacts by company ILIKE."""
    from butlers.tools.relationship import contact_create, contact_search

    await contact_create(pool, first_name="CompanySearch", company="UniqueAcmeCorp")
    results = await contact_search(pool, "UniqueAcmeCorp")
    assert any(r["company"] == "UniqueAcmeCorp" for r in results)


async def test_contact_search_excludes_unlisted(pool):
    """contact_search only returns listed=true contacts."""
    from butlers.tools.relationship import contact_archive, contact_create, contact_search

    c = await contact_create(pool, first_name="UnlistedSearch123")
    await contact_archive(pool, c["id"])
    results = await contact_search(pool, "UnlistedSearch123")
    assert len(results) == 0


async def test_contact_search_pagination(pool):
    """contact_search supports limit and offset."""
    from butlers.tools.relationship import contact_create, contact_search

    for i in range(5):
        await contact_create(pool, first_name=f"PageTest{i}")

    results = await contact_search(pool, "PageTest", limit=2, offset=0)
    assert len(results) == 2
    results2 = await contact_search(pool, "PageTest", limit=2, offset=2)
    assert len(results2) == 2


async def test_contact_archive(pool):
    """contact_archive sets listed=false (soft delete)."""
    from butlers.tools.relationship import contact_archive, contact_create, contact_get

    c = await contact_create(pool, first_name="ArchivePerson")
    archived = await contact_archive(pool, c["id"])
    assert archived["listed"] is False
    # Row still exists
    fetched = await contact_get(pool, c["id"])
    assert fetched is not None
    assert fetched["listed"] is False


async def test_contact_archive_not_found(pool):
    """contact_archive raises ValueError for non-existent contact."""
    from butlers.tools.relationship import contact_archive

    with pytest.raises(ValueError, match="not found"):
        await contact_archive(pool, uuid.uuid4())


# ------------------------------------------------------------------
# Contact info
# ------------------------------------------------------------------


async def test_contact_info_add(pool):
    """contact_info_add creates email/phone records."""
    from butlers.tools.relationship import contact_create, contact_info_add

    c = await contact_create(pool, first_name="InfoPerson")
    info = await contact_info_add(pool, c["id"], "email", "alice@example.com", label="work")
    assert info["type"] == "email"
    assert info["value"] == "alice@example.com"
    assert info["label"] == "work"


async def test_contact_info_list(pool):
    """contact_info_list returns all info for a contact."""
    from butlers.tools.relationship import contact_create, contact_info_add, contact_info_list

    c = await contact_create(pool, first_name="InfoList")
    await contact_info_add(pool, c["id"], "email", "a@b.com")
    await contact_info_add(pool, c["id"], "phone", "+1234567890")

    infos = await contact_info_list(pool, c["id"])
    types = [i["type"] for i in infos]
    assert "email" in types
    assert "phone" in types


async def test_contact_info_remove(pool):
    """contact_info_remove deletes a contact info entry."""
    from butlers.tools.relationship import (
        contact_create,
        contact_info_add,
        contact_info_list,
        contact_info_remove,
    )

    c = await contact_create(pool, first_name="InfoRemove")
    info = await contact_info_add(pool, c["id"], "phone", "+9999999")
    await contact_info_remove(pool, info["id"])
    infos = await contact_info_list(pool, c["id"])
    assert not any(i["id"] == info["id"] for i in infos)


# ------------------------------------------------------------------
# Addresses
# ------------------------------------------------------------------


async def test_address_add(pool):
    """address_add creates an address for a contact."""
    from butlers.tools.relationship import address_add, contact_create

    c = await contact_create(pool, first_name="AddrPerson")
    addr = await address_add(
        pool,
        c["id"],
        type="home",
        line_1="123 Main St",
        city="Springfield",
        province="IL",
        postal_code="62701",
        country="US",
    )
    assert addr["type"] == "home"
    assert addr["city"] == "Springfield"
    assert addr["is_current"] is True


async def test_address_list(pool):
    """address_list returns addresses for a contact."""
    from butlers.tools.relationship import address_add, address_list, contact_create

    c = await contact_create(pool, first_name="AddrList")
    await address_add(pool, c["id"], type="home", city="CityA")
    await address_add(pool, c["id"], type="work", city="CityB")
    addrs = await address_list(pool, c["id"])
    assert len(addrs) == 2


async def test_address_remove(pool):
    """address_remove deletes an address."""
    from butlers.tools.relationship import (
        address_add,
        address_list,
        address_remove,
        contact_create,
    )

    c = await contact_create(pool, first_name="AddrRemove")
    addr = await address_add(pool, c["id"], type="home", city="Gone")
    await address_remove(pool, addr["id"])
    addrs = await address_list(pool, c["id"])
    assert len(addrs) == 0


# ------------------------------------------------------------------
# Bidirectional relationships
# ------------------------------------------------------------------


async def test_relationship_add_creates_two_rows(pool):
    """relationship_add creates two rows for bidirectional link per spec."""
    from butlers.tools.relationship import contact_create, relationship_add

    a = await contact_create(pool, first_name="RelA")
    b = await contact_create(pool, first_name="RelB")

    result = await relationship_add(
        pool, a["id"], b["id"], group_type="family", type="parent", reverse_type="child"
    )
    assert result["type"] == "parent"
    assert result["group_type"] == "family"

    # Check two rows exist
    count = await pool.fetchval(
        """
        SELECT count(*) FROM relationships
        WHERE (contact_id = $1 AND related_contact_id = $2)
           OR (contact_id = $2 AND related_contact_id = $1)
        """,
        a["id"],
        b["id"],
    )
    assert count == 2


async def test_relationship_add_symmetric(pool):
    """relationship_add supports symmetric relationships (friend/friend)."""
    from butlers.tools.relationship import contact_create, relationship_add

    a = await contact_create(pool, first_name="SymA")
    b = await contact_create(pool, first_name="SymB")

    await relationship_add(
        pool, a["id"], b["id"], group_type="friend", type="friend", reverse_type="friend"
    )
    # Both rows should have type="friend"
    rows = await pool.fetch(
        """
        SELECT * FROM relationships
        WHERE (contact_id = $1 AND related_contact_id = $2)
           OR (contact_id = $2 AND related_contact_id = $1)
        """,
        a["id"],
        b["id"],
    )
    assert len(rows) == 2
    assert all(r["type"] == "friend" for r in rows)


async def test_relationship_list(pool):
    """relationship_list returns relationships with related contact info."""
    from butlers.tools.relationship import contact_create, relationship_add, relationship_list

    a = await contact_create(pool, first_name="ListA", last_name="Smith")
    b = await contact_create(pool, first_name="ListB", last_name="Jones")
    await relationship_add(
        pool, a["id"], b["id"], group_type="friend", type="friend", reverse_type="friend"
    )

    rels = await relationship_list(pool, a["id"])
    assert len(rels) >= 1
    assert any(r["related_contact_id"] == b["id"] for r in rels)
    assert any(r.get("related_first_name") == "ListB" for r in rels)


async def test_relationship_remove(pool):
    """relationship_remove deletes both directions by ID."""
    from butlers.tools.relationship import (
        contact_create,
        relationship_add,
        relationship_list,
        relationship_remove,
    )

    a = await contact_create(pool, first_name="RemA")
    b = await contact_create(pool, first_name="RemB")
    rel = await relationship_add(
        pool, a["id"], b["id"], group_type="work", type="colleague", reverse_type="colleague"
    )

    await relationship_remove(pool, rel["id"])

    list_a = await relationship_list(pool, a["id"])
    list_b = await relationship_list(pool, b["id"])
    assert not any(r["related_contact_id"] == b["id"] for r in list_a)
    assert not any(r["related_contact_id"] == a["id"] for r in list_b)


async def test_relationship_remove_not_found(pool):
    """relationship_remove raises ValueError for non-existent ID."""
    from butlers.tools.relationship import relationship_remove

    with pytest.raises(ValueError, match="not found"):
        await relationship_remove(pool, uuid.uuid4())


async def test_relationship_populates_feed(pool):
    """relationship_add creates feed entries for both contacts."""
    from butlers.tools.relationship import contact_create, feed_get, relationship_add

    a = await contact_create(pool, first_name="FeedRelA")
    b = await contact_create(pool, first_name="FeedRelB")
    await relationship_add(
        pool, a["id"], b["id"], group_type="friend", type="friend", reverse_type="friend"
    )

    feed_a = await feed_get(pool, contact_id=a["id"])
    feed_b = await feed_get(pool, contact_id=b["id"])
    assert any(f["action"] == "relationship_added" for f in feed_a)
    assert any(f["action"] == "relationship_added" for f in feed_b)


# ------------------------------------------------------------------
# Dates
# ------------------------------------------------------------------


async def test_date_add(pool):
    """date_add creates an important date per spec."""
    from butlers.tools.relationship import contact_create, date_add

    c = await contact_create(pool, first_name="DatePerson")
    d = await date_add(pool, c["id"], "birthday", day=14, month=3, year=1990)
    assert d["label"] == "birthday"
    assert d["month"] == 3
    assert d["day"] == 14
    assert d["year"] == 1990


async def test_date_add_partial(pool):
    """date_add works with null year (partial date)."""
    from butlers.tools.relationship import contact_create, date_add

    c = await contact_create(pool, first_name="PartialDate")
    d = await date_add(pool, c["id"], "birthday", day=25, month=12)
    assert d["year"] is None


async def test_date_add_populates_feed(pool):
    """date_add creates a contact_feed entry."""
    from butlers.tools.relationship import contact_create, date_add, feed_get

    c = await contact_create(pool, first_name="DateFeed")
    await date_add(pool, c["id"], "birthday", day=1, month=1)
    feed = await feed_get(pool, contact_id=c["id"])
    assert any(f["action"] == "date_added" and f["entity_type"] == "important_date" for f in feed)


async def test_date_list(pool):
    """date_list returns dates ordered by month/day."""
    from butlers.tools.relationship import contact_create, date_add, date_list

    c = await contact_create(pool, first_name="MultiDate")
    await date_add(pool, c["id"], "birthday", day=25, month=12)
    await date_add(pool, c["id"], "anniversary", day=1, month=1)

    dates = await date_list(pool, c["id"])
    assert len(dates) == 2
    assert dates[0]["month"] <= dates[1]["month"]


async def test_upcoming_dates(pool):
    """upcoming_dates returns dates within the specified window."""
    from butlers.tools.relationship import contact_create, date_add, upcoming_dates

    c = await contact_create(pool, first_name="UpcomingPerson")
    now = datetime.now(UTC)
    tomorrow = now + timedelta(days=1)
    await date_add(pool, c["id"], "test-date", day=tomorrow.day, month=tomorrow.month)

    results = await upcoming_dates(pool, days=7)
    assert any(r["contact_id"] == c["id"] for r in results)


async def test_upcoming_dates_excludes_distant(pool):
    """upcoming_dates does not return dates outside the window."""
    from butlers.tools.relationship import contact_create, date_add, upcoming_dates

    c = await contact_create(pool, first_name="DistantDate")
    now = datetime.now(UTC)
    far_future = now + timedelta(days=60)
    await date_add(pool, c["id"], "far-date", day=far_future.day, month=far_future.month)

    results = await upcoming_dates(pool, days=7)
    matching = [r for r in results if r["contact_id"] == c["id"] and r["label"] == "far-date"]
    assert len(matching) == 0


# ------------------------------------------------------------------
# Notes (spec: title, body instead of content)
# ------------------------------------------------------------------


async def test_note_create(pool):
    """note_create stores a note with title, body, emotion per spec."""
    from butlers.tools.relationship import contact_create, note_create

    c = await contact_create(pool, first_name="NotePerson")
    n = await note_create(
        pool, c["id"], body="Had a great lunch", title="Lunch", emotion="positive"
    )
    assert n["body"] == "Had a great lunch"
    assert n["title"] == "Lunch"
    assert n["emotion"] == "positive"


async def test_note_create_minimal(pool):
    """note_create works with only body."""
    from butlers.tools.relationship import contact_create, note_create

    c = await contact_create(pool, first_name="NoteMinimal")
    n = await note_create(pool, c["id"], body="Quick note")
    assert n["title"] is None
    assert n["emotion"] is None


async def test_note_create_populates_feed(pool):
    """note_create creates a contact_feed entry."""
    from butlers.tools.relationship import contact_create, feed_get, note_create

    c = await contact_create(pool, first_name="NoteFeed")
    await note_create(pool, c["id"], body="Feed test note")
    feed = await feed_get(pool, contact_id=c["id"])
    assert any(f["action"] == "note_created" and f["entity_type"] == "note" for f in feed)


async def test_note_list(pool):
    """note_list returns notes for a contact ordered by created_at desc."""
    from butlers.tools.relationship import contact_create, note_create, note_list

    c = await contact_create(pool, first_name="NoteList")
    await note_create(pool, c["id"], body="First")
    await note_create(pool, c["id"], body="Second")
    notes = await note_list(pool, c["id"])
    assert len(notes) == 2


async def test_note_search(pool):
    """note_search finds notes by body content ILIKE."""
    from butlers.tools.relationship import contact_create, note_create, note_search

    c = await contact_create(pool, first_name="NoteSearch")
    await note_create(pool, c["id"], body="Loves playing tennis on weekends")
    await note_create(pool, c["id"], body="Allergic to peanuts")

    results = await note_search(pool, "tennis")
    assert len(results) >= 1
    assert any("tennis" in r["body"] for r in results)


async def test_note_search_scoped_to_contact(pool):
    """note_search can be scoped to a specific contact."""
    from butlers.tools.relationship import contact_create, note_create, note_search

    c1 = await contact_create(pool, first_name="Scope1")
    c2 = await contact_create(pool, first_name="Scope2")
    await note_create(pool, c1["id"], body="unique_scope_term_xyz")
    await note_create(pool, c2["id"], body="unique_scope_term_xyz")

    results = await note_search(pool, "unique_scope_term_xyz", contact_id=c1["id"])
    assert all(r["contact_id"] == c1["id"] for r in results)


# ------------------------------------------------------------------
# Interactions (spec: direction, duration_minutes, metadata)
# ------------------------------------------------------------------


async def test_interaction_log(pool):
    """interaction_log creates an interaction with all spec fields."""
    from butlers.tools.relationship import contact_create, interaction_log

    c = await contact_create(pool, first_name="InterPerson")
    i = await interaction_log(
        pool,
        c["id"],
        "call",
        direction="outbound",
        summary="Discussed project",
        duration_minutes=30,
        metadata={"platform": "zoom"},
    )
    assert i["type"] == "call"
    assert i["direction"] == "outbound"
    assert i["duration_minutes"] == 30
    assert i["metadata"] == {"platform": "zoom"}


async def test_interaction_log_default_time(pool):
    """interaction_log defaults occurred_at to now when not provided."""
    from butlers.tools.relationship import contact_create, interaction_log

    c = await contact_create(pool, first_name="InterDefault")
    i = await interaction_log(pool, c["id"], "message", direction="inbound")
    assert i["occurred_at"] is not None


async def test_interaction_log_custom_time(pool):
    """interaction_log accepts a custom occurred_at."""
    from butlers.tools.relationship import contact_create, interaction_log

    c = await contact_create(pool, first_name="InterCustom")
    ts = datetime(2024, 6, 15, 10, 0, 0, tzinfo=UTC)
    i = await interaction_log(pool, c["id"], "meeting", occurred_at=ts)
    assert i["occurred_at"] == ts


async def test_interaction_log_populates_feed(pool):
    """interaction_log creates a contact_feed entry."""
    from butlers.tools.relationship import contact_create, feed_get, interaction_log

    c = await contact_create(pool, first_name="InterFeed")
    await interaction_log(pool, c["id"], "call")
    feed = await feed_get(pool, contact_id=c["id"])
    assert any(
        f["action"] == "interaction_logged" and f["entity_type"] == "interaction" for f in feed
    )


async def test_interaction_list_with_limit(pool):
    """interaction_list respects the limit parameter."""
    from butlers.tools.relationship import contact_create, interaction_list, interaction_log

    c = await contact_create(pool, first_name="InterLimit")
    for idx in range(5):
        await interaction_log(pool, c["id"], "chat", summary=f"Chat {idx}")

    results = await interaction_list(pool, c["id"], limit=3)
    assert len(results) == 3


async def test_interaction_list_filter_by_type(pool):
    """interaction_list filters by type when provided."""
    from butlers.tools.relationship import contact_create, interaction_list, interaction_log

    c = await contact_create(pool, first_name="InterFilter")
    await interaction_log(pool, c["id"], "call")
    await interaction_log(pool, c["id"], "call")
    await interaction_log(pool, c["id"], "meeting")

    calls = await interaction_list(pool, c["id"], type="call")
    assert len(calls) == 2
    assert all(r["type"] == "call" for r in calls)


# ------------------------------------------------------------------
# Reminders (spec: label, type=one_time/recurring_yearly/recurring_monthly)
# ------------------------------------------------------------------


async def test_reminder_create_one_time(pool):
    """reminder_create stores a one_time reminder per spec."""
    from butlers.tools.relationship import contact_create, reminder_create

    c = await contact_create(pool, first_name="RemindOnce")
    trigger = datetime(2026, 12, 25, 8, 0, 0, tzinfo=UTC)
    r = await reminder_create(
        pool, label="Buy gift", type="one_time", next_trigger_at=trigger, contact_id=c["id"]
    )
    assert r["type"] == "one_time"
    assert r["next_trigger_at"] == trigger
    assert r["label"] == "Buy gift"


async def test_reminder_create_without_contact(pool):
    """reminder_create works without a contact_id (global reminder)."""
    from butlers.tools.relationship import reminder_create

    r = await reminder_create(
        pool,
        label="General check-in",
        type="one_time",
        next_trigger_at=datetime(2026, 4, 1, 9, 0, 0, tzinfo=UTC),
    )
    assert r["contact_id"] is None


async def test_reminder_create_recurring_yearly(pool):
    """reminder_create stores a recurring_yearly reminder."""
    from butlers.tools.relationship import contact_create, reminder_create

    c = await contact_create(pool, first_name="RemindYearly")
    r = await reminder_create(
        pool,
        label="Anniversary",
        type="recurring_yearly",
        next_trigger_at=datetime(2026, 6, 15, 8, 0, 0, tzinfo=UTC),
        contact_id=c["id"],
    )
    assert r["type"] == "recurring_yearly"


async def test_reminder_list(pool):
    """reminder_list returns active reminders for a contact."""
    from butlers.tools.relationship import contact_create, reminder_create, reminder_list

    c = await contact_create(pool, first_name="RemindList")
    future = datetime.now(UTC) + timedelta(days=30)
    await reminder_create(
        pool, label="Reminder 1", type="one_time", next_trigger_at=future, contact_id=c["id"]
    )
    await reminder_create(
        pool, label="Reminder 2", type="one_time", next_trigger_at=future, contact_id=c["id"]
    )

    reminders = await reminder_list(pool, contact_id=c["id"])
    assert len(reminders) == 2


async def test_reminder_dismiss_one_time(pool):
    """reminder_dismiss nullifies next_trigger_at for one_time reminders."""
    from butlers.tools.relationship import contact_create, reminder_create, reminder_dismiss

    c = await contact_create(pool, first_name="DismissOnce")
    r = await reminder_create(
        pool,
        label="Do something",
        type="one_time",
        next_trigger_at=datetime(2026, 3, 14, 8, 0, 0, tzinfo=UTC),
        contact_id=c["id"],
    )

    dismissed = await reminder_dismiss(pool, r["id"])
    assert dismissed["next_trigger_at"] is None
    assert dismissed["last_triggered_at"] is not None


async def test_reminder_dismiss_recurring_yearly(pool):
    """reminder_dismiss advances next_trigger_at by 1 year for recurring_yearly."""
    from butlers.tools.relationship import contact_create, reminder_create, reminder_dismiss

    c = await contact_create(pool, first_name="DismissYearly")
    trigger = datetime(2026, 3, 14, 8, 0, 0, tzinfo=UTC)
    r = await reminder_create(
        pool,
        label="Annual check",
        type="recurring_yearly",
        next_trigger_at=trigger,
        contact_id=c["id"],
    )

    dismissed = await reminder_dismiss(pool, r["id"])
    assert dismissed["next_trigger_at"] == datetime(2027, 3, 14, 8, 0, 0, tzinfo=UTC)
    assert dismissed["last_triggered_at"] is not None


async def test_reminder_dismiss_recurring_monthly(pool):
    """reminder_dismiss advances next_trigger_at by 1 month for recurring_monthly."""
    from butlers.tools.relationship import contact_create, reminder_create, reminder_dismiss

    c = await contact_create(pool, first_name="DismissMonthly")
    trigger = datetime(2026, 3, 14, 8, 0, 0, tzinfo=UTC)
    r = await reminder_create(
        pool,
        label="Monthly check",
        type="recurring_monthly",
        next_trigger_at=trigger,
        contact_id=c["id"],
    )

    dismissed = await reminder_dismiss(pool, r["id"])
    assert dismissed["next_trigger_at"] == datetime(2026, 4, 14, 8, 0, 0, tzinfo=UTC)


async def test_reminder_dismiss_not_found(pool):
    """reminder_dismiss raises ValueError for non-existent reminder."""
    from butlers.tools.relationship import reminder_dismiss

    with pytest.raises(ValueError, match="not found"):
        await reminder_dismiss(pool, uuid.uuid4())


# ------------------------------------------------------------------
# Gifts (spec: name, description, estimated_price_cents, url, pipeline order)
# ------------------------------------------------------------------


async def test_gift_add(pool):
    """gift_add creates a gift with spec fields."""
    from butlers.tools.relationship import contact_create, gift_add

    c = await contact_create(pool, first_name="GiftPerson")
    g = await gift_add(
        pool,
        c["id"],
        name="Kindle Paperwhite",
        occasion="birthday",
        estimated_price_cents=14000,
        url="https://example.com/kindle",
    )
    assert g["name"] == "Kindle Paperwhite"
    assert g["occasion"] == "birthday"
    assert g["status"] == "idea"
    assert g["estimated_price_cents"] == 14000
    assert g["url"] == "https://example.com/kindle"


async def test_gift_add_populates_feed(pool):
    """gift_add creates a contact_feed entry."""
    from butlers.tools.relationship import contact_create, feed_get, gift_add

    c = await contact_create(pool, first_name="GiftFeed")
    await gift_add(pool, c["id"], name="Book")
    feed = await feed_get(pool, contact_id=c["id"])
    assert any(f["action"] == "gift_added" and f["entity_type"] == "gift" for f in feed)


async def test_gift_update_status(pool):
    """gift_update_status changes the status."""
    from butlers.tools.relationship import contact_create, gift_add, gift_update_status

    c = await contact_create(pool, first_name="GiftStatus")
    g = await gift_add(pool, c["id"], name="Watch")

    g = await gift_update_status(pool, g["id"], "searched")
    assert g["status"] == "searched"

    g = await gift_update_status(pool, g["id"], "found")
    assert g["status"] == "found"

    g = await gift_update_status(pool, g["id"], "bought")
    assert g["status"] == "bought"

    g = await gift_update_status(pool, g["id"], "given")
    assert g["status"] == "given"


async def test_gift_update_status_invalid(pool):
    """gift_update_status rejects invalid status values."""
    from butlers.tools.relationship import contact_create, gift_add, gift_update_status

    c = await contact_create(pool, first_name="GiftInvalid")
    g = await gift_add(pool, c["id"], name="Mug")

    with pytest.raises(ValueError, match="Invalid status"):
        await gift_update_status(pool, g["id"], "destroyed")


async def test_gift_update_status_not_found(pool):
    """gift_update_status raises ValueError for non-existent gift."""
    from butlers.tools.relationship import gift_update_status

    with pytest.raises(ValueError, match="not found"):
        await gift_update_status(pool, uuid.uuid4(), "bought")


async def test_gift_update_status_populates_feed(pool):
    """gift_update_status creates a contact_feed entry."""
    from butlers.tools.relationship import contact_create, feed_get, gift_add, gift_update_status

    c = await contact_create(pool, first_name="GiftFeedUpdate")
    g = await gift_add(pool, c["id"], name="Pen")
    await gift_update_status(pool, g["id"], "searched")
    feed = await feed_get(pool, contact_id=c["id"])
    assert any(f["action"] == "gift_status_updated" and f["entity_type"] == "gift" for f in feed)


async def test_gift_list(pool):
    """gift_list returns gifts for a contact."""
    from butlers.tools.relationship import contact_create, gift_add, gift_list

    c = await contact_create(pool, first_name="GiftList")
    await gift_add(pool, c["id"], name="Gift A")
    await gift_add(pool, c["id"], name="Gift B")

    gifts = await gift_list(pool, c["id"])
    assert len(gifts) == 2


async def test_gift_list_filtered_by_status(pool):
    """gift_list filters by status when provided."""
    from butlers.tools.relationship import contact_create, gift_add, gift_list, gift_update_status

    c = await contact_create(pool, first_name="GiftFilter")
    g1 = await gift_add(pool, c["id"], name="Filter A")
    await gift_add(pool, c["id"], name="Filter B")
    await gift_update_status(pool, g1["id"], "bought")

    ideas = await gift_list(pool, c["id"], status="idea")
    assert len(ideas) == 1
    assert ideas[0]["name"] == "Filter B"

    bought = await gift_list(pool, c["id"], status="bought")
    assert len(bought) == 1
    assert bought[0]["name"] == "Filter A"


# ------------------------------------------------------------------
# Loans (spec: lender/borrower, amount_cents, currency)
# ------------------------------------------------------------------


async def test_loan_create(pool):
    """loan_create stores a loan record per spec."""
    from butlers.tools.relationship import contact_create, loan_create

    lender = await contact_create(pool, first_name="Lender")
    borrower = await contact_create(pool, first_name="Borrower")
    loan = await loan_create(pool, lender["id"], borrower["id"], "Dinner", 5000, currency="USD")
    assert loan["amount_cents"] == 5000
    assert loan["currency"] == "USD"
    assert loan["name"] == "Dinner"
    assert loan["settled"] is False


async def test_loan_create_populates_feed(pool):
    """loan_create creates feed entries for both contacts."""
    from butlers.tools.relationship import contact_create, feed_get, loan_create

    a = await contact_create(pool, first_name="LoanFeedA")
    b = await contact_create(pool, first_name="LoanFeedB")
    await loan_create(pool, a["id"], b["id"], "Lunch", 2000)
    feed_a = await feed_get(pool, contact_id=a["id"])
    feed_b = await feed_get(pool, contact_id=b["id"])
    assert any(f["action"] == "loan_created" for f in feed_a)
    assert any(f["action"] == "loan_created" for f in feed_b)


async def test_loan_settle(pool):
    """loan_settle marks a loan as settled."""
    from butlers.tools.relationship import contact_create, loan_create, loan_settle

    a = await contact_create(pool, first_name="SettleLender")
    b = await contact_create(pool, first_name="SettleBorrower")
    loan = await loan_create(pool, a["id"], b["id"], "Coffee", 500)
    settled = await loan_settle(pool, loan["id"])
    assert settled["settled"] is True
    assert settled["settled_at"] is not None


async def test_loan_settle_already_settled(pool):
    """loan_settle raises ValueError if loan is already settled."""
    from butlers.tools.relationship import contact_create, loan_create, loan_settle

    a = await contact_create(pool, first_name="AlreadySettled1")
    b = await contact_create(pool, first_name="AlreadySettled2")
    loan = await loan_create(pool, a["id"], b["id"], "Taxi", 1500)
    await loan_settle(pool, loan["id"])

    with pytest.raises(ValueError, match="already settled"):
        await loan_settle(pool, loan["id"])


async def test_loan_settle_not_found(pool):
    """loan_settle raises ValueError for non-existent loan."""
    from butlers.tools.relationship import loan_settle

    with pytest.raises(ValueError, match="not found"):
        await loan_settle(pool, uuid.uuid4())


async def test_loan_list(pool):
    """loan_list returns loans involving a contact (as lender or borrower)."""
    from butlers.tools.relationship import contact_create, loan_create, loan_list

    a = await contact_create(pool, first_name="LoanListA")
    b = await contact_create(pool, first_name="LoanListB")
    c = await contact_create(pool, first_name="LoanListC")
    await loan_create(pool, a["id"], b["id"], "Loan1", 1000)
    await loan_create(pool, c["id"], a["id"], "Loan2", 2000)

    loans = await loan_list(pool, a["id"])
    assert len(loans) == 2


async def test_loan_list_filter_settled(pool):
    """loan_list filters by settled status when provided."""
    from butlers.tools.relationship import contact_create, loan_create, loan_list, loan_settle

    a = await contact_create(pool, first_name="LoanFilterA")
    b = await contact_create(pool, first_name="LoanFilterB")
    l1 = await loan_create(pool, a["id"], b["id"], "Settled", 1000)
    await loan_create(pool, a["id"], b["id"], "Unsettled", 2000)
    await loan_settle(pool, l1["id"])

    unsettled = await loan_list(pool, a["id"], settled=False)
    assert len(unsettled) == 1
    assert unsettled[0]["name"] == "Unsettled"


# ------------------------------------------------------------------
# Groups (spec: type, role)
# ------------------------------------------------------------------


async def test_group_create(pool):
    """group_create creates a group with optional type."""
    from butlers.tools.relationship import group_create

    g = await group_create(pool, "The Smiths", type="family")
    assert g["name"] == "The Smiths"
    assert g["type"] == "family"


async def test_group_create_no_type(pool):
    """group_create works without a type."""
    from butlers.tools.relationship import group_create

    g = await group_create(pool, "Book Club")
    assert g["type"] is None


async def test_group_add_member_with_role(pool):
    """group_add_member adds a contact to a group with a role."""
    from butlers.tools.relationship import contact_create, group_add_member, group_create

    g = await group_create(pool, "Family Group", type="family")
    c = await contact_create(pool, first_name="GroupMember")
    result = await group_add_member(pool, g["id"], c["id"], role="parent")
    assert result["role"] == "parent"


async def test_group_list_with_members(pool):
    """group_list returns groups with member details."""
    from butlers.tools.relationship import (
        contact_create,
        group_add_member,
        group_create,
        group_list,
    )

    g = await group_create(pool, f"TestGroupList{uuid.uuid4().hex[:6]}")
    c = await contact_create(pool, first_name="GLMember", last_name="Test")
    await group_add_member(pool, g["id"], c["id"], role="member")

    groups = await group_list(pool)
    matching = [gr for gr in groups if gr["id"] == g["id"]]
    assert len(matching) == 1
    assert len(matching[0]["members"]) == 1
    assert matching[0]["members"][0]["first_name"] == "GLMember"


async def test_group_members(pool):
    """group_members returns contacts in a group."""
    from butlers.tools.relationship import (
        contact_create,
        group_add_member,
        group_create,
        group_members,
    )

    g = await group_create(pool, f"MembersGroup{uuid.uuid4().hex[:6]}")
    c1 = await contact_create(pool, first_name="MemA")
    c2 = await contact_create(pool, first_name="MemB")
    await group_add_member(pool, g["id"], c1["id"])
    await group_add_member(pool, g["id"], c2["id"])

    members = await group_members(pool, g["id"])
    names = [m["first_name"] for m in members]
    assert "MemA" in names
    assert "MemB" in names


# ------------------------------------------------------------------
# Labels (spec: contact_search_by_label takes label_id)
# ------------------------------------------------------------------


async def test_label_create(pool):
    """label_create creates a label with optional color."""
    from butlers.tools.relationship import label_create

    lbl = await label_create(pool, f"vip{uuid.uuid4().hex[:6]}", color="#ff0000")
    assert lbl["color"] == "#ff0000"


async def test_label_assign(pool):
    """label_assign assigns a label to a contact."""
    from butlers.tools.relationship import contact_create, label_assign, label_create

    lbl = await label_create(pool, f"important{uuid.uuid4().hex[:6]}")
    c = await contact_create(pool, first_name="LabelPerson")
    result = await label_assign(pool, c["id"], lbl["id"])
    assert result["label_id"] == lbl["id"]
    assert result["contact_id"] == c["id"]


async def test_contact_search_by_label(pool):
    """contact_search_by_label finds contacts by label_id, only listed=true."""
    from butlers.tools.relationship import (
        contact_archive,
        contact_create,
        contact_search_by_label,
        label_assign,
        label_create,
    )

    lbl = await label_create(pool, f"priority{uuid.uuid4().hex[:6]}")
    c1 = await contact_create(pool, first_name="PriA")
    c2 = await contact_create(pool, first_name="PriB")
    c3 = await contact_create(pool, first_name="PriC")
    await label_assign(pool, c1["id"], lbl["id"])
    await label_assign(pool, c2["id"], lbl["id"])
    await label_assign(pool, c3["id"], lbl["id"])
    await contact_archive(pool, c3["id"])

    results = await contact_search_by_label(pool, lbl["id"])
    ids = [r["id"] for r in results]
    assert c1["id"] in ids
    assert c2["id"] in ids
    assert c3["id"] not in ids  # archived


# ------------------------------------------------------------------
# Quick facts (spec: category, content)
# ------------------------------------------------------------------


async def test_fact_set(pool):
    """fact_set stores a fact with category and content."""
    from butlers.tools.relationship import contact_create, fact_set

    c = await contact_create(pool, first_name="FactPerson")
    f = await fact_set(pool, c["id"], "favorite_food", "Sushi")
    assert f["category"] == "favorite_food"
    assert f["content"] == "Sushi"


async def test_fact_list(pool):
    """fact_list returns all facts for a contact ordered by category."""
    from butlers.tools.relationship import contact_create, fact_list, fact_set

    c = await contact_create(pool, first_name="FactList")
    await fact_set(pool, c["id"], "zodiac", "leo")
    await fact_set(pool, c["id"], "allergy", "gluten")

    facts = await fact_list(pool, c["id"])
    categories = [f["category"] for f in facts]
    assert "allergy" in categories
    assert "zodiac" in categories
    assert categories.index("allergy") < categories.index("zodiac")


# ------------------------------------------------------------------
# Activity feed (contact_feed table)
# ------------------------------------------------------------------


async def test_feed_get_auto_populated(pool):
    """Mutating tools automatically populate the contact_feed."""
    from butlers.tools.relationship import contact_create, feed_get, note_create

    c = await contact_create(pool, first_name="FeedPerson")
    await note_create(pool, c["id"], body="Test note for feed")

    feed = await feed_get(pool, contact_id=c["id"])
    actions = [f["action"] for f in feed]
    assert "contact_created" in actions
    assert "note_created" in actions


async def test_feed_get_filter_by_contact(pool):
    """feed_get filters by contact_id."""
    from butlers.tools.relationship import contact_create, feed_get, note_create

    c1 = await contact_create(pool, first_name="FeedA")
    c2 = await contact_create(pool, first_name="FeedB")
    await note_create(pool, c1["id"], body="Note for A")
    await note_create(pool, c2["id"], body="Note for B")

    feed_a = await feed_get(pool, contact_id=c1["id"])
    feed_b = await feed_get(pool, contact_id=c2["id"])
    assert all(f["contact_id"] == c1["id"] for f in feed_a)
    assert all(f["contact_id"] == c2["id"] for f in feed_b)


async def test_feed_get_global(pool):
    """feed_get without contact_id returns all entries."""
    from butlers.tools.relationship import contact_create, feed_get

    await contact_create(pool, first_name="FeedGlobal")
    feed = await feed_get(pool)
    assert isinstance(feed, list)
    assert len(feed) > 0


async def test_feed_get_limit(pool):
    """feed_get respects the limit parameter."""
    from butlers.tools.relationship import contact_create, feed_get, note_create

    c = await contact_create(pool, first_name="FeedLimit")
    for i in range(5):
        await note_create(pool, c["id"], body=f"Note {i}")

    feed = await feed_get(pool, contact_id=c["id"], limit=3)
    assert len(feed) <= 3


async def test_feed_entity_type_and_id(pool):
    """Feed entries contain proper entity_type and entity_id."""
    from butlers.tools.relationship import contact_create, feed_get, gift_add

    c = await contact_create(pool, first_name="FeedEntity")
    g = await gift_add(pool, c["id"], name="EntityGift")

    feed = await feed_get(pool, contact_id=c["id"])
    gift_entries = [f for f in feed if f["action"] == "gift_added"]
    assert len(gift_entries) >= 1
    assert gift_entries[0]["entity_type"] == "gift"
    assert gift_entries[0]["entity_id"] == g["id"]
