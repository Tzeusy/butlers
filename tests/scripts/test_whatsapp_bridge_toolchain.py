"""Contracts for the Go toolchain used to build the WhatsApp bridge."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


def test_module_go_release_matches_pinned_builder_release() -> None:
    go_mod = Path("whatsapp-bridge/go.mod").read_text(encoding="utf-8")
    dockerfile = Path("Dockerfile").read_text(encoding="utf-8")

    module_version = re.search(r"^go (\d+)\.(\d+)(?:\.\d+)?$", go_mod, re.MULTILINE)
    builder_version = re.search(
        r"^FROM golang:(\d+)\.(\d+)-bookworm@sha256:", dockerfile, re.MULTILINE
    )

    assert module_version is not None
    assert builder_version is not None
    assert module_version.groups() == builder_version.groups()
