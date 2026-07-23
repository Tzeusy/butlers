## Why

Routine owner-default notifications are now preserved as durable quiet-hours
holds, but the system has no trustworthy, recoverable way to release a held
morning cohort from an owner interaction. The owner selected a deliberately
narrow v1 authority: a durably accepted direct text DM from the canonical owner
through the Telegram bot. The release must remain safe through duplicate
updates, concurrent runs, daemon crashes, and an ambiguous Telegram send; DND
remains an absolute veto while its canonical cross-writer contract is deferred
to a prerequisite.

## What Changes

- Define a deterministic, Switchboard-coordinated wake-recovery protocol that
  begins only after a qualifying Telegram event and its acceptance provenance
  are durable.
- Define a window-scoped release run, participant and row fencing, and the
  MCP-only prepare, commit, abort, and release exchanges needed to compose one
  exact-target Telegram send without cross-schema queue reads.
- Preserve the existing durable queue's no-re-gating rule while excluding a
  run-reserved cohort from the normal scheduler pass; rows arriving after the
  cohort freeze stay for a later release.
- Preserve DND as an absolute veto that a direct DM never clears, the
  Health-owned policy-sleep exception, all-or-nothing retry/retention behavior,
  and crash/ambiguous-send recovery.
- Defer canonical DND versioning/invalidation and durable post-prepare
  cancellation admission to their dedicated prerequisite changes.
- Require one stable end-to-end egress action key from the accepted event and
  window through Messenger admission and provider receipt reconciliation.
- Document the intentionally strict v1 exclusions: no Telegram user-client,
  group/channel/service/media event, HA/OwnTracks/location trigger, briefing,
  broker catch-up, cron/schedule change, generic context clear, or partial
  cohort release.

## Capabilities

### New Capabilities

- `owner-telegram-wake-recovery`: The strict owner-authorized recovery state
  machine, durable provenance, cohort fencing, RPC protocol, and verification
  contract.

### Modified Capabilities

- `core-notify`: Qualifying quiet-hours holds retain immutable admission and
  exact-target provenance required for a later fenced release.
- `time-aware-delivery`: The ordinary deferred-notification scheduler excludes
  a run-reserved cohort, does not re-gate or recalculate stored delivery
  decisions, and preserves late rows for a later run.
- `butler-switchboard`: Switchboard recognizes only the post-commit canonical
  owner Telegram-bot wake authority and coordinates trusted cross-origin RPCs.
- `butler-health`: Only Health's deterministic policy-sleep context may be
  superseded by a committed wake run; no generic context signal is cleared.
- `butler-messenger`: Messenger admits the one composed release with a stable
  end-to-end idempotency key and makes ambiguous provider outcomes recoverable.
- `database-security`: Runtime roles retain schema isolation; release
  coordination gets only narrowly authenticated MCP and shared-control ACLs.

## Impact

This is an OpenSpec-only planning change. It specifies future changes to the
Switchboard ingestion/recovery coordinator, origin-butler deferred queues,
Health policy-sleep handling, Messenger delivery admission, role grants, and
their tests. It makes no implementation, migration, live trigger,
notification, schedule, or runtime configuration change.

## Prerequisite Boundary

This parent packet deliberately defines no scheduler-visible post-prepare
cancellation route. Once a cohort has durably reached `release_prepared`, an
ordinary cancellation cannot return any member to `pending` under this change;
the frozen cohort remains protocol-bound and cannot fall back to a partial or
ordinary send.

`bu-12iab` owns the canonical DND versioning/invalidation contract. `bu-qs702`
owns the durable Scheduler/Messenger post-prepare cancellation-admission
contract. This packet does not prescribe either prerequisite's future schema,
MCP fields, or implementation. They must land before an implementation relies
on a final cross-writer DND race guarantee or a post-prepare cancellation path.
