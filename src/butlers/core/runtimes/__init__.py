"""Runtime adapter abstraction layer.

Provides the RuntimeAdapter ABC and a registry/factory for looking up
adapter classes by runtime type string.
"""

from butlers.core.runtimes.base import (
    RuntimeAdapter,
    get_adapter,
    register_adapter,
)
from butlers.core.runtimes.gemini import GeminiAdapter

__all__ = [
    "GeminiAdapter",
    "RuntimeAdapter",
    "get_adapter",
    "register_adapter",
]
