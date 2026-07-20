## Context

**[Observed]** The deterministic dashboard-api restore-drill loop restores the newest plain-SQL
backup into the fixed `butlers_restore_drill` scratch database, records its
result in `public.audit_log`, and exposes that result through
`GET /api/system/backups`. It currently records free-form detail only and
treats every recorded outcome alike for the seven-day cadence. Consequently a
`createdb` permission failure can postpone the next attempt for a week while
the owner has no durable attention event or failure age.

The existing role model is schema-scoped at runtime (`SET ROLE
butler_<schema>_rw` and `connector_writer`) but has a bootstrap/migration
connecting role controlled by `scripts/init-db.sql`. A restore drill needs
database creation through that bootstrap-managed connection, not a privilege
grant to a runtime role. RFC 0006 and the security doctrine require this
least-privilege distinction; RFC 0005 requires structured failure evidence
without secrets or high-cardinality metric labels; RFC 0007 requires the
dashboard to distinguish unavailable information from a truthful empty state.

## Goals / Non-Goals

**Goals:**

- Make the restore drill a bounded proof that never writes to the live
  application database.
- Preserve runtime-role least privilege while establishing the bootstrap-only
  `CREATEDB` prerequisite.
- Make missing, failed, passed, and recovered drill states truthful in
  scheduling, stored provenance, the system API, and the dashboard.
- Require real PostgreSQL client/testcontainer proof of success, permission
  denial classification, and scratch cleanup.

**Non-Goals:**

- Running a production drill, changing a live role, deploying or restarting a
  service, or repairing data by hand.
- Adding an API that reveals a privileged database credential or a manual
  operator workaround that creates the scratch database.
- Sending an owner notification, changing the normal backup cadence, or adding
  multi-replica restore-drill execution in this change.

## Decisions

### 1. Bootstrap owns `CREATEDB`; runtime roles never do

`scripts/init-db.sql` is the sole managed bootstrap path that may grant
`CREATEDB`, and it grants it only to the configured migration/connecting role
used by the restore command. Every `butler_*_rw` role and `connector_writer`
must remain `NOCREATEDB`; no dashboard route, runtime configuration, or
credential surface may provide a substitute privileged connection. This keeps
the capability at the owner-controlled bootstrap boundary and preserves the
`SET ROLE` isolation contract.

The alternative of granting `CREATEDB` to a runtime role would make every
runtime connection able to create arbitrary databases. The alternative of
asking an operator to run `ALTER ROLE` or pre-create a scratch database during
an incident turns a recovery proof into an untracked live mutation. Both are
rejected. The operations guide must state the bootstrap prerequisite and direct
operators to the managed bootstrap process, not an ad hoc SQL workaround.

### 2. The scratch database has an explicit, single-executor lifecycle

Each attempt first removes a stale scratch database, creates a fresh scratch
database, restores the selected artifact with the real PostgreSQL client,
verifies non-system data, and attempts post-run cleanup regardless of the
earlier outcome. No command may target the configured live application
database. A pre-cleanup or post-cleanup error is itself a failed attempt; a
pass is valid only after verification and cleanup complete. Failure metadata
distinguishes the lifecycle stage (`pre_cleanup`, `create`, `backup_read`,
`restore`, `verify`, or `post_cleanup`) from a stable code such as
`createdb_permission_denied`, `client_tool_unavailable`, `restore_timeout`,
or `scratch_cleanup_failed`.

The fixed scratch name is retained because it lets the next attempt recover a
leftover from a killed prior attempt. This release assumes exactly one
dashboard-api restore-drill executor. Before any deployment can run more than
one executor, it must add a cross-process exclusive guard (for example a
database advisory lock) around the whole lifecycle; no best-effort timing
assumption is sufficient.

### 3. Persisted result fields drive cadence and the failure epoch

The audit record is the scheduling authority. No record is immediately due;
`pass` is due after seven days; `fail` is due after 24 hours. A missing backup
file is a legitimate no-result skip and creates neither a failure record nor
an attention event. A degraded ledger read does not alter scheduling because
it is an API-read condition, not a recorded drill result.

Every recorded failure carries a closed `failure_stage` and `failure_code`,
plus a sanitized, bounded operator detail (maximum 512 characters). Raw
stderr, passwords, connection strings, dump content, and unbounded backup
paths must not enter the audit metadata, attention ledger, API response, logs,
or metrics. Legacy records without structured fields remain readable with
unknown/null provenance; their text is never parsed to infer a code or cadence.

`failing_since` is the timestamp of the oldest contiguous failed restore-drill
record ending at the current failed result. It is `null` unless the current
result is `fail`; a subsequent pass resets it to `null`. This is calculated
from persisted result ordering, not from an in-memory loop clock or error text.

### 4. Attention provenance records an honesty gap, not a notification

After the failed drill result is durably recorded, the job makes a best-effort
insert into `public.attention_ledger` with `source="restore_drill"`,
`outcome="failed"`, no channel/intent, and `notification_ref=null`. Its reason
is the stable failure code; metadata contains only the stage, code, bounded
sanitized detail, and the recorded-at reference needed for diagnosis. The
attention source check constraint and reader filter vocabulary are expanded in
the same migration. A ledger-write failure is logged and swallowed, but cannot
erase, downgrade, or prevent the audit result; an audit-result write failure
cannot be represented as a durable attention success.

Using `source="notify"` or a synthetic notification reference is rejected
because no owner-facing delivery occurred. Reusing unstructured error text for
the ledger reason is rejected because it makes scheduling and observability
depend on unstable, potentially sensitive process output.

### 5. The monitoring surface leads with current truth

`RestoreDrillFacts` gains additive `failure_code`, `failure_stage`, and
`failing_since` fields. The System page shows the failure age adjacent to the
current failed restore-drill verdict, with code/detail as secondary diagnostic
information. It must not render a stale failure age for `pass`, `pending`, or
`degraded`, and `degraded` remains an explicit unavailable state rather than
an all-clear. The system verdict banner reflects the same current failed state
without inventing a notification or treating historical failure as current
after recovery.

This follows the monitoring hierarchy: the owner sees the current recovery
verdict first, the duration of a current failure next, then concise diagnostic
context on demand. Text and semantic status must communicate the state without
depending on color alone.

## Risks / Trade-offs

- **Bootstrap privilege is broader than a runtime role** → Restrict it to the
  existing bootstrap/migration connecting role, assert all runtime roles are
  `NOCREATEDB`, and expose no new credential or API path.
- **A fixed scratch name collides across replicas** → Keep the current
  single-executor assumption explicit and block multi-replica enablement until
  a cross-process lock is implemented.
- **A ledger write fails after a real drill failure** → Preserve the audit
  result as authority, log the ledger failure, and leave the 24-hour retry
  cadence intact.
- **Old audit rows lack structured fields** → Preserve their result and
  timestamp, return unknown/null structured provenance, and never infer it
  from legacy error text.
- **A mock can hide client-tool behavior** → Require integration coverage that
  invokes real `pg_dump`, gzip, `createdb`, `psql`, and `dropdb` against a
  PostgreSQL testcontainer; intentional environment-unavailability is the only
  allowed skip condition.

## Migration Plan

1. Update the idempotent bootstrap SQL and its role-boundary tests so the
   migration/connecting role receives `CREATEDB` while runtime roles remain
   `NOCREATEDB`; update the operator procedure before enabling the repair.
2. Add a core migration that expands the `attention_ledger` source vocabulary
   to `restore_drill`, preserving existing rows and targeted grants. The
   restore result uses existing audit metadata, so no data backfill or live
   repair is needed.
3. Ship structured result writing, result-aware scheduling, attention recording,
   API/types/UI updates, and focused tests together after the prerequisite
   migration is available.
4. Roll back application code without restoring a dump into the live database.
   If the source-constraint migration is downgraded, remove only
   `source="restore_drill"` attention observations before narrowing the
   constraint; retain audit results and backup artifacts. Do not issue ad hoc
   `ALTER ROLE` statements or manually delete failed-drill evidence as rollback.

## Open Questions

None. Multi-replica execution is explicitly deferred until its exclusive-lock
contract is proposed and implemented.
