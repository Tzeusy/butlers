"""Wellness envelope ingest — translates ingest.v1 wellness envelopes into Health butler facts.

Receives a ``wellness/google_health`` ingest.v1 envelope (delivered by the connector
via the Switchboard → ``route.execute`` path) and deterministically converts it into
a single fact stored via ``memory_store_fact``.

Predicate taxonomy (mem_003):
  sleep_session, sleep_stage_summary,
  measurement_resting_hr, measurement_hrv, measurement_spo2,
  measurement_breathing_rate, measurement_steps, measurement_active_minutes,
  measurement_vo2_max

Prometheus counter ``health_wellness_ingest_total`` is incremented per call with
labels ``predicate`` and ``outcome`` (success | error | skipped_* | rejected_*).
"""

from __future__ import annotations

import logging
from typing import Any

from butlers.connectors.metrics import health_wellness_ingest_total
from butlers.credential_store import resolve_owner_entity_info
from butlers.modules.memory.tools.writing import memory_store_fact

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Predicate routing table
#
# Maps the resource segment of ``event.external_event_id`` (the part before the
# second colon, e.g. ``"sleep"`` from ``"google_health:sleep_session:abc123"``)
# to the canonical mem_003 predicate name.
#
# The connector emits external_event_id in these forms:
#   google_health:sleep_session:<session_id>   (sleep)
#   google_health:<resource>:<date>            (daily summaries)
# ---------------------------------------------------------------------------

_RESOURCE_TO_PREDICATE: dict[str, str] = {
    "sleep": "sleep_session",
    "sleep_session": "sleep_session",
    "sleep_stage": "sleep_stage_summary",
    "resting_hr": "measurement_resting_hr",
    "hrv": "measurement_hrv",
    "spo2": "measurement_spo2",
    "breathing_rate": "measurement_breathing_rate",
    "steps": "measurement_steps",
    "active_minutes": "measurement_active_minutes",
    "vo2_max": "measurement_vo2_max",
}

# ---------------------------------------------------------------------------
# Metadata extractors per predicate
# ---------------------------------------------------------------------------


def _extract_sleep_session_metadata(raw: dict[str, Any]) -> dict[str, Any]:
    """Extract structured metadata for a sleep session record.

    Requires at least a nonzero durationMillis (or duration_ms) field to be
    considered well-formed. Returns an empty dict when the duration is absent
    or zero, signalling that the record is malformed and should be skipped.
    """
    duration_ms = int(raw.get("durationMillis") or raw.get("duration_ms") or 0)
    if duration_ms == 0:
        # No usable duration — treat as malformed.
        return {}

    efficiency = raw.get("efficiency") or raw.get("efficiencyPercent")
    stages: dict[str, Any] = {}
    if "stages" in raw:
        stages = raw["stages"]
    elif "stageSummary" in raw:
        stages = raw["stageSummary"]

    meta: dict[str, Any] = {"duration_ms": duration_ms}
    if efficiency is not None:
        meta["efficiency"] = efficiency
    if stages:
        meta["stages"] = stages
    return meta


def _extract_sleep_stage_metadata(raw: dict[str, Any]) -> dict[str, Any]:
    """Extract structured metadata for a sleep stage summary record."""
    meta: dict[str, Any] = {}
    for key in ("stages", "stageSummary", "stage_summary"):
        val = raw.get(key)
        if val is not None:
            meta["stages"] = val
            break
    if "date" in raw:
        meta["date"] = raw["date"]
    return meta


def _extract_scalar_metadata(raw: dict[str, Any], unit: str) -> dict[str, Any]:
    """Extract a scalar value + unit from a daily-summary record."""
    value = None
    for key in ("value", "count", "avg", "average", "midpoint"):
        val = raw.get(key)
        if val is not None:
            value = val
            break
    meta: dict[str, Any] = {"unit": unit}
    if value is not None:
        meta["value"] = value
    return meta


_PREDICATE_UNIT: dict[str, str] = {
    "measurement_resting_hr": "bpm",
    "measurement_hrv": "ms",
    "measurement_spo2": "%",
    "measurement_breathing_rate": "breaths/min",
    "measurement_steps": "steps",
    "measurement_active_minutes": "minutes",
    "measurement_vo2_max": "ml/kg/min",
    "sleep_stage_summary": "",
}


def _extract_metadata(predicate: str, raw: dict[str, Any]) -> dict[str, Any]:
    """Dispatch metadata extraction to the appropriate extractor for *predicate*."""
    if predicate == "sleep_session":
        return _extract_sleep_session_metadata(raw)
    if predicate == "sleep_stage_summary":
        return _extract_sleep_stage_metadata(raw)
    unit = _PREDICATE_UNIT.get(predicate, "")
    return _extract_scalar_metadata(raw, unit)


# ---------------------------------------------------------------------------
# valid_at extraction
# ---------------------------------------------------------------------------


def _extract_valid_at(predicate: str, raw: dict[str, Any], observed_at: str) -> str:
    """Extract the most appropriate valid_at ISO string for a record.

    For sleep sessions: use session start time.
    For daily summaries: use the date field.
    Falls back to observed_at when no date field is present.
    """
    if predicate in ("sleep_session", "sleep_stage_summary"):
        for key in ("startTime", "start_time", "startAt", "start"):
            val = raw.get(key)
            if val:
                return str(val)
    else:
        # Daily summary — prefer the date the record applies to.
        for key in ("date", "startTime", "start_time"):
            val = raw.get(key)
            if val:
                val_str = str(val)
                # Normalise to ISO: if it's just YYYY-MM-DD append T00:00:00Z
                if "T" not in val_str and len(val_str) == 10:
                    return val_str + "T00:00:00Z"
                return val_str

    return observed_at


# ---------------------------------------------------------------------------
# Primary sender validation
# ---------------------------------------------------------------------------


async def _get_primary_google_identity(pool: Any) -> str | None:
    """Return the primary Google account's email from the DB, or None."""
    try:
        row = await pool.fetchrow(
            "SELECT email FROM public.google_accounts WHERE is_primary = true LIMIT 1"
        )
        if row is None:
            return None
        return row["email"]
    except Exception as exc:  # noqa: BLE001
        logger.warning("wellness_ingest: failed to query primary google account: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Main translation function
# ---------------------------------------------------------------------------


async def translate_wellness_envelope(
    pool: Any,
    embedding_engine: Any,
    envelope: dict[str, Any],
) -> dict[str, Any]:
    """Translate a wellness ingest.v1 envelope into a stored memory fact.

    Parameters
    ----------
    pool:
        asyncpg connection pool (health butler DB, with access to ``public`` schema).
    embedding_engine:
        Shared EmbeddingEngine instance (from memory module).
    envelope:
        An ingest.v1 envelope dict from the google_health connector.

    Returns
    -------
    dict with ``status`` and, on success, ``fact_id`` and ``predicate``.
    Possible statuses: ``ok``, ``rejected_non_primary_sender``,
    ``skipped_unknown_predicate``, ``skipped_malformed_payload``, ``error``.
    """
    # ------------------------------------------------------------------
    # Step 1: Validate primary sender
    # ------------------------------------------------------------------
    sender_identity: str = envelope.get("sender", {}).get("identity", "")
    primary_email = await _get_primary_google_identity(pool)
    if primary_email is None:
        logger.warning(
            "wellness_ingest: no primary Google account found; dropping envelope sender=%r",
            sender_identity,
        )
        health_wellness_ingest_total.labels(
            predicate="unknown", outcome="rejected_non_primary_sender"
        ).inc()
        return {"status": "rejected_non_primary_sender"}

    if sender_identity and sender_identity != primary_email:
        logger.warning(
            "wellness_ingest: sender %r is not the primary Google account %r; dropping",
            sender_identity,
            primary_email,
        )
        health_wellness_ingest_total.labels(
            predicate="unknown", outcome="rejected_non_primary_sender"
        ).inc()
        return {"status": "rejected_non_primary_sender"}

    # ------------------------------------------------------------------
    # Step 2: Resolve owner entity UUID
    # ------------------------------------------------------------------
    owner_entity_id_str = await resolve_owner_entity_info(pool, "owner")
    if owner_entity_id_str is None:
        # Also try querying public.entities directly (same as measurements.py)
        try:
            row = await pool.fetchrow(
                "SELECT id FROM public.entities WHERE 'owner' = ANY(roles) LIMIT 1"
            )
            if row is not None:
                owner_entity_id_str = str(row["id"])
        except Exception as exc:  # noqa: BLE001
            logger.warning("wellness_ingest: owner entity fallback query failed: %s", exc)

    if owner_entity_id_str is None:
        logger.warning("wellness_ingest: owner entity not found; dropping envelope")
        health_wellness_ingest_total.labels(predicate="unknown", outcome="error").inc()
        return {"status": "error", "reason": "owner_entity_not_found"}

    # ------------------------------------------------------------------
    # Step 3: Derive predicate from external_event_id
    # ------------------------------------------------------------------
    external_event_id: str = envelope.get("event", {}).get("external_event_id", "")
    # Format: "google_health:<resource>:<date_or_id>"
    parts = external_event_id.split(":", 2)
    resource_segment = parts[1] if len(parts) >= 2 else ""

    predicate = _RESOURCE_TO_PREDICATE.get(resource_segment)
    if predicate is None:
        logger.warning(
            "wellness_ingest: unknown resource segment %r in external_event_id %r; skipping",
            resource_segment,
            external_event_id,
        )
        health_wellness_ingest_total.labels(
            predicate=resource_segment or "unknown", outcome="skipped_unknown_predicate"
        ).inc()
        return {"status": "skipped_unknown_predicate"}

    # ------------------------------------------------------------------
    # Step 4: Extract valid_at and metadata
    # ------------------------------------------------------------------
    payload = envelope.get("payload", {})
    raw: dict[str, Any] = payload.get("raw") or {}
    observed_at: str = envelope.get("event", {}).get("observed_at", "")
    normalized_text: str = payload.get("normalized_text", "")

    valid_at = _extract_valid_at(predicate, raw, observed_at)

    try:
        metadata = _extract_metadata(predicate, raw)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "wellness_ingest: metadata extraction failed for predicate=%r: %s",
            predicate,
            exc,
        )
        health_wellness_ingest_total.labels(
            predicate=predicate, outcome="skipped_malformed_payload"
        ).inc()
        return {"status": "skipped_malformed_payload"}

    if not metadata:
        logger.warning(
            "wellness_ingest: empty metadata for predicate=%r; skipping",
            predicate,
        )
        health_wellness_ingest_total.labels(
            predicate=predicate, outcome="skipped_malformed_payload"
        ).inc()
        return {"status": "skipped_malformed_payload"}

    # ------------------------------------------------------------------
    # Step 5: Build content string and idempotency key
    # ------------------------------------------------------------------
    content = normalized_text or f"wellness:{predicate}:{valid_at}"
    idempotency_key: str = envelope.get("control", {}).get("idempotency_key", "")

    # ------------------------------------------------------------------
    # Step 6: Store fact
    # ------------------------------------------------------------------
    try:
        result = await memory_store_fact(
            pool,
            embedding_engine,
            subject="owner",
            predicate=predicate,
            content=content,
            scope="health",
            permanence="standard",
            valid_at=valid_at,
            entity_id=owner_entity_id_str,
            idempotency_key=idempotency_key or None,
            retention_class="operational",
            sensitivity="normal",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "wellness_ingest: memory_store_fact failed for predicate=%r: %s",
            predicate,
            exc,
        )
        health_wellness_ingest_total.labels(predicate=predicate, outcome="error").inc()
        return {"status": "error", "reason": str(exc)}

    health_wellness_ingest_total.labels(predicate=predicate, outcome="success").inc()
    return {
        "status": "ok",
        "fact_id": result.get("id"),
        "predicate": predicate,
    }
