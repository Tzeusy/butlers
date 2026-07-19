## Why

Calendar projection currently lacks one durable provenance rule across its
Google parser, context producer, conflict radar, and source ledger. That lets
date-only or butler-authored projection rows be misread as human meetings,
while obsolete internal-source rows can remain visible in freshness state.

The completed-but-unarchived `context-bus-producers` change made the calendar
producer real; this is a compatible truthfulness hardening of its input. It
does not change the producer's writer, scheduling, TTL, or notification
semantics.

## What Changes

- Normalize Google date-only events as `all_day=true`, and defensively treat
  legacy locally-midnight-aligned events spanning at least 24 hours as
  non-meetings even when their stored flag is false.
- Keep `metadata.butler_generated` projection rows visible in the workspace,
  but exclude them from calendar-derived context and all three conflict-radar
  detectors (overlap, back-to-back, and overloaded day). Preserve behavior for
  equivalent timed human events.
- Parse malformed event metadata and timezones conservatively, so projection
  analysis neither raises nor invents a human meeting from uncertain input.
- Retire only the known obsolete internal source keys
  `internal_scheduler:butler`, `internal_scheduler:butlers`, and
  `internal_reminders:butlers`; validate roster names on source registration
  without broad source-name policy or deletion of valid sources.
- Add compatible strict OpenSpec deltas and regression coverage for the
  projection, context, radar, and ledger behavior.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `module-calendar`: projection provenance, all-day normalization, and
  source-ledger hygiene rules change.
- `context-bus`: calendar meeting/focused production excludes internal and
  non-meeting projection rows.
- `calendar-conflict-overcommitment-radar`: all three detectors ignore
  explicitly butler-generated projection rows while retaining human events.

## Impact

- `src/butlers/modules/calendar.py` projection parsing and source registration
- `src/butlers/jobs/context_producers.py` calendar candidate selection
- `src/butlers/core/temporal/conflicts.py` and calendar workspace read-model
  candidate construction
- Focused module, job, radar, and migrated-ledger tests
- No provider API, user-facing workspace visibility, database schema, or new
  dependency change
