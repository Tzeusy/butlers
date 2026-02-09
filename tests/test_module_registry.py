"""Tests for the ModuleRegistry with topological sort."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import BaseModel

from butlers.modules.base import Module
from butlers.modules.registry import ModuleRegistry

# ---------------------------------------------------------------------------
# Config schemas
# ---------------------------------------------------------------------------


class EmptyConfig(BaseModel):
    """Minimal config schema for testing."""


# ---------------------------------------------------------------------------
# Concrete module fixtures
# ---------------------------------------------------------------------------


def _make_module(
    name: str,
    deps: list[str] | None = None,
    migration_label: str | None = None,
) -> type[Module]:
    """Dynamically create a concrete Module subclass for testing."""
    _name = name
    _deps = deps or []
    _migration_label = migration_label

    class DynamicModule(Module):
        @property
        def name(self) -> str:
            return _name

        @property
        def config_schema(self) -> type[BaseModel]:
            return EmptyConfig

        @property
        def dependencies(self) -> list[str]:
            return list(_deps)

        async def register_tools(self, mcp: Any, config: Any, db: Any) -> None:
            pass

        def migration_revisions(self) -> str | None:
            return _migration_label

        async def on_startup(self, config: Any, db: Any) -> None:
            pass

        async def on_shutdown(self) -> None:
            pass

    DynamicModule.__qualname__ = f"DynamicModule_{_name}"
    DynamicModule.__name__ = f"DynamicModule_{_name}"
    return DynamicModule


# Convenience pre-built module classes
ModuleA = _make_module("a")
ModuleB = _make_module("b", deps=["a"])
ModuleC = _make_module("c", deps=["b"])
ModuleD = _make_module("d", deps=["a", "b"])  # diamond dep
ModuleX = _make_module("x")
ModuleY = _make_module("y")

# Circular dependency modules
ModuleCycleA = _make_module("cycle_a", deps=["cycle_b"])
ModuleCycleB = _make_module("cycle_b", deps=["cycle_a"])

# Indirect circular dependency: p -> q -> r -> p
ModuleP = _make_module("p", deps=["r"])
ModuleQ = _make_module("q", deps=["p"])
ModuleR = _make_module("r", deps=["q"])


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_register_module():
    """Registering a module makes it available."""
    reg = ModuleRegistry()
    reg.register(ModuleA)
    assert "a" in reg.available_modules


def test_register_duplicate_name_raises():
    """Registering two modules with the same name raises ValueError."""
    reg = ModuleRegistry()
    reg.register(ModuleA)
    # Create a second class that also returns name "a"
    AnotherA = _make_module("a")
    with pytest.raises(ValueError, match="already registered"):
        reg.register(AnotherA)


def test_available_modules():
    """available_modules returns a sorted list of registered names."""
    reg = ModuleRegistry()
    reg.register(ModuleB)
    reg.register(ModuleA)
    reg.register(ModuleC)
    assert reg.available_modules == ["a", "b", "c"]


def test_load_single_module():
    """Loading a single module with no dependencies returns it alone."""
    reg = ModuleRegistry()
    reg.register(ModuleA)
    result = reg.load_from_config({"a": {}})
    assert len(result) == 1
    assert result[0].name == "a"


def test_load_linear_dependency_chain():
    """A -> B -> C becomes [C, B, A] (dependencies first)."""
    reg = ModuleRegistry()
    reg.register(ModuleA)
    reg.register(ModuleB)
    reg.register(ModuleC)
    result = reg.load_from_config({"a": {}, "b": {}, "c": {}})
    names = [m.name for m in result]
    # a has no deps, b depends on a, c depends on b
    assert names == ["a", "b", "c"]


def test_load_diamond_dependency():
    """Diamond: D depends on both A and B; B depends on A.

    Valid order: A, B, D  (A must come before both B and D).
    """
    reg = ModuleRegistry()
    reg.register(ModuleA)
    reg.register(ModuleB)
    reg.register(ModuleD)
    result = reg.load_from_config({"a": {}, "b": {}, "d": {}})
    names = [m.name for m in result]
    # a must come before b and d; b must come before d
    assert names.index("a") < names.index("b")
    assert names.index("a") < names.index("d")
    assert names.index("b") < names.index("d")


def test_load_independent_modules():
    """Independent modules (no deps) are returned in sorted order."""
    reg = ModuleRegistry()
    reg.register(ModuleY)
    reg.register(ModuleX)
    reg.register(ModuleA)
    result = reg.load_from_config({"x": {}, "y": {}, "a": {}})
    names = [m.name for m in result]
    # All independent — sorted alphabetically by name
    assert names == ["a", "x", "y"]


def test_circular_dependency_raises():
    """Direct circular dependency (A <-> B) raises ValueError."""
    reg = ModuleRegistry()
    reg.register(ModuleCycleA)
    reg.register(ModuleCycleB)
    with pytest.raises(ValueError, match="Circular dependency"):
        reg.load_from_config({"cycle_a": {}, "cycle_b": {}})


def test_indirect_circular_dependency_raises():
    """Indirect circular dependency (P -> Q -> R -> P) raises ValueError."""
    reg = ModuleRegistry()
    reg.register(ModuleP)
    reg.register(ModuleQ)
    reg.register(ModuleR)
    with pytest.raises(ValueError, match="Circular dependency"):
        reg.load_from_config({"p": {}, "q": {}, "r": {}})


def test_missing_dependency_raises():
    """A module depending on a module not in the enabled set raises ValueError."""
    reg = ModuleRegistry()
    reg.register(ModuleA)
    reg.register(ModuleB)  # B depends on A
    # Enable B but not A
    with pytest.raises(ValueError, match="not in the enabled module set"):
        reg.load_from_config({"b": {}})


def test_unknown_module_raises():
    """Requesting an unregistered module raises ValueError."""
    reg = ModuleRegistry()
    with pytest.raises(ValueError, match="Unknown module"):
        reg.load_from_config({"nonexistent": {}})


def test_empty_config_returns_empty():
    """An empty config dict returns an empty list."""
    reg = ModuleRegistry()
    reg.register(ModuleA)
    result = reg.load_from_config({})
    assert result == []
