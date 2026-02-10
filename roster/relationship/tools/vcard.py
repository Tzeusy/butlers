"""vCard import/export — export contacts to vCard 3.0 and import from vCard."""

from __future__ import annotations

import logging
import uuid
from typing import Any

import asyncpg

from butlers.tools.relationship.contacts import _parse_contact, contact_create, contact_get
from butlers.tools.relationship.dates import date_add, date_list
from butlers.tools.relationship.facts import fact_list, fact_set
from butlers.tools.relationship.notes import note_create, note_list

logger = logging.getLogger(__name__)


async def contact_export_vcard(pool: asyncpg.Pool, contact_id: uuid.UUID | None = None) -> str:
    """Export one or all contacts as vCard 3.0.

    Args:
        pool: Database connection pool
        contact_id: Optional contact ID. If None, exports all non-archived contacts.

    Returns:
        vCard 3.0 formatted string (multiple vCards if exporting all)
    """
    import vobject

    if contact_id is not None:
        # Export single contact
        contact = await contact_get(pool, contact_id)
        contacts = [contact]
    else:
        # Export all non-archived contacts
        rows = await pool.fetch("SELECT * FROM contacts WHERE archived_at IS NULL ORDER BY name")
        contacts = [_parse_contact(row) for row in rows]

    vcards = []
    for contact in contacts:
        vcard = vobject.vCard()

        # FN (Formatted Name) - required field
        vcard.add("fn")
        vcard.fn.value = contact["name"]

        # N (Name) - required field, split name into components
        vcard.add("n")
        name_parts = contact["name"].split(" ", 1)
        if len(name_parts) == 2:
            vcard.n.value = vobject.vcard.Name(family=name_parts[1], given=name_parts[0])
        else:
            vcard.n.value = vobject.vcard.Name(family=name_parts[0])

        details = contact.get("details", {})

        # TEL (Phone) - from details.contact_info
        phones = details.get("phones", [])
        for phone in phones:
            tel = vcard.add("tel")
            tel.value = phone.get("number", "")
            tel.type_param = phone.get("type", "VOICE")

        # EMAIL - from details.emails
        emails = details.get("emails", [])
        for email in emails:
            email_field = vcard.add("email")
            email_field.value = email.get("address", "")
            email_field.type_param = email.get("type", "INTERNET")

        # ADR (Address) - from details.addresses
        addresses = details.get("addresses", [])
        for addr in addresses:
            adr = vcard.add("adr")
            adr.value = vobject.vcard.Address(
                street=addr.get("street", ""),
                city=addr.get("city", ""),
                region=addr.get("state", ""),
                code=addr.get("postal_code", ""),
                country=addr.get("country", ""),
            )
            adr.type_param = addr.get("type", "HOME")

        # BDAY (Birthday) - from important_dates
        dates = await date_list(pool, contact["id"])
        for date in dates:
            if date["label"].lower() == "birthday":
                vcard.add("bday")
                if date.get("year"):
                    vcard.bday.value = f"{date['year']:04d}-{date['month']:02d}-{date['day']:02d}"
                else:
                    vcard.bday.value = f"--{date['month']:02d}-{date['day']:02d}"
                break

        # ORG (Organization) - from quick_facts.company
        facts = await fact_list(pool, contact["id"])
        facts_dict = {f["key"]: f["value"] for f in facts}

        if "company" in facts_dict:
            vcard.add("org")
            vcard.org.value = [facts_dict["company"]]

        # TITLE (Job Title) - from quick_facts.job_title
        if "job_title" in facts_dict:
            vcard.add("title")
            vcard.title.value = facts_dict["job_title"]

        # NOTE - combine emotion notes if any
        notes = await note_list(pool, contact["id"])
        if notes:
            note_texts = [n["content"] for n in notes[:3]]  # Limit to 3 most recent
            vcard.add("note")
            vcard.note.value = "\n---\n".join(note_texts)

        vcards.append(vcard.serialize())

    return "".join(vcards)


async def contact_import_vcard(pool: asyncpg.Pool, vcf_content: str) -> list[dict[str, Any]]:
    """Import vCard data and create contacts.

    Parses vCard 3.0/4.0 content and creates contacts with:
    - FN -> name
    - TEL -> details.phones
    - EMAIL -> details.emails
    - ADR -> details.addresses
    - BDAY -> important_dates (birthday)
    - ORG -> quick_facts (company)
    - TITLE -> quick_facts (job_title)
    - NOTE -> notes

    Args:
        pool: Database connection pool
        vcf_content: vCard formatted string (can contain multiple vCards)

    Returns:
        List of created contact dicts
    """
    import vobject

    created_contacts = []

    # Parse vCard(s) - vobject can handle multiple vCards in one string
    try:
        vcards = vobject.readComponents(vcf_content)
    except (vobject.base.ParseError, Exception) as e:
        raise ValueError(f"Failed to parse vCard content: {e}") from e

    for vcard in vcards:
        # Required: FN (Formatted Name)
        if not hasattr(vcard, "fn"):
            logger.warning("Skipping vCard without FN field")
            continue

        name = vcard.fn.value

        # Build details dict
        details = {"phones": [], "emails": [], "addresses": []}

        # TEL (Phone numbers)
        if hasattr(vcard, "tel_list"):
            for tel in vcard.tel_list:
                phone_type = "VOICE"
                if hasattr(tel, "type_param"):
                    phone_type = tel.type_param if isinstance(tel.type_param, str) else "VOICE"
                details["phones"].append({"number": tel.value, "type": phone_type})

        # EMAIL
        if hasattr(vcard, "email_list"):
            for email in vcard.email_list:
                email_type = "INTERNET"
                if hasattr(email, "type_param"):
                    if isinstance(email.type_param, str):
                        email_type = email.type_param
                    else:
                        email_type = "INTERNET"
                details["emails"].append({"address": email.value, "type": email_type})

        # ADR (Addresses)
        if hasattr(vcard, "adr_list"):
            for adr in vcard.adr_list:
                addr_type = "HOME"
                if hasattr(adr, "type_param"):
                    addr_type = adr.type_param if isinstance(adr.type_param, str) else "HOME"

                addr_value = adr.value
                details["addresses"].append(
                    {
                        "street": addr_value.street if hasattr(addr_value, "street") else "",
                        "city": addr_value.city if hasattr(addr_value, "city") else "",
                        "state": addr_value.region if hasattr(addr_value, "region") else "",
                        "postal_code": addr_value.code if hasattr(addr_value, "code") else "",
                        "country": addr_value.country if hasattr(addr_value, "country") else "",
                        "type": addr_type,
                    }
                )

        # Create the contact
        contact = await contact_create(pool, name, details)
        created_contacts.append(contact)

        # BDAY (Birthday) -> important_dates
        if hasattr(vcard, "bday"):
            bday_value = vcard.bday.value
            if isinstance(bday_value, str):
                # Parse date string: YYYY-MM-DD or --MM-DD
                parts = bday_value.strip().split("-")
                parts = [p for p in parts if p]  # Remove empty strings

                if len(parts) >= 2:
                    try:
                        if len(parts) == 3:
                            # YYYY-MM-DD
                            year = int(parts[0])
                            month = int(parts[1])
                            day = int(parts[2])
                            await date_add(pool, contact["id"], "birthday", month, day, year)
                        else:
                            # --MM-DD or MM-DD
                            month = int(parts[0])
                            day = int(parts[1])
                            await date_add(pool, contact["id"], "birthday", month, day)
                    except (ValueError, IndexError) as e:
                        logger.warning(f"Failed to parse birthday '{bday_value}': {e}")
            elif hasattr(bday_value, "year"):
                # Date object
                try:
                    await date_add(
                        pool,
                        contact["id"],
                        "birthday",
                        bday_value.month,
                        bday_value.day,
                        bday_value.year,
                    )
                except Exception as e:
                    logger.warning(f"Failed to add birthday: {e}")

        # ORG (Organization) -> quick_facts.company
        if hasattr(vcard, "org"):
            org_value = vcard.org.value
            if isinstance(org_value, list) and org_value:
                await fact_set(pool, contact["id"], "company", org_value[0])
            elif isinstance(org_value, str):
                await fact_set(pool, contact["id"], "company", org_value)

        # TITLE (Job Title) -> quick_facts.job_title
        if hasattr(vcard, "title"):
            await fact_set(pool, contact["id"], "job_title", vcard.title.value)

        # NOTE -> notes
        if hasattr(vcard, "note"):
            note_value = vcard.note.value
            if note_value:
                # Split on --- if it was exported from our system
                note_parts = note_value.split("\n---\n")
                for note_text in note_parts:
                    if note_text.strip():
                        await note_create(pool, contact["id"], note_text.strip())

    return created_contacts
