"""Tests for roster/health/tools/wellness_ingest.py.

Covers:
1. Predicate derivation for all 9 resources (happy path + unknown resource)
2. Non-primary sender rejection
3. Replay-idempotency (same idempotency_key → no duplicate)
4. Malformed payload (missing required field) → skipped_malformed_payload
5. Prometheus counter increments with correct labels

All tests are unit tests (no DB required) — DB calls are mocked.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Envelope builder helpers
# ---------------------------------------------------------------------------


def _make_sleep_envelope(
    session_id: str = "sess-abc",
    sender_identity: str = "user@example.com",
    idempotency_key: str | None = None,
    raw: dict | None = None,
) -> dict:
    """Build a minimal sleep session ingest.v1 envelope."""
    return {
        "schema_version": "ingest.v1",
        "source": {
            "channel": "wellness",
            "provider": "google_health",
            "endpoint_identity": f"google_health:user:{sender_identity}",
        },
        "event": {
            "external_event_id": f"google_health:sleep_session:{session_id}",
            "external_thread_id": None,
            "observed_at": "2026-04-25T06:00:00Z",
        },
        "sender": {"identity": sender_identity},
        "payload": {
            "raw": raw
            if raw is not None
            else {
                "durationMillis": 25200000,
                "efficiency": 87,
                "startTime": "2026-04-24T23:00:00Z",
            },
            "normalized_text": "Slept 7h 0m (87% efficiency)",
        },
        "control": {
            "idempotency_key": idempotency_key or f"google_health:sleep:{session_id}",
            "policy_tier": "default",
            "ingestion_tier": "full",
        },
    }


def _make_daily_envelope(
    resource: str,
    record_date: str = "2026-04-24",
    sender_identity: str = "user@example.com",
    raw: dict | None = None,
) -> dict:
    """Build a minimal daily-summary ingest.v1 envelope."""
    return {
        "schema_version": "ingest.v1",
        "source": {
            "channel": "wellness",
            "provider": "google_health",
            "endpoint_identity": f"google_health:user:{sender_identity}",
        },
        "event": {
            "external_event_id": f"google_health:{resource}:{record_date}",
            "external_thread_id": None,
            "observed_at": "2026-04-25T06:00:00Z",
        },
        "sender": {"identity": sender_identity},
        "payload": {
            "raw": raw if raw is not None else {"value": 62, "date": record_date},
            "normalized_text": f"{resource}: 62",
        },
        "control": {
            "idempotency_key": f"google_health:{resource}:{record_date}",
            "policy_tier": "default",
            "ingestion_tier": "full",
        },
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_pool():
    """Mock asyncpg pool that returns a primary account row and owner entity row."""
    pool = AsyncMock()
    pool.fetchrow.side_effect = _default_fetchrow
    return pool


async def _default_fetchrow(query: str, *args, **kwargs):
    """Default fetchrow that returns primary account or owner entity based on query."""
    if "google_accounts" in query:
        row = MagicMock()
        row.__getitem__ = MagicMock(
            side_effect=lambda k: "user@example.com" if k == "email" else None
        )
        return row
    if "public.entities" in query:
        row = MagicMock()
        row.__getitem__ = MagicMock(side_effect=lambda k: str(uuid.uuid4()) if k == "id" else None)
        return row
    return None


@pytest.fixture
def mock_embedding_engine():
    return MagicMock()


@pytest.fixture
def store_fact_result():
    return {"id": str(uuid.uuid4()), "superseded_id": None}


# ---------------------------------------------------------------------------
# Helper to call translate_wellness_envelope with standard mocks
# ---------------------------------------------------------------------------


async def _call_translate(
    envelope: dict,
    pool=None,
    embedding_engine=None,
    store_fact_return=None,
) -> dict:
    """Call translate_wellness_envelope with mocked dependencies."""
    from butlers.tools.health.wellness_ingest import translate_wellness_envelope

    if pool is None:
        pool = AsyncMock()

        async def _fetchrow(query, *args, **kwargs):
            if "google_accounts" in query:
                row = MagicMock()
                row.__getitem__ = MagicMock(
                    side_effect=lambda k: "user@example.com" if k == "email" else None
                )
                return row
            if "public.entities" in query:
                row = MagicMock()
                row.__getitem__ = MagicMock(
                    side_effect=lambda k: str(uuid.uuid4()) if k == "id" else None
                )
                return row
            return None

        pool.fetchrow.side_effect = _fetchrow

    if embedding_engine is None:
        embedding_engine = MagicMock()

    sf_result = store_fact_return or {"id": str(uuid.uuid4()), "superseded_id": None}

    with (
        patch(
            "butlers.tools.health.wellness_ingest.resolve_owner_entity_info",
            new_callable=AsyncMock,
            return_value=str(uuid.uuid4()),
        ),
        patch(
            "butlers.tools.health.wellness_ingest.memory_store_fact",
            new_callable=AsyncMock,
            return_value=sf_result,
        ) as mock_store,
        patch("butlers.tools.health.wellness_ingest.health_wellness_ingest_total") as mock_counter,
    ):
        result = await translate_wellness_envelope(pool, embedding_engine, envelope)
        return result, mock_store, mock_counter


# ---------------------------------------------------------------------------
# 1. Predicate derivation for all 9 resources
# ---------------------------------------------------------------------------


class TestPredicateDerivation:
    """All 9 canonical wellness predicates are correctly derived."""

    @pytest.mark.parametrize(
        "resource,expected_predicate",
        [
            ("sleep_session", "sleep_session"),
            ("sleep_stage", "sleep_stage_summary"),
            ("resting_hr", "measurement_resting_hr"),
            ("hrv", "measurement_hrv"),
            ("spo2", "measurement_spo2"),
            ("breathing_rate", "measurement_breathing_rate"),
            ("steps", "measurement_steps"),
            ("active_minutes", "measurement_active_minutes"),
            ("vo2_max", "measurement_vo2_max"),
        ],
    )
    async def test_predicate_happy_path(self, resource: str, expected_predicate: str) -> None:
        """Each of the 9 resources maps to its canonical predicate and returns status=ok."""
        if resource == "sleep_session":
            # sleep_session → category=sleep, needs session_id style event_id
            envelope = _make_sleep_envelope()
            # Override external_event_id to use sleep_session resource segment
            envelope["event"]["external_event_id"] = "google_health:sleep_session:sess-1"
        else:
            # sleep_stage needs extra raw fields
            raw: dict = {"value": 62, "date": "2026-04-24"}
            if resource == "sleep_stage":
                raw = {"stages": {"deep": 90, "rem": 45, "light": 180}, "date": "2026-04-24"}
            envelope = _make_daily_envelope(resource, raw=raw)

        result, mock_store, mock_counter = await _call_translate(envelope)

        assert result["status"] == "ok", f"Expected ok for {resource}, got {result}"
        assert result["predicate"] == expected_predicate
        assert "fact_id" in result
        mock_store.assert_awaited_once()
        call_kwargs = mock_store.call_args
        # Verify predicate passed to memory_store_fact
        assert call_kwargs.kwargs.get("predicate") == expected_predicate or (
            len(call_kwargs.args) >= 4 and call_kwargs.args[3] == expected_predicate
        )

    async def test_unknown_resource_returns_skipped(self) -> None:
        """Unknown resource segment returns skipped_unknown_predicate."""
        envelope = _make_daily_envelope("unknown_resource")
        result, mock_store, mock_counter = await _call_translate(envelope)

        assert result["status"] == "skipped_unknown_predicate"
        mock_store.assert_not_awaited()
        mock_counter.labels.assert_called_once()
        label_call = mock_counter.labels.call_args
        assert label_call.kwargs.get("outcome") == "skipped_unknown_predicate"


# ---------------------------------------------------------------------------
# 2. Non-primary sender rejection
# ---------------------------------------------------------------------------


class TestSenderRejection:
    async def test_non_primary_sender_rejected(self) -> None:
        """Sender that doesn't match primary account is rejected."""
        envelope = _make_sleep_envelope(sender_identity="other@example.com")
        # Pool returns "user@example.com" as primary; envelope sender is different

        from butlers.tools.health.wellness_ingest import translate_wellness_envelope

        pool = AsyncMock()

        async def _fetchrow(query, *args, **kwargs):
            if "google_accounts" in query:
                row = MagicMock()
                row.__getitem__ = MagicMock(
                    side_effect=lambda k: "user@example.com" if k == "email" else None
                )
                return row
            return None

        pool.fetchrow.side_effect = _fetchrow

        with patch(
            "butlers.tools.health.wellness_ingest.health_wellness_ingest_total"
        ) as mock_counter:
            result = await translate_wellness_envelope(pool, MagicMock(), envelope)

        assert result["status"] == "rejected_non_primary_sender"
        mock_counter.labels.assert_called_once()
        label_call = mock_counter.labels.call_args
        assert label_call.kwargs.get("outcome") == "rejected_non_primary_sender"

    async def test_no_primary_account_rejects(self) -> None:
        """When primary account is not found, envelope is rejected."""
        from butlers.tools.health.wellness_ingest import translate_wellness_envelope

        pool = AsyncMock()
        pool.fetchrow.return_value = None  # no primary account

        with patch("butlers.tools.health.wellness_ingest.health_wellness_ingest_total"):
            result = await translate_wellness_envelope(pool, MagicMock(), _make_sleep_envelope())

        assert result["status"] == "rejected_non_primary_sender"


# ---------------------------------------------------------------------------
# 3. Replay idempotency
# ---------------------------------------------------------------------------


class TestReplayIdempotency:
    async def test_idempotency_key_forwarded_to_store_fact(self) -> None:
        """idempotency_key from control is forwarded to memory_store_fact."""
        envelope = _make_sleep_envelope(idempotency_key="google_health:sleep:sess-abc")
        result, mock_store, _ = await _call_translate(envelope)

        assert result["status"] == "ok"
        call_kwargs = mock_store.call_args
        assert call_kwargs.kwargs.get("idempotency_key") == "google_health:sleep:sess-abc"

    async def test_second_call_uses_same_idempotency_key(self) -> None:
        """Two calls with the same idempotency_key both forward it to store_fact.

        The store_fact layer is responsible for deduplication; we verify the key
        is forwarded consistently across both calls.
        """
        ikey = "google_health:sleep:sess-replay"
        envelope = _make_sleep_envelope(session_id="sess-replay", idempotency_key=ikey)

        with (
            patch(
                "butlers.tools.health.wellness_ingest.resolve_owner_entity_info",
                new_callable=AsyncMock,
                return_value=str(uuid.uuid4()),
            ),
            patch(
                "butlers.tools.health.wellness_ingest.memory_store_fact",
                new_callable=AsyncMock,
                return_value={"id": str(uuid.uuid4()), "superseded_id": None},
            ) as mock_store,
            patch("butlers.tools.health.wellness_ingest.health_wellness_ingest_total"),
        ):
            pool = AsyncMock()

            async def _fetchrow(query, *args, **kwargs):
                if "google_accounts" in query:
                    row = MagicMock()
                    row.__getitem__ = MagicMock(
                        side_effect=lambda k: "user@example.com" if k == "email" else None
                    )
                    return row
                if "public.entities" in query:
                    row = MagicMock()
                    row.__getitem__ = MagicMock(
                        side_effect=lambda k: str(uuid.uuid4()) if k == "id" else None
                    )
                    return row
                return None

            pool.fetchrow.side_effect = _fetchrow
            embedding_engine = MagicMock()

            from butlers.tools.health.wellness_ingest import translate_wellness_envelope

            r1 = await translate_wellness_envelope(pool, embedding_engine, envelope)
            r2 = await translate_wellness_envelope(pool, embedding_engine, envelope)

        assert r1["status"] == "ok"
        assert r2["status"] == "ok"
        # Both calls forwarded the same idempotency_key
        assert mock_store.call_count == 2
        for call in mock_store.call_args_list:
            assert call.kwargs.get("idempotency_key") == ikey


# ---------------------------------------------------------------------------
# 4. Malformed payload
# ---------------------------------------------------------------------------


class TestMalformedPayload:
    async def test_empty_raw_skips_sleep_session(self) -> None:
        """Sleep session with empty raw (no durationMillis) returns skipped_malformed_payload.

        A sleep record with no duration is considered malformed — duration is the
        minimum required field for a sleep session fact to be meaningful.
        """
        envelope = _make_sleep_envelope(raw={"startTime": "2026-04-24T23:00:00Z"})
        # No durationMillis → duration_ms=0 → treated as malformed
        result, mock_store, mock_counter = await _call_translate(envelope)

        assert result["status"] == "skipped_malformed_payload"
        mock_store.assert_not_awaited()

    async def test_none_raw_skips(self) -> None:
        """Envelope with raw=None is treated as empty → skipped_malformed_payload."""
        envelope = _make_sleep_envelope()
        envelope["payload"]["raw"] = None
        # raw becomes {} → no durationMillis → malformed
        result, mock_store, mock_counter = await _call_translate(envelope)

        assert result["status"] == "skipped_malformed_payload"
        mock_store.assert_not_awaited()

    async def test_warning_logged_on_missing_field(self, caplog) -> None:
        """A warning is logged when payload is malformed."""
        import logging

        envelope = _make_sleep_envelope(raw={"startTime": "2026-04-24T23:00:00Z"})
        with caplog.at_level(logging.WARNING, logger="butlers.tools.health.wellness_ingest"):
            result, _mock_store, _mock_ctr = await _call_translate(envelope)

        assert result["status"] == "skipped_malformed_payload"
        # Warning should have been emitted
        assert any("malformed" in r.message or "empty" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# 5. Prometheus counter
# ---------------------------------------------------------------------------


class TestPrometheusCounter:
    async def test_success_increments_counter_with_correct_labels(self) -> None:
        """On success, counter is incremented with predicate and outcome=success."""
        envelope = _make_daily_envelope("resting_hr")
        result, _, mock_counter = await _call_translate(envelope)

        assert result["status"] == "ok"
        mock_counter.labels.assert_called_once_with(
            predicate="measurement_resting_hr", outcome="success"
        )
        mock_counter.labels.return_value.inc.assert_called_once()

    async def test_unknown_predicate_increments_skipped_counter(self) -> None:
        """Unknown resource increments counter with skipped_unknown_predicate outcome."""
        envelope = _make_daily_envelope("completely_unknown")
        result, _, mock_counter = await _call_translate(envelope)

        assert result["status"] == "skipped_unknown_predicate"
        label_call = mock_counter.labels.call_args
        assert label_call.kwargs.get("outcome") == "skipped_unknown_predicate"
        mock_counter.labels.return_value.inc.assert_called_once()

    async def test_non_primary_rejection_increments_counter(self) -> None:
        """Non-primary sender increments counter with rejected_non_primary_sender."""
        from butlers.tools.health.wellness_ingest import translate_wellness_envelope

        envelope = _make_sleep_envelope(sender_identity="stranger@example.com")
        pool = AsyncMock()

        async def _fetchrow(query, *args, **kwargs):
            if "google_accounts" in query:
                row = MagicMock()
                row.__getitem__ = MagicMock(
                    side_effect=lambda k: "primary@example.com" if k == "email" else None
                )
                return row
            return None

        pool.fetchrow.side_effect = _fetchrow

        with patch(
            "butlers.tools.health.wellness_ingest.health_wellness_ingest_total"
        ) as mock_counter:
            result = await translate_wellness_envelope(pool, MagicMock(), envelope)

        assert result["status"] == "rejected_non_primary_sender"
        mock_counter.labels.assert_called_once_with(
            predicate="unknown", outcome="rejected_non_primary_sender"
        )
        mock_counter.labels.return_value.inc.assert_called_once()

    @pytest.mark.parametrize(
        "resource",
        [
            "sleep_session",
            "resting_hr",
            "hrv",
            "spo2",
            "breathing_rate",
            "steps",
            "active_minutes",
            "vo2_max",
        ],
    )
    async def test_counter_label_predicate_matches_resource(self, resource: str) -> None:
        """Counter is labeled with the canonical predicate name, not the resource key."""
        from butlers.tools.health.wellness_ingest import _RESOURCE_TO_PREDICATE

        if resource == "sleep_session":
            envelope = _make_sleep_envelope()
        else:
            envelope = _make_daily_envelope(resource)

        result, _, mock_counter = await _call_translate(envelope)

        assert result["status"] == "ok"
        expected_predicate = _RESOURCE_TO_PREDICATE[resource]
        mock_counter.labels.assert_called_once_with(predicate=expected_predicate, outcome="success")
