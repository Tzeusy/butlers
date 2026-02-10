"""Tests for the Memory butler EmbeddingEngine."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# Load the embedding module from disk (roster/ is not a Python package).
# ---------------------------------------------------------------------------
_EMBEDDING_PATH = Path(__file__).resolve().parent.parent / "embedding.py"


def _load_embedding_module():
    spec = importlib.util.spec_from_file_location("embedding", _EMBEDDING_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_mod = _load_embedding_module()
EmbeddingEngine = _mod.EmbeddingEngine

# ---------------------------------------------------------------------------
# Unit tests -- mock the model for speed
# ---------------------------------------------------------------------------


def _fake_encode(texts, **_kwargs):
    """Return deterministic fake vectors matching model output shape."""
    if isinstance(texts, str):
        return np.zeros(384, dtype=np.float32)
    return np.zeros((len(texts), 384), dtype=np.float32)


@pytest.fixture()
def engine():
    """Return an EmbeddingEngine with the model replaced by a mock."""
    with patch.object(_mod, "SentenceTransformer") as mock_cls:
        mock_model = MagicMock()
        mock_model.encode = MagicMock(side_effect=_fake_encode)
        mock_cls.return_value = mock_model
        eng = EmbeddingEngine()
        yield eng


@pytest.mark.unit
class TestEmbedUnit:
    def test_embed_returns_list_of_floats(self, engine):
        result = engine.embed("hello world")
        assert isinstance(result, list)
        assert len(result) == 384
        assert all(isinstance(v, float) for v in result)

    def test_embed_empty_string(self, engine):
        """Empty strings should not crash; they get normalised to a space."""
        result = engine.embed("")
        assert isinstance(result, list)
        assert len(result) == 384

    def test_embed_none(self, engine):
        """None should be handled gracefully."""
        result = engine.embed(None)
        assert isinstance(result, list)
        assert len(result) == 384

    def test_embed_whitespace_only(self, engine):
        result = engine.embed("   ")
        assert len(result) == 384


@pytest.mark.unit
class TestEmbedBatchUnit:
    def test_batch_returns_correct_count(self, engine):
        texts = ["one", "two", "three"]
        result = engine.embed_batch(texts)
        assert len(result) == 3
        assert all(len(v) == 384 for v in result)

    def test_batch_empty_list(self, engine):
        result = engine.embed_batch([])
        assert result == []

    def test_batch_with_none_elements(self, engine):
        result = engine.embed_batch([None, "hello", ""])
        assert len(result) == 3
        assert all(len(v) == 384 for v in result)

    def test_batch_single_item(self, engine):
        result = engine.embed_batch(["solo"])
        assert len(result) == 1
        assert len(result[0]) == 384


@pytest.mark.unit
class TestDimension:
    def test_dimension_property(self, engine):
        assert engine.dimension == 384


# ---------------------------------------------------------------------------
# Integration tests -- load the real model (slow, needs download)
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestEmbedIntegration:
    @pytest.fixture(scope="class")
    def real_engine(self):
        """Load the real model once per test class."""
        return EmbeddingEngine()

    def test_real_embed_dimension(self, real_engine):
        vec = real_engine.embed("The quick brown fox jumps over the lazy dog.")
        assert len(vec) == 384
        assert all(isinstance(v, float) for v in vec)

    def test_real_embed_different_texts_differ(self, real_engine):
        v1 = real_engine.embed("cats")
        v2 = real_engine.embed("quantum mechanics")
        assert v1 != v2

    def test_real_embed_batch(self, real_engine):
        vecs = real_engine.embed_batch(["alpha", "beta", "gamma"])
        assert len(vecs) == 3
        assert all(len(v) == 384 for v in vecs)

    def test_real_embed_empty_string(self, real_engine):
        vec = real_engine.embed("")
        assert len(vec) == 384
