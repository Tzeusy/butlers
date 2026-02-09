"""Runtime adapter abstraction layer.

Provides the RuntimeAdapter ABC and a registry/factory for looking up
adapter classes by runtime type string.
"""

from butlers.core.runtimes.base import (
    GeminiAdapter,
    RuntimeAdapter,
    get_adapter,
    register_adapter,
)
from butlers.core.runtimes.claude_code import ClaudeCodeAdapter
from butlers.core.runtimes.codex import CodexAdapter

__all__ = [
    "ClaudeCodeAdapter",
    "CodexAdapter",
    "GeminiAdapter",
    "RuntimeAdapter",
    "get_adapter",
    "register_adapter",
]
