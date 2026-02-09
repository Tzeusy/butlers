"""Butler configuration loading and validation.

Reads butler.toml from a config directory, parses all sections, and returns
a validated ButlerConfig dataclass.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path


class ConfigError(Exception):
    """Raised when butler configuration is missing, malformed, or invalid."""


@dataclass
class ScheduleConfig:
    """A single scheduled task entry from [[butler.schedule]]."""

    name: str
    cron: str
    prompt: str


@dataclass
class RuntimeConfig:
    """Runtime configuration from [butler.runtime] section.

    Controls which LLM runtime and model the butler uses. The model string
    is opaque to the framework — no validation beyond non-empty. Each runtime
    defines its own valid model IDs.
    """

    model: str | None = None


@dataclass
class ButlerConfig:
    """Parsed and validated butler configuration."""

    name: str
    port: int
    description: str | None = None
    db_name: str = ""
    runtime: RuntimeConfig = field(default_factory=RuntimeConfig)
    schedules: list[ScheduleConfig] = field(default_factory=list)
    modules: dict[str, dict] = field(default_factory=dict)
    env_required: list[str] = field(default_factory=list)
    env_optional: list[str] = field(default_factory=list)


def _parse_runtime(butler_section: dict) -> RuntimeConfig:
    """Parse the optional [butler.runtime] sub-section.

    Returns a RuntimeConfig with model set to None if the section or field
    is absent. Empty-string model values are normalised to None.
    """
    runtime_section = butler_section.get("runtime", {})
    model = runtime_section.get("model")

    # Normalise empty string to None
    if isinstance(model, str) and not model.strip():
        model = None

    return RuntimeConfig(model=model)


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

    # --- [butler.runtime] sub-section ---
    runtime = _parse_runtime(butler_section)

    # --- [butler.env] sub-section ---
    env_section = butler_section.get("env", {})
    env_required = list(env_section.get("required", []))
    env_optional = list(env_section.get("optional", []))

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
        runtime=runtime,
        schedules=schedules,
        modules=modules,
        env_required=env_required,
        env_optional=env_optional,
    )
