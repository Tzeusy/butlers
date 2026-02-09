"""Butler configuration loading and validation.

Reads butler.toml from a config directory, parses all sections, and returns
a validated ButlerConfig dataclass.
"""

from __future__ import annotations

import os
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Pattern matching ${VAR_NAME} — supports alphanumeric + underscore variable names.
_ENV_VAR_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


class ConfigError(Exception):
    """Raised when butler configuration is missing, malformed, or invalid."""


@dataclass
class ScheduleConfig:
    """A single scheduled task entry from [[butler.schedule]]."""

    name: str
    cron: str
    prompt: str


@dataclass
class ButlerConfig:
    """Parsed and validated butler configuration."""

    name: str
    port: int
    description: str | None = None
    db_name: str = ""
    schedules: list[ScheduleConfig] = field(default_factory=list)
    modules: dict[str, dict] = field(default_factory=dict)
    env_required: list[str] = field(default_factory=list)
    env_optional: list[str] = field(default_factory=list)
    shutdown_timeout_s: float = 30.0


def resolve_env_vars(value: Any) -> Any:
    """Recursively resolve ``${VAR_NAME}`` references in config values.

    Walks dicts, lists, and strings.  Non-string leaf values (int, bool,
    float, None) are returned unchanged.

    Parameters
    ----------
    value:
        A parsed TOML value — may be a dict, list, string, int, float,
        bool, or None.

    Returns
    -------
    Any
        The same structure with all ``${VAR_NAME}`` references in string
        values replaced by the corresponding environment variable.

    Raises
    ------
    ConfigError
        If a referenced environment variable is not set.
    """
    if isinstance(value, dict):
        return {k: resolve_env_vars(v) for k, v in value.items()}

    if isinstance(value, list):
        return [resolve_env_vars(item) for item in value]

    if isinstance(value, str):
        return _resolve_string(value)

    # int, float, bool, None — pass through unchanged.
    return value


def _resolve_string(s: str) -> str:
    """Replace all ``${VAR_NAME}`` occurrences in *s* with env var values.

    Collects all missing variable names and reports them in a single error.
    """
    missing: list[str] = []

    def _replace(match: re.Match) -> str:
        var_name = match.group(1)
        env_value = os.environ.get(var_name)
        if env_value is None:
            missing.append(var_name)
            return match.group(0)  # keep placeholder for error reporting
        return env_value

    result = _ENV_VAR_PATTERN.sub(_replace, s)

    if missing:
        vars_str = ", ".join(missing)
        raise ConfigError(
            f"Unresolved environment variable(s) in config value: {vars_str} (original: {s!r})"
        )

    return result


def load_config(config_dir: Path) -> ButlerConfig:
    """Load and validate a butler.toml from *config_dir*.

    Parameters
    ----------
    config_dir:
        Directory containing ``butler.toml``.

    Returns
    -------
    ButlerConfig
        Fully parsed and validated configuration.

    Raises
    ------
    ConfigError
        If the file is missing, contains invalid TOML, or lacks required fields.
    """
    toml_path = config_dir / "butler.toml"

    if not toml_path.exists():
        raise ConfigError(f"Config file not found: {toml_path}")

    raw_bytes = toml_path.read_bytes()
    try:
        data = tomllib.loads(raw_bytes.decode())
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"Invalid TOML in {toml_path}: {exc}") from exc

    # --- Resolve env var references before any validation ---
    data = resolve_env_vars(data)

    # --- [butler] section (required) ---
    butler_section = data.get("butler")
    if not isinstance(butler_section, dict):
        raise ConfigError("Missing [butler] section in config")

    name = butler_section.get("name")
    if name is None:
        raise ConfigError("Missing required field: butler.name")

    port = butler_section.get("port")
    if port is None:
        raise ConfigError("Missing required field: butler.port")

    description = butler_section.get("description")

    # --- [butler.db] sub-section ---
    db_section = butler_section.get("db", {})
    db_name = db_section.get("name", f"butler_{name}")

    # --- [butler.env] sub-section ---
    env_section = butler_section.get("env", {})
    env_required = list(env_section.get("required", []))
    env_optional = list(env_section.get("optional", []))

    # --- [butler.shutdown] sub-section ---
    shutdown_section = butler_section.get("shutdown", {})
    shutdown_timeout_s = float(shutdown_section.get("timeout_s", 30.0))

    # --- [[butler.schedule]] array ---
    raw_schedules = butler_section.get("schedule", [])
    schedules: list[ScheduleConfig] = []
    for entry in raw_schedules:
        schedules.append(
            ScheduleConfig(
                name=entry["name"],
                cron=entry["cron"],
                prompt=entry["prompt"],
            )
        )

    # --- [modules.*] sections ---
    modules: dict[str, dict] = {}
    raw_modules = data.get("modules", {})
    for mod_name, mod_cfg in raw_modules.items():
        modules[mod_name] = dict(mod_cfg) if isinstance(mod_cfg, dict) else {}

    return ButlerConfig(
        name=name,
        port=port,
        description=description,
        db_name=db_name,
        schedules=schedules,
        modules=modules,
        env_required=env_required,
        env_optional=env_optional,
        shutdown_timeout_s=shutdown_timeout_s,
    )
