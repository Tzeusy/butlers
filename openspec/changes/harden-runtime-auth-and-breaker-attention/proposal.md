## Why

The runtime can currently disagree with the dashboard about whether a model is
healthy. In the observed incident, a stale schema-local Codex credential
overwrote the newer public credential in the daemon's shared runtime volume;
the dashboard's isolated test passed while real routed sessions failed to
refresh. Independently, several OpenCode entries used provider-qualified IDs
that the configured provider rejects, and breaker notifications could send
duplicates because their debounce was a non-atomic read-send-write sequence.

The owner needs one trustworthy answer to "is this runtime usable?" and one
bounded, explainable alert per actual outage episode. A dashboard probe,
best-effort telemetry write, or a different butler's stale local secret must
not change that answer.

## What Changes

- Establish an explicit authoritative shared credential scope for `cli-auth/*`.
  Runtime restore and rotation persistence will use that scope only; stale
  schema-local CLI-auth rows are retained as ignored diagnostics and cannot
  overwrite shared runtime files.
- Define canonical provider-native runtime model identifiers, migrate the
  affected OpenCode catalog entries, and validate catalog writes and probes
  against the same resolved adapter arguments used for runtime execution.
- Replace the breaker alert's audit-marker debounce with an atomic
  closed-to-open transition and a durable attention-delivery outbox. The
  Switchboard alone claims and sends queued attention; delivery is at-most-once
  for an alert episode, with ambiguous transport outcomes made visible as
  `uncertain` rather than automatically retried.
- Make post-send routing and attention-ledger telemetry best-effort so a
  confirmed Messenger response remains successful even when later bookkeeping
  fails. Non-Switchboard roles will no longer invoke `switchboard.*` delivery
  SQL directly.
- Apply the shared outbox to the fleet-halt owner page, and make the Models
  page distinguish a catalog probe from a routed-success breaker recovery.
  The operator can inspect an uncertain alert and explicitly request a new
  alert episode; no automatic replay can create a duplicate page.
- Add migration-safe targeted grants, operator-facing diagnostics, traceable
  lifecycle state, and regression coverage for credential scope, concurrent
  breaker openings, worker restart, ACL isolation, post-send failure, and
  provider-native OpenCode IDs.

## Capabilities

### New Capabilities

- `runtime-attention-outbox`: Durable, Switchboard-owned, at-most-once
  operational-attention episode delivery with explicit terminal and uncertain
  states.

### Modified Capabilities

- `core-credentials`: `cli-auth/*` authority, restore, rotation persistence,
  and safe conflict diagnostics become explicitly shared-scope behavior.
- `core-daemon`: daemon and connector startup restore CLI auth from the
  authoritative shared scope without per-butler overwrite ordering.
- `model-catalog`: breaker opening becomes an atomic transition that produces
  one alert episode; provider-native model IDs are validated and migrated.
- `runtime-opencode`: OpenCode model selection follows the provider's canonical
  native identifier contract instead of assuming one universal prefix form.
- `core-notify`: confirmed delivery is insulated from post-send bookkeeping,
  and attention records remain observations rather than idempotency authority.
- `database-security`: the public outbox and dispatch-transition access receive
  narrowly scoped runtime-role grants; Switchboard retains delivery ownership.
- `dashboard-model-settings`: model verification, routed breaker state, alert
  delivery state, and explicit operator recovery are shown as distinct facts.
- `dashboard-spend-dashboard`: fleet-halt attention uses the shared durable
  outbox rather than an audit-marker debounce.

## Impact

- Core credential, daemon lifecycle, Codex auth synchronization, model routing,
  spawner provenance, and OpenCode runtime code.
- Switchboard notification routing, deterministic background delivery work,
  attention ledger/audit telemetry, and role-grant migrations.
- Model catalog data migration and dashboard API/frontend contracts for Models
  and fleet-halt status.
- No credential values, existing local secret rows, historical dispatch
  attempts, notification records, or audit evidence are deleted by rollout.
