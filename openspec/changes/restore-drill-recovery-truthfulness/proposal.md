## Why

The owner cannot treat a backup as recoverable merely because it exists: the
only observed restore drill failed at `createdb` permission denial, yet that
failure currently resets the normal weekly cadence and produces neither durable
attention provenance nor a visible failure age. This change makes the restore
drill a bounded, least-privilege proof of recovery rather than an unverified
all-clear.

## What Changes

- Define a bootstrap-only `CREATEDB` boundary: the migration/connecting role
  may receive the capability during database bootstrap, while every butler and
  connector runtime role remains `NOCREATEDB` and no API exposes a privileged
  database credential.
- Define the scratch-database restore lifecycle, its no-live-mutation
  prerequisite, and the current single-deployment guard; a future
  multi-replica deployment must add a cross-process concurrency guard before
  it may run the fixed-name drill concurrently.
- Make cadence result-aware: no recorded result is immediately due, a pass is
  due after seven days, and a recorded failure is due after 24 hours. A pass
  after failures closes the contiguous failure epoch.
- Persist stable failure stage/code and bounded sanitized detail, then emit a
  best-effort attention-ledger event with truthful `restore_drill` provenance;
  ledger trouble must not erase the drill result or imply an owner notification.
- Extend the system backup API and System page with failure-only
  `failing_since` visibility while preserving explicit pending and degraded
  states; prove the command path with a real PostgreSQL testcontainer.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `database-security`: add the least-privilege bootstrap boundary for a
  restore-drill database-creation capability.
- `deployment-hardening`: make the documented restore path operationally safe,
  lifecycle-bounded, and result-aware.
- `system-overview-page`: expose truthful restore result provenance, cadence,
  and current failure age in the API and dashboard.
- `core-notify`: extend the attention ledger vocabulary for a non-notification
  restore-drill failure event.
- `testing`: require environment-proof restore-drill integration evidence
  against PostgreSQL tooling in a testcontainer.

## Impact

Future implementation will touch bootstrap SQL, the restore-drill job and its
audit/attention records, the system API and frontend types/tile, operations
documentation, and focused unit, API/frontend, migration/role, and Docker
testcontainer tests. It does not introduce a live drill, alter a live role,
deploy or restart services, perform manual data repair, or broaden database
privileges at runtime.
