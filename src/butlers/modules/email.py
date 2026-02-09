"""Email module — send_email, search_inbox, read_email MCP tools.

Uses IMAP for inbox access and SMTP for sending.
Configured via [modules.email] in butler.toml.
"""

from __future__ import annotations

import asyncio
import email as email_lib
import imaplib
import logging
import os
import smtplib
from email.mime.text import MIMEText
from typing import Any

from pydantic import BaseModel

from butlers.modules.base import Module

logger = logging.getLogger(__name__)


class EmailConfig(BaseModel):
    """Configuration for the Email module."""

    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    imap_host: str = "imap.gmail.com"
    imap_port: int = 993
    use_tls: bool = True


class EmailModule(Module):
    """Email module providing send_email, search_inbox, and read_email tools."""

    @property
    def name(self) -> str:
        return "email"

    @property
    def config_schema(self) -> type[BaseModel]:
        return EmailConfig

    @property
    def dependencies(self) -> list[str]:
        return []

    @property
    def credentials_env(self) -> list[str]:
        """Environment variables required for email authentication."""
        return ["EMAIL_ADDRESS", "EMAIL_PASSWORD"]

    def migration_revisions(self) -> str | None:
        return None  # No custom tables needed

    async def register_tools(self, mcp: Any, config: Any, db: Any) -> None:
        """Register send_email, search_inbox, read_email MCP tools."""
        self._config = EmailConfig(**(config or {}))

        @mcp.tool()
        async def send_email(to: str, subject: str, body: str) -> dict:
            """Send an email via SMTP."""
            return await self._send_email(to, subject, body)

        @mcp.tool()
        async def search_inbox(query: str) -> list[dict]:
            """Search inbox via IMAP SEARCH."""
            return await self._search_inbox(query)

        @mcp.tool()
        async def read_email(message_id: str) -> dict:
            """Read a specific email by message ID."""
            return await self._read_email(message_id)

    async def on_startup(self, config: Any, db: Any) -> None:
        """Initialize email config. Connections are created per-operation."""
        self._config = EmailConfig(**(config or {}))

    async def on_shutdown(self) -> None:
        """No persistent connections to clean up."""
        pass

    # ------------------------------------------------------------------
    # Implementation helpers using stdlib imaplib/smtplib
    # ------------------------------------------------------------------

    def _get_credentials(self) -> tuple[str, str]:
        """Read email credentials from environment variables.

        Raises ``RuntimeError`` if either EMAIL_ADDRESS or EMAIL_PASSWORD
        is not set.
        """
        address = os.environ.get("EMAIL_ADDRESS")
        password = os.environ.get("EMAIL_PASSWORD")
        if not address or not password:
            raise RuntimeError("EMAIL_ADDRESS and EMAIL_PASSWORD environment variables must be set")
        return address, password

    def _smtp_send(self, to: str, subject: str, body: str) -> dict:
        """Blocking SMTP send — intended to be run via ``asyncio.to_thread``."""
        address, password = self._get_credentials()

        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = address
        msg["To"] = to

        if self._config.use_tls:
            server = smtplib.SMTP(self._config.smtp_host, self._config.smtp_port)
            server.starttls()
        else:
            server = smtplib.SMTP(self._config.smtp_host, self._config.smtp_port)

        try:
            server.login(address, password)
            server.sendmail(address, [to], msg.as_string())
        finally:
            server.quit()

        logger.info("Email sent to %s: %s", to, subject)
        return {"status": "sent", "to": to, "subject": subject}

    def _imap_search(self, query: str) -> list[dict]:
        """Blocking IMAP search — intended to be run via ``asyncio.to_thread``."""
        address, password = self._get_credentials()

        if self._config.use_tls:
            conn = imaplib.IMAP4_SSL(self._config.imap_host, self._config.imap_port)
        else:
            conn = imaplib.IMAP4(self._config.imap_host, self._config.imap_port)

        try:
            conn.login(address, password)
            conn.select("INBOX")

            # Use the query as an IMAP SEARCH criterion
            _status, data = conn.search(None, query)
            message_ids = data[0].split() if data[0] else []

            results: list[dict] = []
            for msg_id in message_ids[-50:]:  # Limit to 50 most recent
                _status, msg_data = conn.fetch(msg_id, "(RFC822.HEADER)")
                if msg_data[0] is None:
                    continue
                raw_header = msg_data[0][1]
                parsed = email_lib.message_from_bytes(raw_header)
                results.append(
                    {
                        "message_id": msg_id.decode(),
                        "from": parsed.get("From", ""),
                        "subject": parsed.get("Subject", ""),
                        "date": parsed.get("Date", ""),
                    }
                )
        finally:
            conn.logout()

        return results

    def _imap_read(self, message_id: str) -> dict:
        """Blocking IMAP fetch — intended to be run via ``asyncio.to_thread``."""
        address, password = self._get_credentials()

        if self._config.use_tls:
            conn = imaplib.IMAP4_SSL(self._config.imap_host, self._config.imap_port)
        else:
            conn = imaplib.IMAP4(self._config.imap_host, self._config.imap_port)

        try:
            conn.login(address, password)
            conn.select("INBOX")

            _status, msg_data = conn.fetch(message_id.encode(), "(RFC822)")
            if msg_data[0] is None:
                return {"error": f"Message {message_id} not found"}

            raw_msg = msg_data[0][1]
            parsed = email_lib.message_from_bytes(raw_msg)

            # Extract body
            body = ""
            if parsed.is_multipart():
                for part in parsed.walk():
                    if part.get_content_type() == "text/plain":
                        payload = part.get_payload(decode=True)
                        if payload:
                            body = payload.decode(errors="replace")
                        break
            else:
                payload = parsed.get_payload(decode=True)
                if payload:
                    body = payload.decode(errors="replace")

            return {
                "message_id": message_id,
                "from": parsed.get("From", ""),
                "to": parsed.get("To", ""),
                "subject": parsed.get("Subject", ""),
                "date": parsed.get("Date", ""),
                "body": body,
            }
        finally:
            conn.logout()

    async def _send_email(self, to: str, subject: str, body: str) -> dict:
        """Send email via SMTP. Uses asyncio.to_thread for blocking SMTP calls."""
        return await asyncio.to_thread(self._smtp_send, to, subject, body)

    async def _search_inbox(self, query: str) -> list[dict]:
        """Search inbox via IMAP. Uses asyncio.to_thread for blocking IMAP calls."""
        return await asyncio.to_thread(self._imap_search, query)

    async def _read_email(self, message_id: str) -> dict:
        """Read specific email via IMAP. Uses asyncio.to_thread for blocking IMAP calls."""
        return await asyncio.to_thread(self._imap_read, message_id)
