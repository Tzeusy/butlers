"""Sensitivity classification for tool arguments.

Provides heuristic detection of safety-critical arguments and a resolution
function that combines explicit module declarations, heuristic matching, and
a safe default.

Resolution order (highest priority first):
    1. Explicit declaration via ``Module.tool_metadata()``
    2. Heuristic based on argument name
    3. Default: not sensitive
"""

from __future__ import annotations

from butlers.modules.base import Module, ToolMeta

# Argument names that are heuristically considered sensitive.
# Matched case-insensitively against the exact argument name.
SENSITIVE_ARG_NAMES: frozenset[str] = frozenset(
    {
        "to",
        "recipient",
        "recipients",
        "email",
        "address",
        "url",
        "uri",
        "amount",
        "price",
        "cost",
        "account",
    }
)


def is_sensitive_by_heuristic(arg_name: str) -> bool:
    """Return True if *arg_name* matches a known sensitive pattern.

    Matching is case-insensitive against the canonical set of sensitive
    argument names.
    """
    return arg_name.lower() in SENSITIVE_ARG_NAMES


def resolve_arg_sensitivity(
    tool_name: str,
    arg_name: str,
    module: Module | None = None,
) -> bool:
    """Determine whether *arg_name* on *tool_name* is sensitive.

    Resolution order:
        1. Explicit declaration in ``module.tool_metadata()`` — if the module
           provides a ``ToolMeta`` for *tool_name* that lists *arg_name*,
           that value wins.
        2. Heuristic — if *arg_name* matches a known sensitive pattern, it is
           considered sensitive.
        3. Default — the argument is **not** sensitive.

    Parameters
    ----------
    tool_name:
        The name of the MCP tool.
    arg_name:
        The name of the argument to classify.
    module:
        The ``Module`` instance that registered *tool_name*.  When ``None``
        (e.g. for core tools), only heuristic and default apply.

    Returns
    -------
    bool
        ``True`` if the argument is safety-critical.
    """
    # 1. Explicit declaration
    if module is not None:
        metadata = module.tool_metadata()
        tool_meta: ToolMeta | None = metadata.get(tool_name)
        if tool_meta is not None and arg_name in tool_meta.arg_sensitivities:
            return tool_meta.arg_sensitivities[arg_name]

    # 2. Heuristic
    if is_sensitive_by_heuristic(arg_name):
        return True

    # 3. Default
    return False


def classify_tool_args(
    tool_name: str,
    arg_names: list[str],
    module: Module | None = None,
) -> dict[str, bool]:
    """Classify all arguments of a tool as sensitive or not.

    Convenience wrapper around ``resolve_arg_sensitivity`` that processes
    an entire argument list at once.

    Returns a dict mapping each argument name to its sensitivity flag.
    """
    return {arg: resolve_arg_sensitivity(tool_name, arg, module) for arg in arg_names}
