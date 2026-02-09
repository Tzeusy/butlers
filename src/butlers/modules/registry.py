"""Module registry with dependency resolution via topological sort."""

from __future__ import annotations

from collections import deque

from butlers.modules.base import Module


class ModuleRegistry:
    """Registry for butler modules with dependency resolution.

    Modules are registered by class, then instantiated and ordered when
    a butler's configuration is loaded.  Dependency ordering uses Kahn's
    algorithm (in-degree counting) to produce a topological sort so that
    every module is initialised only after its dependencies.
    """

    def __init__(self) -> None:
        self._modules: dict[str, type[Module]] = {}

    def register(self, module_cls: type[Module]) -> None:
        """Register a module class.

        Raises ``ValueError`` if a module with the same name is already
        registered.  The module name is obtained by instantiating the class
        temporarily — this is intentional to avoid relying on class-level
        attributes that could diverge from the instance property.
        """
        # We need the name without a full instantiation dance for concrete
        # subclasses; use a temporary instance to read the property.
        instance = module_cls()
        name = instance.name
        if name in self._modules:
            raise ValueError(f"Module '{name}' is already registered")
        self._modules[name] = module_cls

    @property
    def available_modules(self) -> list[str]:
        """List all registered module names (sorted for determinism)."""
        return sorted(self._modules.keys())

    def load_from_config(self, modules_config: dict[str, dict]) -> list[Module]:
        """Instantiate and order modules from config.

        Parameters
        ----------
        modules_config:
            Mapping of module name to per-module config dict.  Only modules
            present in this mapping are enabled for the butler.

        Returns
        -------
        list[Module]
            Module instances in dependency order (dependencies first).

        Raises
        ------
        ValueError
            If *modules_config* references an unknown module, a module
            depends on a module not in the enabled set, or the dependency
            graph contains a cycle.
        """
        # 1. Validate all requested modules are registered.
        for name in modules_config:
            if name not in self._modules:
                raise ValueError(f"Unknown module: '{name}'")

        # 2. Instantiate each module.
        instances: dict[str, Module] = {}
        for name in modules_config:
            instances[name] = self._modules[name]()

        # 3. Validate all dependencies exist in the enabled set.
        for name, instance in instances.items():
            for dep in instance.dependencies:
                if dep not in instances:
                    raise ValueError(
                        f"Module '{name}' depends on '{dep}', "
                        f"which is not in the enabled module set"
                    )

        # 4. Topological sort via Kahn's algorithm.
        in_degree: dict[str, int] = {name: 0 for name in instances}
        # Build adjacency: edge from dep -> dependent (dep must come first).
        adjacency: dict[str, list[str]] = {name: [] for name in instances}
        for name, instance in instances.items():
            for dep in instance.dependencies:
                adjacency[dep].append(name)
                in_degree[name] += 1

        queue: deque[str] = deque()
        for name, degree in in_degree.items():
            if degree == 0:
                queue.append(name)

        sorted_names: list[str] = []
        while queue:
            # Sort the current zero-degree batch for deterministic output.
            batch = sorted(queue)
            queue.clear()
            for node in batch:
                sorted_names.append(node)
                for neighbour in adjacency[node]:
                    in_degree[neighbour] -= 1
                    if in_degree[neighbour] == 0:
                        queue.append(neighbour)

        if len(sorted_names) != len(instances):
            # Some modules remain with non-zero in-degree — cycle detected.
            remaining = set(instances) - set(sorted_names)
            raise ValueError(f"Circular dependency detected among modules: {sorted(remaining)}")

        return [instances[name] for name in sorted_names]
