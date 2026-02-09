"""Tests for butler configuration loading and validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from butlers.config import ButlerConfig, ConfigError, ScheduleConfig, load_config

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FULL_TOML = """\
[butler]
name = "jarvis"
port = 8100
description = "Personal assistant butler"

[butler.db]
name = "jarvis_db"

[butler.env]
required = ["OPENAI_API_KEY", "PG_DSN"]
optional = ["SLACK_TOKEN"]

[[butler.schedule]]
name = "daily-digest"
cron = "0 8 * * *"
prompt = "Summarise overnight emails"

[[butler.schedule]]
name = "weekly-report"
cron = "0 9 * * 1"
prompt = "Generate weekly status report"

[modules.email]
provider = "gmail"
max_threads = 50

[modules.telegram]
bot_token_env = "TG_TOKEN"
"""

MINIMAL_TOML = """\
[butler]
name = "alfred"
port = 9000
"""


def _write_toml(tmp_path: Path, content: str, filename: str = "butler.toml") -> Path:
    """Write *content* to a TOML file inside *tmp_path* and return the directory."""
    (tmp_path / filename).write_text(content)
    return tmp_path


# ---------------------------------------------------------------------------
# Happy-path tests
# ---------------------------------------------------------------------------


def test_load_full_config(tmp_path: Path):
    """All sections present — every field is parsed correctly."""
    config_dir = _write_toml(tmp_path, FULL_TOML)
    cfg = load_config(config_dir)

    assert isinstance(cfg, ButlerConfig)
    assert cfg.name == "jarvis"
    assert cfg.port == 8100
    assert cfg.description == "Personal assistant butler"
    assert cfg.db_name == "jarvis_db"

    # Schedules
    assert len(cfg.schedules) == 2
    assert cfg.schedules[0] == ScheduleConfig(
        name="daily-digest", cron="0 8 * * *", prompt="Summarise overnight emails"
    )
    assert cfg.schedules[1] == ScheduleConfig(
        name="weekly-report", cron="0 9 * * 1", prompt="Generate weekly status report"
    )

    # Modules
    assert "email" in cfg.modules
    assert cfg.modules["email"] == {"provider": "gmail", "max_threads": 50}
    assert "telegram" in cfg.modules
    assert cfg.modules["telegram"] == {"bot_token_env": "TG_TOKEN"}

    # Env
    assert cfg.env_required == ["OPENAI_API_KEY", "PG_DSN"]
    assert cfg.env_optional == ["SLACK_TOKEN"]


def test_load_minimal_config(tmp_path: Path):
    """Only [butler] with name and port — defaults applied everywhere else."""
    config_dir = _write_toml(tmp_path, MINIMAL_TOML)
    cfg = load_config(config_dir)

    assert cfg.name == "alfred"
    assert cfg.port == 9000
    assert cfg.description is None
    assert cfg.schedules == []
    assert cfg.modules == {}
    assert cfg.env_required == []
    assert cfg.env_optional == []


def test_default_db_name(tmp_path: Path):
    """db_name defaults to butler_{name} when [butler.db] is omitted."""
    config_dir = _write_toml(tmp_path, MINIMAL_TOML)
    cfg = load_config(config_dir)

    assert cfg.db_name == "butler_alfred"


def test_env_section(tmp_path: Path):
    """Parses [butler.env] required and optional lists."""
    toml = """\
[butler]
name = "envbot"
port = 7000

[butler.env]
required = ["API_KEY"]
optional = ["DEBUG", "VERBOSE"]
"""
    config_dir = _write_toml(tmp_path, toml)
    cfg = load_config(config_dir)

    assert cfg.env_required == ["API_KEY"]
    assert cfg.env_optional == ["DEBUG", "VERBOSE"]


def test_schedule_parsing(tmp_path: Path):
    """Parses [[butler.schedule]] entries into ScheduleConfig objects."""
    toml = """\
[butler]
name = "cronbot"
port = 7001

[[butler.schedule]]
name = "tick"
cron = "*/10 * * * *"
prompt = "Do a tick"
"""
    config_dir = _write_toml(tmp_path, toml)
    cfg = load_config(config_dir)

    assert len(cfg.schedules) == 1
    sched = cfg.schedules[0]
    assert sched.name == "tick"
    assert sched.cron == "*/10 * * * *"
    assert sched.prompt == "Do a tick"


def test_modules_parsing(tmp_path: Path):
    """Parses [modules.*] sections into a dict of dicts."""
    toml = """\
[butler]
name = "modbot"
port = 7002

[modules.calendar]
provider = "google"

[modules.weather]
api_key_env = "WEATHER_KEY"
units = "metric"
"""
    config_dir = _write_toml(tmp_path, toml)
    cfg = load_config(config_dir)

    assert set(cfg.modules.keys()) == {"calendar", "weather"}
    assert cfg.modules["calendar"] == {"provider": "google"}
    assert cfg.modules["weather"] == {"api_key_env": "WEATHER_KEY", "units": "metric"}


# ---------------------------------------------------------------------------
# Validation / error tests
# ---------------------------------------------------------------------------


def test_missing_config_file(tmp_path: Path):
    """Raises ConfigError when butler.toml does not exist."""
    with pytest.raises(ConfigError, match="Config file not found"):
        load_config(tmp_path)


def test_invalid_toml(tmp_path: Path):
    """Raises ConfigError on malformed TOML with location info."""
    _write_toml(tmp_path, "[butler\nname = oops")
    with pytest.raises(ConfigError, match="Invalid TOML"):
        load_config(tmp_path)


def test_missing_name(tmp_path: Path):
    """Raises ConfigError when butler.name is absent."""
    _write_toml(tmp_path, "[butler]\nport = 8000\n")
    with pytest.raises(ConfigError, match="butler.name"):
        load_config(tmp_path)


def test_missing_port(tmp_path: Path):
    """Raises ConfigError when butler.port is absent."""
    _write_toml(tmp_path, '[butler]\nname = "noport"\n')
    with pytest.raises(ConfigError, match="butler.port"):
        load_config(tmp_path)


# ---------------------------------------------------------------------------
# Runtime config tests
# ---------------------------------------------------------------------------


def test_runtime_default_to_claude_code(tmp_path: Path):
    """When [runtime] section is missing, default to claude-code."""
    toml = """\
[butler]
name = "runtimebot"
port = 7003
"""
    config_dir = _write_toml(tmp_path, toml)
    cfg = load_config(config_dir)

    assert cfg.runtime.type == "claude-code"


def test_runtime_explicit_claude_code(tmp_path: Path):
    """Parse [runtime] section with explicit type = 'claude-code'."""
    toml = """\
[butler]
name = "ccbot"
port = 7004

[runtime]
type = "claude-code"
"""
    config_dir = _write_toml(tmp_path, toml)
    cfg = load_config(config_dir)

    assert cfg.runtime.type == "claude-code"


def test_runtime_codex(tmp_path: Path):
    """Parse [runtime] section with type = 'codex'."""
    toml = """\
[butler]
name = "codexbot"
port = 7005

[runtime]
type = "codex"
"""
    config_dir = _write_toml(tmp_path, toml)
    cfg = load_config(config_dir)

    assert cfg.runtime.type == "codex"


def test_runtime_gemini(tmp_path: Path):
    """Parse [runtime] section with type = 'gemini'."""
    toml = """\
[butler]
name = "geminibot"
port = 7006

[runtime]
type = "gemini"
"""
    config_dir = _write_toml(tmp_path, toml)
    cfg = load_config(config_dir)

    assert cfg.runtime.type == "gemini"


def test_runtime_invalid_type_raises_error(tmp_path: Path):
    """Invalid runtime type raises clear ConfigError at load time."""
    toml = """\
[butler]
name = "invalidbot"
port = 7007

[runtime]
type = "invalid-runtime"
"""
    config_dir = _write_toml(tmp_path, toml)

    with pytest.raises(ConfigError, match="Unknown runtime type 'invalid-runtime'"):
        load_config(config_dir)


def test_runtime_config_accessible_from_butler_config(tmp_path: Path):
    """Verify runtime config is accessible via config.runtime.type."""
    toml = """\
[butler]
name = "accessbot"
port = 7008

[runtime]
type = "gemini"
"""
    config_dir = _write_toml(tmp_path, toml)
    cfg = load_config(config_dir)

    # Can access runtime.type directly
    assert cfg.runtime.type == "gemini"

    # Runtime config is a RuntimeConfig instance
    from butlers.config import RuntimeConfig

    assert isinstance(cfg.runtime, RuntimeConfig)
