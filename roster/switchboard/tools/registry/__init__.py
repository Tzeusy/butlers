"""Registry tools — butler registration and discovery."""

from butlers.tools.switchboard.registry.registry import (
    discover_butlers,
    list_butlers,
    register_butler,
)

__all__ = [
    "discover_butlers",
    "list_butlers",
    "register_butler",
]
