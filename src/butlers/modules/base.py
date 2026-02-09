"""Abstract base class for butler modules."""

from __future__ import annotations

import abc
from typing import Any

from pydantic import BaseModel


class Module(abc.ABC):
    """Abstract base class for butler modules.

    Every pluggable module must subclass Module and implement all abstract
    members. Modules add domain-specific MCP tools to a butler but never
    touch core infrastructure.
    """

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Unique module name (e.g., 'email', 'telegram')."""
        ...

    @property
    @abc.abstractmethod
    def config_schema(self) -> type[BaseModel]:
        """Pydantic model class for this module's configuration."""
        ...

    @property
    @abc.abstractmethod
    def dependencies(self) -> list[str]:
        """Names of modules this module depends on."""
        ...

    @abc.abstractmethod
    async def register_tools(self, mcp: Any, config: Any, db: Any) -> None:
        """Register MCP tools on the butler's FastMCP server."""
        ...

    @abc.abstractmethod
    def migration_revisions(self) -> str | None:
        """Return Alembic branch label for module migrations, or None."""
        ...

    @abc.abstractmethod
    async def on_startup(self, config: Any, db: Any) -> None:
        """Called after dependency resolution and migrations."""
        ...

    @abc.abstractmethod
    async def on_shutdown(self) -> None:
        """Called during butler shutdown."""
        ...
