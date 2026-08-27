"""Keep secrets-router contract citations on live OpenSpec baselines.

The router's endpoint docstrings are a maintainer-facing trace from the
interface to the behaviour it implements.  An archived change directory is
historical evidence, not a live contract, so this guard deliberately inspects
only ``secrets_v2.py`` docstrings labelled ``Spec anchor``.  It does not create
a repository-wide documentation policy or reinterpret other citation forms.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SECRETS_V2 = _REPO_ROOT / "src" / "butlers" / "api" / "routers" / "secrets_v2.py"
_SPEC_ANCHOR_HEADING = re.compile(r"^Spec anchor\s*$", re.MULTILINE)
_SPEC_PATH = re.compile(r"^\s*(openspec/[^\s]+/spec\.md)\s*$", re.MULTILINE)


def _spec_anchor_docstrings() -> list[tuple[str, str]]:
    """Return the named interface docstrings that declare a Spec anchor."""
    tree = ast.parse(_SECRETS_V2.read_text(encoding="utf-8"), filename=str(_SECRETS_V2))
    anchored: list[tuple[str, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Module | ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            continue
        docstring = ast.get_docstring(node)
        if docstring is None or _SPEC_ANCHOR_HEADING.search(docstring) is None:
            continue
        name = getattr(node, "name", "module")
        anchored.append((name, docstring))
    return anchored


def test_secrets_v2_spec_anchors_resolve_to_live_baseline_specs() -> None:
    """Every labelled router anchor names at least one existing baseline spec."""
    findings: list[str] = []
    anchored = _spec_anchor_docstrings()
    assert anchored, "secrets_v2.py has no Spec anchor docstrings to verify"

    for name, docstring in anchored:
        heading = _SPEC_ANCHOR_HEADING.search(docstring)
        assert heading is not None  # narrowed above; preserves the type invariant.
        paths = _SPEC_PATH.findall(docstring[heading.end() :])
        if not paths:
            findings.append(f"{name}: Spec anchor names no OpenSpec baseline path")
            continue
        for path in paths:
            if not path.startswith("openspec/specs/"):
                findings.append(f"{name}: {path} is not a live baseline path")
            elif not (_REPO_ROOT / path).is_file():
                findings.append(f"{name}: {path} does not exist")

    assert not findings, "secrets_v2.py Spec anchor drift:\n" + "\n".join(findings)
