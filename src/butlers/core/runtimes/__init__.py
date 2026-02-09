"""Runtime adapter abstraction layer.

Provides the RuntimeAdapter ABC and a registry/factory for looking up
adapter classes by runtime type string.
"""

from butlers.core.runtimes.base import (
    ClaudeCodeAdapter,
    CodexAdapter,
    GeminiAdapter,
    RuntimeAdapter,
    get_adapter,
    register_adapter,
)

__all__ = [
    "ClaudeCodeAdapter",
    "CodexAdapter",
    "GeminiAdapter",
    "RuntimeAdapter",
    "get_adapter",
    "register_adapter",
]
