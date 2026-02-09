"""Telegram module — send_message and get_updates MCP tools.

Supports polling mode (dev, no public URL needed) and webhook mode (production).
Configured via [modules.telegram] in butler.toml.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

import httpx
from pydantic import BaseModel

from butlers.modules.base import Module

logger = logging.getLogger(__name__)

TELEGRAM_API_BASE = "https://api.telegram.org/bot{token}"


class TelegramConfig(BaseModel):
    """Configuration for the Telegram module."""

    mode: str = "polling"  # "polling" or "webhook"
    webhook_url: str | None = None
    poll_interval: float = 1.0


class TelegramModule(Module):
    """Telegram module providing send_message and get_updates MCP tools."""

    def __init__(self) -> None:
        self._config: TelegramConfig = TelegramConfig()
        self._client: httpx.AsyncClient | None = None
        self._poll_task: asyncio.Task[None] | None = None
        self._last_update_id: int = 0
        self._updates_buffer: list[dict[str, Any]] = []

    @property
    def name(self) -> str:
        return "telegram"

    @property
    def config_schema(self) -> type[BaseModel]:
        return TelegramConfig

    @property
    def dependencies(self) -> list[str]:
        return []

    @property
    def credentials_env(self) -> list[str]:
        """Environment variables required by this module."""
        return ["TELEGRAM_BOT_TOKEN"]

    def migration_revisions(self) -> str | None:
        return None  # No custom tables needed

    def _base_url(self) -> str:
        """Build the Telegram API base URL using the bot token."""
        token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        return TELEGRAM_API_BASE.format(token=token)

    def _get_client(self) -> httpx.AsyncClient:
        """Return the HTTP client, creating one if needed."""
        if self._client is None:
            self._client = httpx.AsyncClient()
        return self._client

    async def register_tools(self, mcp: Any, config: Any, db: Any) -> None:
        """Register send_message and get_updates MCP tools."""
        self._config = TelegramConfig(**(config or {}))
        module = self  # capture for closures

        @mcp.tool()
        async def send_message(chat_id: str, text: str) -> dict[str, Any]:
            """Send a message to a Telegram chat."""
            return await module._send_message(chat_id, text)

        @mcp.tool()
        async def get_updates() -> list[dict[str, Any]]:
            """Get recent messages from Telegram."""
            return await module._get_updates()

    async def on_startup(self, config: Any, db: Any) -> None:
        """Start polling or set webhook based on config."""
        self._config = TelegramConfig(**(config or {}))
        self._client = httpx.AsyncClient()
        self._last_update_id = 0
        self._updates_buffer = []

        if self._config.mode == "webhook" and self._config.webhook_url:
            await self._set_webhook(self._config.webhook_url)
        elif self._config.mode == "polling":
            self._poll_task = asyncio.create_task(self._poll_loop())

    async def on_shutdown(self) -> None:
        """Clean up: cancel polling, close HTTP client."""
        if self._poll_task and not self._poll_task.done():
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # ------------------------------------------------------------------
    # Telegram API helpers
    # ------------------------------------------------------------------

    async def _send_message(self, chat_id: str, text: str) -> dict[str, Any]:
        """Call Telegram sendMessage API."""
        url = f"{self._base_url()}/sendMessage"
        client = self._get_client()
        resp = await client.post(url, json={"chat_id": chat_id, "text": text})
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()
        return data

    async def _get_updates(self) -> list[dict[str, Any]]:
        """Call Telegram getUpdates API and return new messages."""
        url = f"{self._base_url()}/getUpdates"
        params: dict[str, Any] = {"timeout": 0}
        if self._last_update_id:
            params["offset"] = self._last_update_id + 1

        client = self._get_client()
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()
        updates: list[dict[str, Any]] = data.get("result", [])

        if updates:
            self._last_update_id = updates[-1]["update_id"]

        return updates

    async def _set_webhook(self, url: str) -> dict[str, Any]:
        """Call Telegram setWebhook API."""
        api_url = f"{self._base_url()}/setWebhook"
        client = self._get_client()
        resp = await client.post(api_url, json={"url": url})
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()
        return data

    async def _delete_webhook(self) -> dict[str, Any]:
        """Call Telegram deleteWebhook API."""
        url = f"{self._base_url()}/deleteWebhook"
        client = self._get_client()
        resp = await client.post(url)
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()
        return data

    async def _poll_loop(self) -> None:
        """Long-polling loop for dev mode."""
        while True:
            try:
                updates = await self._get_updates()
                if updates:
                    self._updates_buffer.extend(updates)
                    logger.debug("Polled %d update(s) from Telegram", len(updates))
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Error polling Telegram updates")

            await asyncio.sleep(self._config.poll_interval)
