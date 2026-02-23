"""Comprehensive tests for cost estimation and cost endpoint models."""

from __future__ import annotations

import pytest

from butlers.api.models import CostSummary, DailyCost, TopSession
from butlers.api.pricing import (
    ModelPricing,
    PricingConfig,
    PricingError,
    estimate_session_cost,
    load_pricing,
)

pytestmark = pytest.mark.unit


class TestPricingConfig:
    def test_model_ids_sorted(self):
        config = PricingConfig(
            {
                "z-model": ModelPricing(0.001, 0.002),
                "a-model": ModelPricing(0.003, 0.004),
            }
        )
        assert config.model_ids == ["a-model", "z-model"]

    def test_get_model_pricing_returns_none_for_unknown(self):
        config = PricingConfig({})
        assert config.get_model_pricing("nonexistent") is None

    def test_get_model_pricing_returns_correct_pricing(self):
        mp = ModelPricing(0.000003, 0.000015)
        config = PricingConfig({"claude-sonnet": mp})
        result = config.get_model_pricing("claude-sonnet")
        assert result is mp

    def test_estimate_cost_known_model(self):
        config = PricingConfig(
            {
                "test-model": ModelPricing(0.000003, 0.000015),
            }
        )
        cost = config.estimate_cost("test-model", 1000, 500)
        expected = 0.000003 * 1000 + 0.000015 * 500
        assert cost == pytest.approx(expected)

    def test_estimate_cost_unknown_model_returns_none(self):
        config = PricingConfig({})
        assert config.estimate_cost("unknown", 100, 50) is None

    def test_estimate_cost_zero_tokens(self):
        config = PricingConfig(
            {
                "test-model": ModelPricing(0.000003, 0.000015),
            }
        )
        assert config.estimate_cost("test-model", 0, 0) == 0.0

    def test_estimate_cost_large_tokens(self):
        config = PricingConfig(
            {
                "test-model": ModelPricing(0.000003, 0.000015),
            }
        )
        cost = config.estimate_cost("test-model", 1_000_000, 500_000)
        expected = 0.000003 * 1_000_000 + 0.000015 * 500_000
        assert cost == pytest.approx(expected)


class TestEstimateSessionCost:
    def test_known_model_returns_positive(self):
        config = PricingConfig(
            {
                "model-a": ModelPricing(0.000003, 0.000015),
            }
        )
        result = estimate_session_cost(config, "model-a", 1000, 500)
        assert result > 0

    def test_unknown_model_returns_zero(self):
        config = PricingConfig({})
        result = estimate_session_cost(config, "unknown", 1000, 500)
        assert result == 0.0

    def test_matches_direct_estimate(self):
        config = PricingConfig(
            {
                "model-a": ModelPricing(0.000003, 0.000015),
            }
        )
        direct = config.estimate_cost("model-a", 1000, 500)
        helper = estimate_session_cost(config, "model-a", 1000, 500)
        assert direct == helper


class TestLoadPricing:
    def test_loads_default_pricing_toml(self):
        config = load_pricing()
        assert len(config.model_ids) >= 1

    def test_missing_file_raises_error(self, tmp_path):
        with pytest.raises(PricingError, match="not found"):
            load_pricing(tmp_path / "nonexistent.toml")

    def test_invalid_toml_raises_error(self, tmp_path):
        bad_file = tmp_path / "bad.toml"
        bad_file.write_text("not valid [[[toml")
        with pytest.raises(PricingError, match="Invalid TOML"):
            load_pricing(bad_file)

    def test_missing_models_section_raises_error(self, tmp_path):
        toml_file = tmp_path / "pricing.toml"
        toml_file.write_text("[other]\nkey = 1\n")
        with pytest.raises(PricingError, match="Missing.*models"):
            load_pricing(toml_file)

    def test_missing_price_field_raises_error(self, tmp_path):
        toml_file = tmp_path / "pricing.toml"
        toml_file.write_text('[models]\n[models."bad-model"]\ninput_price_per_token = 0.001\n')
        with pytest.raises(PricingError, match="Missing required field"):
            load_pricing(toml_file)

    def test_valid_custom_pricing(self, tmp_path):
        toml_file = tmp_path / "pricing.toml"
        toml_file.write_text(
            "[models]\n"
            '[models."my-model"]\n'
            "input_price_per_token = 0.001\n"
            "output_price_per_token = 0.002\n"
        )
        config = load_pricing(toml_file)
        assert "my-model" in config.model_ids
        pricing = config.get_model_pricing("my-model")
        assert pricing.input_price_per_token == 0.001
        assert pricing.output_price_per_token == 0.002


class TestCostModels:
    def test_cost_summary_defaults(self):
        s = CostSummary(
            total_cost_usd=0.0,
            total_sessions=0,
            total_input_tokens=0,
            total_output_tokens=0,
        )
        assert s.by_butler == {}
        assert s.by_model == {}

    def test_cost_summary_with_breakdown(self):
        s = CostSummary(
            total_cost_usd=1.5,
            total_sessions=10,
            total_input_tokens=100000,
            total_output_tokens=50000,
            by_butler={"switchboard": 1.0, "general": 0.5},
            by_model={"claude-sonnet": 1.5},
        )
        assert s.by_butler["switchboard"] == 1.0
        assert sum(s.by_butler.values()) == pytest.approx(s.total_cost_usd)

    def test_cost_summary_json_round_trip(self):
        s = CostSummary(
            total_cost_usd=2.34,
            total_sessions=5,
            total_input_tokens=50000,
            total_output_tokens=25000,
        )
        restored = CostSummary.model_validate_json(s.model_dump_json())
        assert restored == s

    def test_daily_cost_model(self):
        d = DailyCost(
            date="2026-02-10",
            cost_usd=0.45,
            sessions=3,
            input_tokens=10000,
            output_tokens=5000,
        )
        assert d.date == "2026-02-10"
        assert d.cost_usd == 0.45

    def test_daily_cost_json_round_trip(self):
        d = DailyCost(
            date="2026-02-09",
            cost_usd=1.23,
            sessions=7,
            input_tokens=50000,
            output_tokens=25000,
        )
        restored = DailyCost.model_validate_json(d.model_dump_json())
        assert restored == d

    def test_top_session_model(self):
        t = TopSession(
            session_id="abc-123",
            butler="switchboard",
            cost_usd=0.89,
            input_tokens=30000,
            output_tokens=15000,
            model="claude-sonnet-4-5-20250929",
            started_at="2026-02-10T10:30:00Z",
        )
        assert t.butler == "switchboard"
        assert t.model == "claude-sonnet-4-5-20250929"

    def test_top_session_json_round_trip(self):
        t = TopSession(
            session_id="def-456",
            butler="general",
            cost_usd=2.34,
            input_tokens=100000,
            output_tokens=50000,
            model="claude-opus-4-6",
            started_at="2026-02-10T09:00:00Z",
        )
        restored = TopSession.model_validate_json(t.model_dump_json())
        assert restored == t


class TestModelPricingDataclass:
    def test_frozen(self):
        mp = ModelPricing(0.001, 0.002)
        with pytest.raises(AttributeError):
            mp.input_price_per_token = 0.003

    def test_values(self):
        mp = ModelPricing(0.000003, 0.000015)
        assert mp.input_price_per_token == 0.000003
        assert mp.output_price_per_token == 0.000015
