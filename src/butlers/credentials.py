"""Credential validation for butler startup.

Checks that all required environment variables (core, butler-level, and
module-level) are present, and warns about missing optional vars.  Reports
all missing variables in a single aggregated error.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


class CredentialError(Exception):
    """Raised when required credentials are missing."""


def validate_credentials(
    env_required: list[str],
    env_optional: list[str],
    module_credentials: dict[str, list[str]] | None = None,
) -> None:
    """Validate that all required environment variables are set.

    Parameters
    ----------
    env_required:
        Required env vars from ``[butler.env].required``.
    env_optional:
        Optional env vars from ``[butler.env].optional`` (warn if missing).
    module_credentials:
        Dict mapping module name to list of required env var names.

    Raises
    ------
    CredentialError
        If any required env vars are missing, with an aggregated report
        identifying each missing variable and its source component.
    """
    missing: list[tuple[str, str]] = []  # (var_name, source_component)

    # Always check ANTHROPIC_API_KEY
    if not os.environ.get("ANTHROPIC_API_KEY"):
        missing.append(("ANTHROPIC_API_KEY", "core"))

    # Check [butler.env].required
    for var in env_required:
        if not os.environ.get(var):
            missing.append((var, "butler.env"))

    # Check module credentials
    if module_credentials:
        for module_name, cred_vars in module_credentials.items():
            for var in cred_vars:
                if not os.environ.get(var):
                    missing.append((var, f"module:{module_name}"))

    # Warn about optional vars
    for var in env_optional:
        if not os.environ.get(var):
            logger.warning("Optional env var %s is not set", var)

    # Raise aggregated error if any missing
    if missing:
        lines = [f"  - {var} (required by {source})" for var, source in missing]
        msg = "Missing required environment variables:\n" + "\n".join(lines)
        raise CredentialError(msg)
