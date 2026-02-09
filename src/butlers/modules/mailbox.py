"""Mailbox module — per-butler async message inbox with MCP tools.

Each butler with this module gets a mailbox table for fire-and-forget
messages from other butlers, users, or external channels.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel

from butlers.modules.base import Module

logger = logging.getLogger(__name__)

VALID_STATUSES = {"unread", "read", "actioned", "archived"}
KNOWN_CHANNELS = {"mcp", "telegram", "email", "api", "scheduler", "system"}


class MailboxConfig(BaseModel):
    """Configuration for the mailbox module."""

    max_retention_days: int | None = None


class MailboxModule(Module):
    """Mailbox module providing async message inbox tools for a butler."""

    def __init__(self) -> None:
        self._config: MailboxConfig = MailboxConfig()
        self._db: Any = None

    @property
    def name(self) -> str:
        return "mailbox"

    @property
    def config_schema(self) -> type[BaseModel]:
        return MailboxConfig

    @property
    def dependencies(self) -> list[str]:
        return []

    def migration_revisions(self) -> str | None:
        return "mailbox"

    async def on_startup(self, config: Any, db: Any) -> None:
        """Store config and db reference."""
        self._config = MailboxConfig(**(config or {}))
        self._db = db

    async def on_shutdown(self) -> None:
        """No-op for now."""

    async def register_tools(self, mcp: Any, config: Any, db: Any) -> None:
        """Register mailbox MCP tools on the butler's FastMCP server."""
        self._config = MailboxConfig(**(config or {}))
        self._db = db
        module = self

        @mcp.tool()
        async def mailbox_post(
            sender: str,
            sender_channel: str,
            body: str,
            subject: str | None = None,
            priority: int = 2,
            metadata: str | None = None,
        ) -> dict[str, Any]:
            """Post a new message to this butler's mailbox."""
            return await module._mailbox_post(
                db, sender, sender_channel, body, subject, priority, metadata
            )

        @mcp.tool()
        async def mailbox_list(
            status: str | None = None,
            sender: str | None = None,
            limit: int = 50,
            offset: int = 0,
        ) -> list[dict[str, Any]]:
            """List messages in the mailbox with optional filters."""
            return await module._mailbox_list(db, status, sender, limit, offset)

        @mcp.tool()
        async def mailbox_read(message_id: str) -> dict[str, Any]:
            """Read a single message by ID, auto-marking unread as read."""
            return await module._mailbox_read(db, message_id)

        @mcp.tool()
        async def mailbox_update_status(message_id: str, status: str) -> dict[str, Any]:
            """Update a message's status."""
            return await module._mailbox_update_status(db, message_id, status)

        @mcp.tool()
        async def mailbox_stats() -> dict[str, Any]:
            """Return message counts grouped by status."""
            return await module._mailbox_stats(db)

    # ------------------------------------------------------------------
    # Implementation
    # ------------------------------------------------------------------

    async def _mailbox_post(
        self,
        pool: Any,
        sender: str,
        sender_channel: str,
        body: str,
        subject: str | None = None,
        priority: int = 2,
        metadata: str | None = None,
    ) -> dict[str, Any]:
        """Insert a new message into the mailbox."""
        if sender_channel not in KNOWN_CHANNELS:
            logger.warning("Unknown sender_channel '%s' — accepting anyway", sender_channel)

        meta = json.loads(metadata) if metadata else {}
        body_json = body if isinstance(body, dict) else {"text": body}

        msg_id = await pool.fetchval(
            """
            INSERT INTO mailbox (sender, sender_channel, subject, body, priority, metadata)
            VALUES ($1, $2, $3, $4::jsonb, $5, $6::jsonb)
            RETURNING id
            """,
            sender,
            sender_channel,
            subject,
            json.dumps(body_json),
            priority,
            json.dumps(meta),
        )
        return {"message_id": str(msg_id)}

    async def _mailbox_list(
        self,
        pool: Any,
        status: str | None = None,
        sender: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Query the mailbox with optional filters."""
        conditions = []
        params: list[Any] = []
        param_idx = 1

        if status is not None:
            conditions.append(f"status = ${param_idx}")
            params.append(status)
            param_idx += 1

        if sender is not None:
            conditions.append(f"sender = ${param_idx}")
            params.append(sender)
            param_idx += 1

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        params.append(limit)
        limit_param = f"${param_idx}"
        param_idx += 1

        params.append(offset)
        offset_param = f"${param_idx}"

        query = f"""
            SELECT id, sender, sender_channel, subject, status, priority, created_at
            FROM mailbox
            {where}
            ORDER BY created_at DESC
            LIMIT {limit_param} OFFSET {offset_param}
        """

        rows = await pool.fetch(query, *params)
        return [
            {
                "id": str(row["id"]),
                "sender": row["sender"],
                "sender_channel": row["sender_channel"],
                "subject": row["subject"],
                "status": row["status"],
                "priority": row["priority"],
                "created_at": row["created_at"].isoformat(),
            }
            for row in rows
        ]

    async def _mailbox_read(
        self,
        pool: Any,
        message_id: str,
    ) -> dict[str, Any]:
        """Fetch a single message by ID, auto-marking unread as read."""
        try:
            msg_uuid = uuid.UUID(message_id)
        except ValueError:
            return {"error": f"Invalid message_id: {message_id}"}

        row = await pool.fetchrow("SELECT * FROM mailbox WHERE id = $1", msg_uuid)
        if row is None:
            return {"error": f"Message not found: {message_id}"}

        # Auto-mark unread as read
        if row["status"] == "unread":
            now = datetime.now(UTC)
            await pool.execute(
                "UPDATE mailbox SET status = 'read', read_at = $2 WHERE id = $1",
                msg_uuid,
                now,
            )
            # Return updated values
            return {
                "id": str(row["id"]),
                "sender": row["sender"],
                "sender_channel": row["sender_channel"],
                "subject": row["subject"],
                "body": json.loads(row["body"]) if isinstance(row["body"], str) else row["body"],
                "priority": row["priority"],
                "status": "read",
                "metadata": (
                    json.loads(row["metadata"])
                    if isinstance(row["metadata"], str)
                    else row["metadata"]
                ),
                "created_at": row["created_at"].isoformat(),
                "read_at": now.isoformat(),
                "actioned_at": (row["actioned_at"].isoformat() if row["actioned_at"] else None),
            }

        return {
            "id": str(row["id"]),
            "sender": row["sender"],
            "sender_channel": row["sender_channel"],
            "subject": row["subject"],
            "body": json.loads(row["body"]) if isinstance(row["body"], str) else row["body"],
            "priority": row["priority"],
            "status": row["status"],
            "metadata": (
                json.loads(row["metadata"]) if isinstance(row["metadata"], str) else row["metadata"]
            ),
            "created_at": row["created_at"].isoformat(),
            "read_at": row["read_at"].isoformat() if row["read_at"] else None,
            "actioned_at": row["actioned_at"].isoformat() if row["actioned_at"] else None,
        }

    async def _mailbox_update_status(
        self,
        pool: Any,
        message_id: str,
        status: str,
    ) -> dict[str, Any]:
        """Change a message's status."""
        if status not in VALID_STATUSES:
            return {"error": f"Invalid status '{status}'. Must be one of: {sorted(VALID_STATUSES)}"}

        try:
            msg_uuid = uuid.UUID(message_id)
        except ValueError:
            return {"error": f"Invalid message_id: {message_id}"}

        row = await pool.fetchrow("SELECT id, status FROM mailbox WHERE id = $1", msg_uuid)
        if row is None:
            return {"error": f"Message not found: {message_id}"}

        now = datetime.now(UTC)

        # Set timestamps based on status transition
        if status == "read":
            await pool.execute(
                "UPDATE mailbox SET status = $2, read_at = COALESCE(read_at, $3) WHERE id = $1",
                msg_uuid,
                status,
                now,
            )
        elif status == "actioned":
            await pool.execute(
                """
                UPDATE mailbox
                SET status = $2, read_at = COALESCE(read_at, $3),
                    actioned_at = COALESCE(actioned_at, $3)
                WHERE id = $1
                """,
                msg_uuid,
                status,
                now,
            )
        else:
            await pool.execute(
                "UPDATE mailbox SET status = $2 WHERE id = $1",
                msg_uuid,
                status,
            )

        return {"message_id": str(msg_uuid), "status": status}

    async def _mailbox_stats(self, pool: Any) -> dict[str, Any]:
        """Return counts grouped by status."""
        rows = await pool.fetch("SELECT status, COUNT(*) as count FROM mailbox GROUP BY status")
        counts = {s: 0 for s in VALID_STATUSES}
        total = 0
        for row in rows:
            counts[row["status"]] = row["count"]
            total += row["count"]
        counts["total"] = total
        return counts
