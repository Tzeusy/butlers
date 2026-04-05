"""Tests for deterministic job handler registration in _DETERMINISTIC_SCHEDULE_JOB_REGISTRY.

Covers:
- Daily briefing contribution handlers for specialist butlers (health, finance, etc.)
- collect_briefing_contributions for general butler
- Home butler deterministic jobs (device_health_check, environment_report, etc.)
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit

# Specialist butlers that must expose daily_briefing_contribution
_SPECIALIST_BUTLERS = ("health", "finance", "relationship", "travel", "education", "home")

_HOME_DETERMINISTIC_JOBS = (
    "device_health_check",
    "environment_report",
    "energy_digest",
    "maintenance_schedule_check",
)


class TestBriefingJobRegistration:
    def test_briefing_handlers_registered_and_callable(self):
        """All 7 briefing handlers registered and callable; count is exactly 7."""
        from butlers.daemon import _DETERMINISTIC_SCHEDULE_JOB_REGISTRY

        # All specialist butlers have daily_briefing_contribution
        missing = [
            butler
            for butler in _SPECIALIST_BUTLERS
            if "daily_briefing_contribution"
            not in _DETERMINISTIC_SCHEDULE_JOB_REGISTRY.get(butler, {})
        ]
        assert not missing, (
            f"daily_briefing_contribution not registered for specialist butlers: {missing}"
        )

        # General butler has collect_briefing_contributions
        jobs = _DETERMINISTIC_SCHEDULE_JOB_REGISTRY.get("general", {})
        assert "collect_briefing_contributions" in jobs, (
            "collect_briefing_contributions not registered for general butler"
        )

        # All 7 handler references are callable
        handler_entries: list[tuple[str, str]] = [
            (butler, "daily_briefing_contribution") for butler in _SPECIALIST_BUTLERS
        ] + [("general", "collect_briefing_contributions")]

        not_callable = []
        for butler, job_name in handler_entries:
            handler = _DETERMINISTIC_SCHEDULE_JOB_REGISTRY.get(butler, {}).get(job_name)
            if not callable(handler):
                not_callable.append(f"{butler}/{job_name}")
        assert not not_callable, f"Non-callable handlers in registry: {not_callable}"

        # Exactly 7 briefing handler slots
        specialist_count = sum(
            1
            for butler in _SPECIALIST_BUTLERS
            if "daily_briefing_contribution" in _DETERMINISTIC_SCHEDULE_JOB_REGISTRY.get(butler, {})
        )
        total = specialist_count + int("collect_briefing_contributions" in jobs)
        assert total == 7, f"Expected exactly 7 briefing handler slots, got {total}"

    def test_briefing_handlers_are_resolvable_via_resolve_function(self):
        """_resolve_deterministic_schedule_job_name returns job names for briefing jobs."""
        from butlers.daemon import _resolve_deterministic_schedule_job_name

        # Specialist butlers
        for butler in _SPECIALIST_BUTLERS:
            resolved = _resolve_deterministic_schedule_job_name(
                butler_name=butler,
                trigger_source="schedule:daily_briefing_contribution",
                job_name="daily_briefing_contribution",
            )
            assert resolved == "daily_briefing_contribution", (
                f"Expected 'daily_briefing_contribution' for {butler}, got {resolved!r}"
            )

        # General butler
        resolved = _resolve_deterministic_schedule_job_name(
            butler_name="general",
            trigger_source="schedule:collect_briefing_contributions",
            job_name="collect_briefing_contributions",
        )
        assert resolved == "collect_briefing_contributions", (
            f"Expected 'collect_briefing_contributions' for general, got {resolved!r}"  # noqa: E501
        )


class TestHomeJobRegistration:
    def test_home_jobs_registered_callable_and_resolve(self):
        """All four home jobs registered, callable, existing entries intact, and resolve correctly."""
        from butlers.daemon import _DETERMINISTIC_SCHEDULE_JOB_REGISTRY, _resolve_deterministic_schedule_job_name

        home_jobs = _DETERMINISTIC_SCHEDULE_JOB_REGISTRY.get("home", {})

        # All four registered
        missing = [job for job in _HOME_DETERMINISTIC_JOBS if job not in home_jobs]
        assert not missing, (
            f"Home deterministic jobs not in _DETERMINISTIC_SCHEDULE_JOB_REGISTRY['home']: {missing}"
        )

        # All four callable
        not_callable = [
            job_name
            for job_name in _HOME_DETERMINISTIC_JOBS
            if not callable(home_jobs.get(job_name))
        ]
        assert not not_callable, (
            f"Non-callable or missing handlers in _DETERMINISTIC_SCHEDULE_JOB_REGISTRY['home']: "
            f"{not_callable}"
        )

        # Existing entries untouched
        expected_existing = {
            "daily_briefing_contribution",
            "memory_consolidation",
            "memory_episode_cleanup",
            "memory_purge_superseded",
        }
        missing_existing = expected_existing - home_jobs.keys()
        assert not missing_existing, f"Pre-existing home registry entries were removed: {missing_existing}"

        # Resolvable via resolve function
        for job_name in _HOME_DETERMINISTIC_JOBS:
            resolved = _resolve_deterministic_schedule_job_name(
                butler_name="home",
                trigger_source=f"schedule:{job_name}",
                job_name=job_name,
            )
            assert resolved == job_name, f"Expected {job_name!r} for home butler, got {resolved!r}"
