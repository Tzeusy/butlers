"""Deterministic job implementations for the Home butler's scheduled monitoring tasks.

These handlers replace prompt-based LLM dispatch with threshold-based classification,
memory storage, and Telegram notifications — eliminating LLM costs for formulaic
monitoring work.

Jobs read current entity state from the connector-populated ``ha_entity_snapshot``
table (or its SPO successor) and load monitoring thresholds from the state store
(``home:thresholds:*``), falling back to HA REST API only for historical statistics.

Design reference: openspec/specs/home-deterministic-jobs/spec.md
"""

from __future__ import annotations

import logging
from typing import Any

import asyncpg

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Device health check
# ---------------------------------------------------------------------------


async def run_device_health_check(pool: asyncpg.Pool) -> dict[str, Any]:
    """Survey all HA entities for offline status and low battery levels.

    Reads entity states from the connector-populated snapshot, classifies issues
    by severity using configurable thresholds from the state store
    (``home:thresholds:battery``, ``home:thresholds:offline_hours``), stores
    findings in memory, and sends a Telegram notification with the results.

    Returns a dict with keys: ``devices_checked``, ``issues_found``,
    ``critical_count``, ``warning_count``.
    """
    # NOTE: Full implementation is deferred to a follow-up task. This stub
    # satisfies the job registry registration requirement so that the scheduler
    # can dispatch to it without a RuntimeError. The actual monitoring logic
    # (entity snapshot queries, threshold loading, memory fact storage, and
    # Telegram notification) will be implemented in the home-deterministic-jobs
    # feature work.
    logger.info("device_health_check: stub — full implementation pending")
    return {
        "devices_checked": 0,
        "issues_found": 0,
        "critical_count": 0,
        "warning_count": 0,
    }


# ---------------------------------------------------------------------------
# Environment report
# ---------------------------------------------------------------------------


async def run_environment_report(pool: asyncpg.Pool) -> dict[str, Any]:
    """Read environmental sensors per area and send a comfort report.

    Reads temperature, humidity, CO2, and illuminance sensor readings grouped
    by Home Assistant area from the connector-populated snapshot. Compares each
    reading against stored comfort preferences and configurable deviation
    thresholds (``home:thresholds:comfort_defaults``,
    ``home:thresholds:comfort_deviation``). Stores deviations in memory and
    sends a room-by-room Telegram notification.

    Returns a dict with keys: ``areas_checked``, ``sensors_read``,
    ``deviations_found``.
    """
    logger.info("environment_report: stub — full implementation pending")
    return {
        "areas_checked": 0,
        "sensors_read": 0,
        "deviations_found": 0,
    }


# ---------------------------------------------------------------------------
# Energy digest
# ---------------------------------------------------------------------------


async def run_energy_digest(pool: asyncpg.Pool) -> dict[str, Any]:
    """Fetch weekly energy statistics and send a structured digest.

    Discovers energy-related sensor entities from the connector-populated
    snapshot, fetches weekly historical statistics via the HA REST API
    (``recorder/get_statistics_during_period``), computes top consumers and
    percentage deviation from stored baselines using configurable anomaly
    thresholds (``home:thresholds:energy``), updates baseline memory facts, and
    sends a structured weekly digest via Telegram.

    Returns a dict with keys: ``total_kwh``, ``devices_ranked``,
    ``anomalies_found``, ``baseline_updated``.
    """
    logger.info("energy_digest: stub — full implementation pending")
    return {
        "total_kwh": 0.0,
        "devices_ranked": 0,
        "anomalies_found": 0,
        "baseline_updated": False,
    }


# ---------------------------------------------------------------------------
# Maintenance schedule check
# ---------------------------------------------------------------------------


async def run_maintenance_schedule_check(pool: asyncpg.Pool) -> dict[str, Any]:
    """Check all maintenance items for due/overdue status and send reminders.

    Queries all home maintenance items (stored via the ``ha_maintenance_*``
    tools), identifies items that are due or overdue, and sends a Telegram
    notification listing them with recommended actions.

    Returns a dict with keys: ``items_checked``, ``due_count``,
    ``overdue_count``.
    """
    logger.info("maintenance_schedule_check: stub — full implementation pending")
    return {
        "items_checked": 0,
        "due_count": 0,
        "overdue_count": 0,
    }
