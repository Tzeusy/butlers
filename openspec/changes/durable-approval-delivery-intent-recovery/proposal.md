## Why

Parking an approval action is currently durable, but owner notification is a
best-effort post-commit side effect. A process crash, quiet-hours hold, or
ambiguous provider result can therefore leave a still-pending action without a
recoverable, truthful notification record. Approval is a safety boundary: a
notification worker may recover attention, but it must never decide, execute,
or otherwise mutate the parked domain action.

## What Changes

- Add a schema-local, one-to-one durable approval-delivery intent created in
  the same transaction as every new pending action, with a stable action key,
  resolved RFC 0021 admission result, and no provider credential or raw
  provider error persisted.
- Add a deterministic notification-only worker with leased, fenced claims,
  bounded at-least-once retries/backoff, stale-claim recovery, and a
  pre-provider durable handoff marker.
- Extend the notification boundary to classify a handoff as confirmed,
  definitively safe to retry, or ambiguous. Reuse one stable idempotency key
  when the provider can prove duplicate safety; otherwise quarantine an
  uncertain post-start handoff instead of sending speculatively again.
- Atomically cancel outstanding delivery intents when an action is decided or
  expires, while preserving the immutable action decision semantics. The
  worker changes intent and attempt records only; it never approves, rejects,
  expires, executes, or mutates a parked action.
- Preserve RFC 0021's one-notification-per-action, quiet-hours exact-release,
  control-plane budget exemption, and burst-digest/collapse semantics without
  reusing or changing the generic deferred-notification queue.
- Add safe state/reason vocabularies, retention rules, API/dashboard truth,
  and stuck/ambiguous observability. Existing push-emission rows remain legacy
  evidence; there is no historical-intent backfill or replay.

## Capabilities

### New Capabilities

- `approval-delivery-intent-recovery`: The schema-local durable intent,
  fenced notification-only recovery worker, provider-handoff classification,
  cancellation, retention, and rollout contract.

### Modified Capabilities

- `module-approvals`: Every pending-action admission atomically creates its
  delivery intent and every terminal action transition fences or cancels it.
- `core-notify`: `notify.v1` carries a stable delivery idempotency key and
  returns a normalized, safe handoff classification for recovery callers.
- `butler-messenger`: The actual provider boundary durably reconciles an
  approval egress key; it does not resurrect the retired, unwired generic
  delivery-tracking tables.
- `dashboard-approvals`: Approval API and UI expose delivery recovery state
  without leaking secrets, recipients, raw provider responses, or implying
  that an ambiguous handoff was never sent.

## Impact

This is an OpenSpec-only planning change. Future implementation affects the
Approvals module schema and parking/decision paths, daemon-owned background
worker lifecycle, notify/routing/Messenger delivery boundary, approval API and
dashboard, metrics, and integration/contract tests. It makes no source
implementation, migration execution, live replay, owner message, approval
decision, entity/fact mutation, deployment, or runtime change.
