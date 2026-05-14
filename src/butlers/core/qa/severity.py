"""QA case severity labels and dossier helper utilities."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Any, Literal

from butlers.core.qa.models import QaFinding
from butlers.core.qa.notes import InvestigationNotes

SeverityLabel = Literal["high", "medium", "low"]
CaseState = Literal["detect", "diagnose", "pr", "landed", "escalated"]


def map_severity(severity: int) -> SeverityLabel:
    """Map the stored 0..4 QA severity integer into a dossier label."""

    if severity in (0, 1):
        return "high"
    if severity == 2:
        return "medium"
    if severity in (3, 4):
        return "low"
    raise ValueError(f"Unknown QA severity: {severity}")


def short_id_from_uuid(value: uuid.UUID) -> str:
    """Return a stable ``#NNN`` ID from a UUIDv7 timestamp.

    UUIDv7 stores its Unix epoch millisecond timestamp in the high 48 bits.
    The dossier short ID uses the lowest three decimal digits of that timestamp
    portion, so it is deterministic for a given attempt UUID while staying
    compact enough for the case rail.
    """

    timestamp_ms = value.int >> 80
    return f"#{timestamp_ms % 1000:03d}"


def state_of_case(attempt: Mapping[str, Any] | object) -> CaseState:
    """Map a healing attempt row or object into the QA dossier state track."""

    status = _get_field(attempt, "status")
    if status == "pr_merged":
        return "landed"
    if status in {"pr_open", "drafted"}:
        return "pr"
    if status == "unfixable" or _failed_with_human_action(attempt):
        return "escalated"
    if status == "investigating":
        return "diagnose"
    return "detect"


def headline_for_case(attempt: Mapping[str, Any] | object, finding: QaFinding | None) -> str:
    """Choose the best available human headline for a QA case."""

    headline = _investigation_notes_headline(finding)
    if headline:
        return headline

    event_summary = getattr(finding, "event_summary", None) if finding is not None else None
    if event_summary:
        return event_summary

    exception_type = _get_field(attempt, "exception_type") or "UnknownError"
    butler_name = _get_field(attempt, "butler_name") or "unknown"
    return f"{exception_type} in {butler_name}"


def _failed_with_human_action(attempt: Mapping[str, Any] | object) -> bool:
    status = _get_field(attempt, "status")
    detail = _get_field(attempt, "error_detail")
    return status == "failed" and isinstance(detail, str) and "human action" in detail.lower()


def _investigation_notes_headline(finding: QaFinding | None) -> str | None:
    if finding is None:
        return None

    structured_evidence = finding.structured_evidence
    if not isinstance(structured_evidence, Mapping):
        return None

    notes = structured_evidence.get("investigation_notes")
    if isinstance(notes, InvestigationNotes):
        return notes.headline or None
    if isinstance(notes, Mapping):
        headline = notes.get("headline")
        if isinstance(headline, str) and headline:
            return headline
    return None


def _get_field(source: Mapping[str, Any] | object, field: str) -> Any:
    if isinstance(source, Mapping):
        return source.get(field)
    return getattr(source, field, None)
