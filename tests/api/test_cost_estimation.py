"""Tests for cost estimation dependency injection and helpers."""

from __future__ import annotations

import pytest

from butlers.api.pricing import PricingConfig, estimate_session_cost, load_pricing

pytestmark = pytest.mark.unit

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

VALID_TOML = """\
[models]

[models."claude-sonnet-4-5-20250929"]
input_price_per_token = 0.000003
output_price_per_token = 0.000015

[models."claude-haiku-4-5-20251001"]
input_price_per_token = 0.0000008
output_price_per_token = 0.000004
"""


@pytest.fixture()
def pricing_file(tmp_path):
    """Write a valid pricing.toml and return its path."""
    p = tmp_path / "pricing.toml"
    p.write_text(VALID_TOML)
    return p


@pytest.fixture()
def config(pricing_file):
    """Load a PricingConfig from the valid fixture file."""
    return load_pricing(pricing_file)


# ---------------------------------------------------------------------------
# estimate_session_cost
# ---------------------------------------------------------------------------


class TestEstimateSessionCost:
    def test_known_model_returns_correct_cost(self, config):
        # 1000 input * $3/1M + 500 output * $15/1M = 0.003 + 0.0075 = 0.0105
        cost = estimate_session_cost(
            config,
            model_id="claude-sonnet-4-5-20250929",
            input_tokens=1000,
            output_tokens=500,
        )
        assert cost == pytest.approx(0.0105)

    def test_unknown_model_returns_zero(self, config):
        cost = estimate_session_cost(
            config,
            model_id="nonexistent-model",
            input_tokens=1000,
            output_tokens=500,
        )
        assert cost == 0.0

    def test_zero_tokens(self, config):
        cost = estimate_session_cost(
            config,
            model_id="claude-sonnet-4-5-20250929",
            input_tokens=0,
            output_tokens=0,
        )
        assert cost == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Dependency injection: init_pricing / get_pricing
# ---------------------------------------------------------------------------


class TestPricingDependency:
    def test_get_pricing_raises_before_init(self):
        """get_pricing raises RuntimeError when called before init_pricing."""
        import butlers.api.deps as deps_mod

        # Ensure clean state
        original = deps_mod._pricing_config
        deps_mod._pricing_config = None
        try:
            with pytest.raises(RuntimeError, match="PricingConfig not initialized"):
                deps_mod.get_pricing()
        finally:
            deps_mod._pricing_config = original

    def test_init_pricing_loads_config(self, pricing_file):
        """init_pricing loads the given pricing.toml and returns a PricingConfig."""
        import butlers.api.deps as deps_mod

        original = deps_mod._pricing_config
        try:
            result = deps_mod.init_pricing(pricing_file)
            assert isinstance(result, PricingConfig)
            assert len(result.model_ids) == 2
        finally:
            deps_mod._pricing_config = original

    def test_get_pricing_returns_config_after_init(self, pricing_file):
        """After init_pricing, get_pricing returns the same PricingConfig."""
        import butlers.api.deps as deps_mod

        original = deps_mod._pricing_config
        try:
            expected = deps_mod.init_pricing(pricing_file)
            actual = deps_mod.get_pricing()
            assert actual is expected
        finally:
            deps_mod._pricing_config = original

    def test_init_pricing_loads_default_repo_toml(self):
        """init_pricing with no path loads the repo-root pricing.toml."""
        import butlers.api.deps as deps_mod

        original = deps_mod._pricing_config
        try:
            result = deps_mod.init_pricing()
            assert isinstance(result, PricingConfig)
            assert len(result.model_ids) >= 1
        finally:
            deps_mod._pricing_config = original
