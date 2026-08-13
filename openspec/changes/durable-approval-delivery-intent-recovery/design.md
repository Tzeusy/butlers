## Context

RFC 0021 requires a one-tap owner notification whenever an action parks. The
current common helper, `park_pending_action()`, inserts a pending action and
then makes an independent best-effort push attempt. Its `approval_push_emissions`
row has useful legacy display outcomes, but it is not an atomic outbox: a
runtime-less caller, crash, quiet-hours deferral, or failed/ambiguous transport
can leave an action pending without a recoverable notification intent.

The affected path crosses every approval producer, its owning schema, daemon
background lifecycle, Switchboard/Messenger notify routing, dashboard reads,
and retention. The design must preserve four independent contracts:

- RFC 0017 owner-only recipient resolution and secret handling;
- RFC 0021's exact quiet-hours release, control-plane budget exemption, and
  first-three / digest / collapsed burst behavior;
- RFC 0022's rule that PostgreSQL `NOTIFY` is only a wake hint, never durable
  work; and
- Doctrine's parked-action boundary: notification recovery can never approve,
  execute, expire, defer, or edit the domain action.

The active `strict-owner-telegram-wake-recovery` planning change concerns the
generic deferred-notification queue. This change deliberately does not join
that queue, its wake cohort, or its cross-schema protocol. Legacy generic
approval rows keep their existing behavior; new approval intents are neither
backfilled nor replayed into either system.

## Goals / Non-Goals

**Goals:**

- Commit each new pending action and one unique delivery intent atomically.
- Make due notification work recoverable across duplicate parks, concurrent
  workers, process crashes/restarts, and ordinary transient failures.
- Preserve RFC 0021 quiet-hours, no-re-gate, budget, and burst-collapse
  semantics exactly at durable admission.
- Make the provider boundary safe when it can prove duplicate idempotency and
  honest when a post-start outcome is ambiguous.
- Fence all decision/expiry races and expose only safe delivery truth to API,
  dashboard, logs, metrics, and retention.
- Produce an implementation packet that can be independently reviewed and
  exercised against real PostgreSQL before any rollout.

**Non-Goals:**

- No source implementation, Alembic execution, deployment, daemon restart,
  live provider replay, owner notification, approval decision/execution,
  entity/fact mutation, or historical-intent backfill in this planning change.
- No generic notification-queue redesign, quiet-hours wake release, new owner
  channel policy, daily insight-budget change, or change to a parked action's
  expiration/decision semantics.
- No exactly-once provider claim. A provider without a stable idempotency or
  reconciliation primitive must remain visibly ambiguous after an uncertain
  post-start outcome.

## Decisions

### D1 — The local approval intent is the transactional outbox boundary

Each approval-owning schema gains `approval_delivery_intents`, one row per
`pending_actions.id`, and append-only `approval_delivery_attempts`. The shared
parking helper accepts a typed `ParkRequest`, validates origin and safe dossier
data, and uses one acquired connection plus one transaction to:

1. insert or return the semantic-key-deduplicated pending action;
2. serialize the current schema's RFC 0021 burst calculation;
3. resolve the quiet-hours *admission* into a persisted `not_before`; and
4. insert the action's unique intent (and existing action-queued audit event
   where its current caller contract requires it).

The intent carries the immutable action key, origin, mode, timing, state,
claim fields, and safe reason metadata. It does not carry a callback token,
callback secret, recipient, raw message, raw `tool_args`, or provider payload.
The worker reads the local pending action and renders the current deterministic
dossier only while it is still eligible to notify. A future defer changes the
action expiry but neither creates another intent nor causes another push.

`approval_push_emissions` is read-compatible legacy evidence during rollout;
new code must not write both it and an intent for the same parked action.

**Alternative considered:** an after-commit callback plus a retry job. Rejected
because the callback can be lost before the retry job knows the action exists.

### D2 — Admission snapshots RFC 0021 rather than reusing generic deferral

The parking transaction uses the same Owner Attention Policy calculation as
RFC 0021. It records one `not_before` equal to `requested_at` or the exact end
of the quiet interval. The worker uses that stored value; it never recomputes a
changed policy at delivery time. This preserves the existing no-re-gate rule.

Under the existing per-schema advisory transaction lock, the transaction
counts newly admitted approval intents in the ten-minute window and chooses:

| Park ordinal in window | Intent mode / behavior |
| --- | --- |
| 1–3 | `single`; worker eventually renders one action dossier. |
| 4 | `burst_digest`; worker renders one deterministic dashboard digest using the transaction's pending count. |
| 5+ | `collapsed`; terminal at admission and has no transport attempt. |

All three modes have an intent row and action key. The admission decision uses
the approval control-plane policy only; it does not consume or borrow the
insight broker's daily budget. New intent rows never go into
`deferred_notifications`, and the generic scheduler never claims them.

**Alternative considered:** calculate burst/quiet behavior in the worker.
Rejected because concurrent admission or later policy changes would make the
same parked action nondeterministic and could generate duplicate digests.

### D3 — Fenced claims linearize recovery before provider handoff

The daemon starts a dedicated approval-delivery loop only when its local
Approvals module/schema is active. Core owns the loop lifecycle; the approvals
module owns its schema/repository and deterministic render rules. This keeps a
module from creating an independent scheduler while preserving schema
ownership.

Claiming uses a local query with `FOR UPDATE SKIP LOCKED`, increasing
`claim_fence`, assigning a fresh opaque `claim_token`, and setting a finite
lease. All renewals and state writes require the same token/fence. The worker
uses a fixed lock order (`pending_actions`, then intent) whenever it must
coordinate with a decision writer.

The implementation has two recovery categories:

1. A stale `claimed` row lacks a provider-start marker and can be reclaimed
   safely by a higher fence.
2. A stale `handoff_started` row may have reached a provider. It must be
   reconciled through Messenger using its immutable action key. It may become
   `delivered`, `retry_wait` only with proof of safe retry, or `ambiguous`; it
   cannot be directly claimed to send again.

Backoff is exponential with bounded jitter/cap and database-time scheduling.
Attempts continue while a pending action remains eligible; a long-lived
failure becomes a derived stuck alert rather than an untracked terminal drop.

**Alternative considered:** use the generic scheduler's due-row scan. Rejected
because that scan has no action fence or provider-handoff semantics and changes
would couple this control plane to unrelated notification behavior.

### D4 — Send-start is the cancellation linearization point

The worker resolves the current verified owner target and callback secret only
in memory. If either is absent, it writes a safe pre-handoff retry reason and
never calls the provider. Otherwise it enters a local transaction, locks the
action and intent, verifies `status='pending'` and an unexpired action, and
persists an attempt plus `handoff_started` under its fence. That commit is the
last cancellation-safe point.

Each terminal domain path out of pending uses the same connection transaction
to change the action and cancel the matching nonterminal intent. If the
decision/expiry wins before send-start, no provider call occurs. If send-start
wins, a later domain transition cancels future recovery but cannot revoke a
network call that may already be in flight. Any late delivery result is
append-only attempt evidence and cannot restore the action or intent to a
sendable state.

The worker has no code path that writes `pending_actions`; an observed
past-expiry action lets it cancel only its own intent. The normal expiry
operation remains the sole domain transition writer.

**Alternative considered:** hold the transaction while calling Messenger.
Rejected because a network wait would hold action locks and still cannot
transactionally undo a provider side effect.

### D5 — Messenger owns idempotency and ambiguous egress truth

The current `notify.v1` response is an in-memory success/failure shape and
Messenger routes `approval_request` inline. Future `NotifyDeliveryV1` adds a
required, non-secret delivery idempotency key for recovery callers. Switchboard
validates and forwards it. At the actual Messenger provider boundary, a new,
narrowly wired approval-handoff ledger is keyed by it and returns a normalized
safe classification:

| Boundary result | Definition | Local action |
| --- | --- | --- |
| `confirmed` | Provider acceptance/duplicate acknowledgement or a reconciled receipt proves the same key completed. | Mark intent `delivered`. |
| `safe_retry` | No provider call began, or the adapter/reconciliation contract proves reuse of the same key cannot duplicate. | Back off and retry the same key. |
| `ambiguous` | A provider-start record exists but no confirmation/reconciliation proof exists. | Mark intent `ambiguous`; reconcile only, never blindly resend. |

The new ledger must be used on the real `route.execute`/provider path. It is
not a restoration of Messenger's retired, unwired generic delivery-request
tables. Provider-specific adapters may add true idempotency or lookup support
later, but they may not label an unknown post-start outcome safe merely to
increase retries.

**Alternative considered:** interpret a client timeout as a retryable
`notify()` error. Rejected because the Messenger/provider call may already have
succeeded even though the source daemon did not receive the result.

### D6 — Safety vocabulary and truthfulness are schema/API contracts

Migration checks constrain intent state, mode, handoff class, and reason code
to closed values. The API projects a small `ApprovalDeliveryStatus` instead of
the legacy `push_outcome` as authoritative truth:

- `state`, `mode`, safe `last_reason_code`, attempt count, `next_attempt_at`;
- `stuck` and `ambiguous` booleans derived server-side; and
- a legacy evidence indicator only while old emission rows remain.

The dashboard distinguishes “waiting for quiet hours,” “retrying,” “delivery
uncertain,” “collapsed into digest,” and “cancelled by decision” from a
confirmed provider handoff. It must never infer “owner was never notified”
from a null/failed old push row. No recipient, tool arguments, token, raw
provider error, full message, or secret enters a list API, frontend type,
metric label, or user-visible diagnostic.

**Alternative considered:** store raw exception text for debugging. Rejected:
it can contain target identity or provider content and makes a closed recovery
state impossible to reason about across consumers.

### D7 — Retention preserves unresolved safety evidence

Attempts are append-only for an intent's lifetime. A safe terminal summary is
also appended to the approval event spine, whose existing historical
provenance rules outlive mutable action rows. Routine retention never deletes a
nonterminal or `ambiguous` intent while its action remains pending. Terminal
intent/attempt rows are removed only in the same retention phase as their
terminal action; migration downgrade refuses to drop any nonempty new table.

This intentionally favors an observable stale intent over deletion/replay. It
also allows an application binary rollback to leave additive data intact until
a compatible binary returns, rather than converting it into a live provider
send or a domain mutation.

## Risks / Trade-offs

- **Provider ambiguity can leave an owner notification unresolved.** → Show
  `ambiguous`/stuck truth, keep dashboard decisions available, and prohibit
  speculative duplicates until an adapter gains a proof-bearing reconcile path.
- **A source worker may crash after a remote call.** → Messenger's key ledger
  is the reconciliation authority; the source's send-start marker never alone
  permits another send.
- **Concurrent decision and worker sends are intrinsically non-transactional.**
  → Make send-start an explicit durable linearization point, cancel on the
  winner, and test both orderings.
- **A per-schema worker can increase background load.** → Claim in bounded
  batches, use due indexes and capped retry scheduling, and expose backlog/oldest-due
  metrics before enabling more schemas.
- **Legacy push data can confuse operators during rollout.** → Mark it
  explicitly legacy in API/UI and never synthesize/backfill it into new intents.
- **A migration downgrade can lose recovery evidence.** → Use guarded
  non-destructive downgrade checks, not a destructive “rollback.”

## Migration Plan

1. Add an additive Approvals migration for intent/attempt tables, constraints,
   due/lease indexes, and safe approval-event vocabulary; add a separately
   owned, wired Messenger handoff migration for stable action-key
   reconciliation. Do not execute either in this change.
2. Release compatible read paths and observability with the new writer/worker
   disabled. Existing emission rows stay readable as legacy evidence.
3. Add the atomic parking helper and terminal transition helper, update all
   listed producers, and enable new writes for newly parked actions only. Do
   not dual-send a legacy emission and a new intent.
4. Enable the worker after real-PostgreSQL fault/concurrency coverage and an
   owner-authorized staging/canary drill. Expand schema-by-schema while
   watching due age, lease expiry, ambiguous count, and no duplicate handoffs.
5. Keep schema and data on binary rollback. Disable new admission first; do
   not downgrade/drop while any intent/attempt/event evidence exists. Active
   intents remain visible and recover only when a compatible worker returns.

## Open Questions

- Which current provider adapters can accept/reconcile a stable idempotency
  key today, and which must return `ambiguous` after every post-start timeout?
  The implementation packet requires an adapter capability inventory before
  enablement; it may not assume Telegram has one.
- What bounded retry and stuck-SLO values best fit the existing daemon cadence?
  Choose them as explicit reviewed constants/configuration with database-time
  tests; do not silently inherit the generic scheduler's polling interval.
- Should the safe terminal event be one generic delivery-summary event or a
  small closed family of event types? The migration must preserve existing
  approval-event retention/provenance checks either way.
