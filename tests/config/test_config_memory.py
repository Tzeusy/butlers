"""Tests for MemoryConfig dataclass and [butler.memory] config parsing.

Covers:
- MemoryConfig defaults (enabled=True, port=8150, etc.)
- load_config parses [butler.memory] section
- load_config uses defaults when [butler.memory] absent
- load_config parses [butler.memory.retrieval] score_weights
- Custom port and token_budget are respected
"""

from __future__ import annotations

from pathlib import Path

import pytest

from butlers.config import ButlerConfig, MemoryConfig, load_config

pytestmark = pytest.mark.unit

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_toml(tmp_path: Path, content: str) -> Path:
    """Write *content* to a butler.toml inside *tmp_path* and return the directory."""
    (tmp_path / "butler.toml").write_text(content)
    return tmp_path


# ---------------------------------------------------------------------------
# MemoryConfig dataclass defaults
# ---------------------------------------------------------------------------


class TestMemoryConfigDefaults:
    """Tests for MemoryConfig default values."""

    def test_enabled_default(self):
        """MemoryConfig defaults enabled to True."""
        mc = MemoryConfig()
        assert mc.enabled is True

    def test_port_default(self):
        """MemoryConfig defaults port to 8150."""
        mc = MemoryConfig()
        assert mc.port == 8150

    def test_context_token_budget_default(self):
        """MemoryConfig defaults context_token_budget to 3000."""
        mc = MemoryConfig()
        assert mc.context_token_budget == 3000

    def test_retrieval_limit_default(self):
        """MemoryConfig defaults retrieval_limit to 20."""
        mc = MemoryConfig()
        assert mc.retrieval_limit == 20

    def test_retrieval_mode_default(self):
        """MemoryConfig defaults retrieval_mode to 'hybrid'."""
        mc = MemoryConfig()
        assert mc.retrieval_mode == "hybrid"

    def test_score_weights_default(self):
        """MemoryConfig defaults score_weights to standard distribution."""
        mc = MemoryConfig()
        assert mc.score_weights == {
            "relevance": 0.4,
            "importance": 0.3,
            "recency": 0.2,
            "confidence": 0.1,
        }

    def test_butler_config_memory_default(self):
        """ButlerConfig defaults memory to a MemoryConfig with all defaults."""
        cfg = ButlerConfig(name="test", port=9000)
        assert isinstance(cfg.memory, MemoryConfig)
        assert cfg.memory.enabled is True
        assert cfg.memory.port == 8150


# ---------------------------------------------------------------------------
# load_config parses [butler.memory] section
# ---------------------------------------------------------------------------


class TestLoadConfigMemory:
    """Tests for load_config parsing of [butler.memory]."""

    def test_parses_memory_section(self, tmp_path: Path):
        """load_config parses [butler.memory] enabled and port."""
        toml = """\
[butler]
name = "membot"
port = 8200

[butler.memory]
enabled = false
port = 9999
"""
        config_dir = _write_toml(tmp_path, toml)
        cfg = load_config(config_dir)

        assert cfg.memory.enabled is False
        assert cfg.memory.port == 9999

    def test_defaults_when_memory_absent(self, tmp_path: Path):
        """load_config uses MemoryConfig defaults when [butler.memory] absent."""
        toml = """\
[butler]
name = "nomembot"
port = 8201
"""
        config_dir = _write_toml(tmp_path, toml)
        cfg = load_config(config_dir)

        assert cfg.memory.enabled is True
        assert cfg.memory.port == 8150
        assert cfg.memory.context_token_budget == 3000
        assert cfg.memory.retrieval_limit == 20
        assert cfg.memory.retrieval_mode == "hybrid"

    def test_parses_retrieval_section(self, tmp_path: Path):
        """load_config parses [butler.memory.retrieval] sub-section."""
        toml = """\
[butler]
name = "retbot"
port = 8202

[butler.memory]
enabled = true

[butler.memory.retrieval]
context_token_budget = 5000
default_limit = 50
default_mode = "semantic"
"""
        config_dir = _write_toml(tmp_path, toml)
        cfg = load_config(config_dir)

        assert cfg.memory.context_token_budget == 5000
        assert cfg.memory.retrieval_limit == 50
        assert cfg.memory.retrieval_mode == "semantic"

    def test_parses_retrieval_score_weights(self, tmp_path: Path):
        """load_config parses [butler.memory.retrieval] score_weights."""
        toml = """\
[butler]
name = "scorebot"
port = 8203

[butler.memory.retrieval]
[butler.memory.retrieval.score_weights]
relevance = 0.5
importance = 0.2
recency = 0.2
confidence = 0.1
"""
        config_dir = _write_toml(tmp_path, toml)
        cfg = load_config(config_dir)

        assert cfg.memory.score_weights == {
            "relevance": 0.5,
            "importance": 0.2,
            "recency": 0.2,
            "confidence": 0.1,
        }

    def test_custom_port_and_token_budget(self, tmp_path: Path):
        """Custom port and context_token_budget are respected."""
        toml = """\
[butler]
name = "custombot"
port = 8204

[butler.memory]
port = 8200

[butler.memory.retrieval]
context_token_budget = 10000
"""
        config_dir = _write_toml(tmp_path, toml)
        cfg = load_config(config_dir)

        assert cfg.memory.port == 8200
        assert cfg.memory.context_token_budget == 10000

    def test_score_weights_default_when_retrieval_absent(self, tmp_path: Path):
        """Score weights use defaults when [butler.memory.retrieval] absent."""
        toml = """\
[butler]
name = "noretbot"
port = 8205

[butler.memory]
enabled = true
"""
        config_dir = _write_toml(tmp_path, toml)
        cfg = load_config(config_dir)

        assert cfg.memory.score_weights == MemoryConfig().score_weights

    def test_partial_memory_section(self, tmp_path: Path):
        """Only some fields set in [butler.memory]; rest default."""
        toml = """\
[butler]
name = "partialbot"
port = 8206

[butler.memory]
enabled = true
port = 7777
"""
        config_dir = _write_toml(tmp_path, toml)
        cfg = load_config(config_dir)

        assert cfg.memory.enabled is True
        assert cfg.memory.port == 7777
        # Retrieval defaults still apply
        assert cfg.memory.context_token_budget == 3000
        assert cfg.memory.retrieval_limit == 20
        assert cfg.memory.retrieval_mode == "hybrid"
