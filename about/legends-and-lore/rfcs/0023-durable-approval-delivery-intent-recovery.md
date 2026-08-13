# RFC 0023: Durable Approval Delivery Intent Recovery

**Status:** Proposed — owner sign-off required before implementation
**Date:** 2026-08-13
**Related:** RFC 0006 (schema isolation), RFC 0017 (owner-routing safety),
RFC 0019 (parked automation), RFC 0021 (one-tap approvals), RFC 0022
(cross-process event transport), `about/heart-and-soul/security.md`
(Approval Gates)

---

## Summary

An approval action is safe only when it remains pending until an authenticated
human decides it. Its notification is also consequential: without a durable
record and recovery path, a process crash or transport ambiguity can strand a
pending action invisibly. The current post-park push is a best-effort
post-commit effect, so it cannot prove that a pending action has a recoverable
owner-notification intent.

This RFC makes approval notification a durable, schema-local control-plane
protocol. Parking a new action and creating exactly one delivery intent happen
in one database transaction. A deterministic, notification-only worker claims
those intents with a fence, retries safe pre-handoff failures with backoff,
and delegates provider idempotency/ambiguity to the actual Messenger egress
boundary. It may change intent and attempt records, but it has no authority to
approve, reject, expire, execute, defer, edit, or otherwise mutate the parked
domain action.

The protocol completes RFC 0021's delivery reliability boundary; it does not
weaken its human gate or change its quiet-hours, budget, or burst policy.

## Doctrine position

The system remains parked-first and fail-closed:

- A notification is an aid to owner attention, never an authorization to act.
  `pending_actions.status` remains the sole decision/execution gate.
- The recovery worker is deterministic daemon infrastructure. It invokes no
  model, executes no approved tool, and never calls an approval decision or
  executor API.
- Each intent stays in the schema that owns its pending action. It reaches
  Switchboard and Messenger only through the existing authenticated
  `notify.v1` path; no worker receives a peer pool, DSN, or direct schema
  grant (RFC 0006).
- Owner recipients and callback secrets are resolved only at a safe egress
  attempt through existing owner-routing and credential boundaries. Neither is
  persisted in an intent, attempt, API response, metric label, or audit error.
- An uncertain provider send is not an invitation to send again. We prefer an
  honest, visible `ambiguous` state to a duplicate owner control-plane message.

## Current failure boundary

`park_pending_action()` currently inserts `pending_actions(status='pending')`
and only then calls `emit_approval_push()`. That helper independently reserves
`approval_push_emissions`, may create a generic `deferred_notifications` row,
and invokes the live delivery runtime. A crash or unavailable runtime between
those effects leaves no authoritative recovery record. The generic deferred
pass has neither an approval-action foreign key nor a claim fence, durable
attempt ledger, bounded retry schedule, terminal-decision cancellation, or
ambiguous-provider semantics.

`approval_push_emissions` remains useful legacy evidence during rollout, but
its `delivered|deferred|collapsed|duplicate|failed` projection is not a
delivery intent state machine. This RFC does not backfill it, replay it, or use
it as the new worker queue.

## Normative design

### 1. Atomic admission and stable identity

Every new `pending` action SHALL be created through one ownership-schema
transaction that also creates one `approval_delivery_intents` row:

| Field / invariant | Contract |
| --- | --- |
| `action_id` | Non-null foreign key to the newly inserted `pending_actions.id`, unique across the intent table. |
| `action_key` | Immutable, deterministic `approval:<owning-schema>:<action_id>` key; unique and used end-to-end at the notification boundary. |
| `origin_butler` | Required validated origin name; a missing or invalid origin fails admission before the action commits. |
| `mode` | `single`, `burst_digest`, or `collapsed`, selected in the same transaction under the existing per-schema burst serialization. |
| timing | `not_before` and initial `next_attempt_at` are the RFC 0021 admission decision, derived from database time and the Owner Attention Policy. |
| safety | Only closed state/reason values and bounded safe metadata are stored. No recipient, callback token/secret, rendered message, raw provider response, or free-form exception is retained. |

The transaction inserts the action, computes the RFC 0021 burst mode and
quiet-hours release time, inserts the intent, and commits together. A unique
producer deduplication conflict returns the already-admitted action/intent
pair; it never creates a second intent or a fresh notification key. An action
is not committed without its intent, and an intent is not committed without its
action.

`collapsed` is still a durable intent, but it is terminal at admission and has
no provider handoff. A `burst_digest` intent is the one deterministic digest
for the window. This preserves the existing first-three / one-digest / later
collapse behavior while making every parked action observable.

### 2. Closed state and reason vocabulary

The intent state is intentionally smaller than provider implementation detail:

| State | Meaning | May make a provider call? |
| --- | --- | --- |
| `ready` | Admitted and due, but not claimed. | No |
| `claimed` | A worker owns a bounded lease and fence. | No |
| `handoff_started` | The final cancellable boundary passed and an immutable attempt-start record committed. | One fenced/reconciled attempt only |
| `retry_wait` | No provider side effect is known; retry at `next_attempt_at`. | Not until reclaimed |
| `delivered` | Messenger/provider boundary confirmed acceptance for this action key. It does not assert owner read. | No |
| `collapsed` | RFC 0021 burst policy deliberately suppressed this action's direct push. | No |
| `cancelled` | A decision/expiry won before send-start, or recovery stopped after a decision raced a started handoff. | No |
| `ambiguous` | A post-start provider outcome cannot be proven safe to retry. | Reconciliation only |

`stuck` is an observable derived condition, not a writeable terminal state:
due `ready`/`retry_wait` work older than the configured recovery SLO, an
expired `claimed`/`handoff_started` lease, or any `ambiguous` intent is stuck.
This keeps the state machine small while making actionability visible.

The only persisted reason codes are versioned allowlists such as
`quiet_hours`, `owner_recipient_unavailable`, `callback_secret_unavailable`,
`transport_unavailable`, `provider_preflight_failed`,
`provider_outcome_unknown`, `action_approved`, `action_rejected`,
`action_expired`, and `action_abandoned`. New code must reject an unknown code.
Raw exception text, recipient values, callback material, message content, and
provider payloads stay in protected operational logs where already permitted,
not in the durable cross-surface state.

### 3. Fenced notification-only worker

Daemon lifecycle owns a dedicated approval-delivery loop for every daemon that
owns the Approvals module. The worker receives only:

1. its local pool and intent/attempt repository;
2. a deterministic envelope renderer plus current owner-recipient and callback
   secret resolvers; and
3. a narrow `notify.v1` dispatch/reconciliation client.

It does not receive an approval operations object, executor, action-mutation
repository, entity/fact service, or generic scheduler queue writer. It may
read the associated action to render and verify pending status; it may write
only intent/attempt/audit-observability records.

Claims use `FOR UPDATE SKIP LOCKED` and an atomic transition that increments a
monotonic `claim_fence`, assigns an unpredictable `claim_token`, and sets a
short `claim_expires_at`. Every heartbeat and transition includes
`(intent_id, claim_token, claim_fence)` in its predicate. A stale worker
therefore cannot renew a successor lease, write a terminal outcome, or start a
second handoff. A stale `claimed` lease can be safely reclaimed because no
provider-start record exists. A stale `handoff_started` lease is never blindly
reclaimed for send; it enters reconciliation and remains `ambiguous` absent
proof of safe retry.

Safe failures before the provider-start marker enter `retry_wait`. Backoff is
deterministic, exponentially increasing with jitter, capped at a bounded delay
and retried until the action becomes terminal/expired or a provider outcome is
ambiguous. This is at-least-once recovery for work that has not crossed an
uncertain side-effect boundary; it is not an unsound exactly-once claim.

### 4. Provider handoff and ambiguity

The source worker carries `action_key` as the required `notify.v1` delivery
idempotency key. Switchboard forwards it unchanged. Messenger, at the actual
provider boundary, owns a narrowly wired handoff/reconciliation ledger keyed
by that value. It is not a revival of the retired generic Messenger delivery
tracking tables.

Before a provider call, Messenger durably records a handoff attempt. It returns
one normalized class, with a safe code and optional opaque receipt reference:

| Handoff class | Source-worker transition | Retry rule |
| --- | --- | --- |
| `confirmed` | `delivered` | No repeat. A provider duplicate acknowledgement for the same key is also confirmed. |
| `safe_retry` | `retry_wait` | Retry with the same key after backoff; valid only when no provider effect started or a provider idempotency/reconciliation guarantee proves it harmless. |
| `ambiguous` | `ambiguous` | Do not send again. Reconcile the same key only; no new key or speculative duplicate is allowed. |

For a provider without a durable idempotency or lookup capability (Telegram is
the important current case), a crash, timeout, or lost response after the
provider-start marker is `ambiguous`. A later worker may ask Messenger for the
same key, but it cannot reissue the send merely because the source worker did
not receive a response. `delivered` means a confirmed handoff/acceptance at
the implemented boundary, never a claim that the owner read or acted on it.

### 5. Decision and expiry cancellation

Every action transition out of `pending` — approve, reject, explicit expiry,
stale-expiry sweep, and any future terminal path — SHALL run in the same local
transaction as a fenced cancellation of its nonterminal delivery intent. The
fixed lock order is action then intent. A future direct SQL update of a pending
action is prohibited by a contract test unless it goes through this shared
transition helper.

There is one explicit race boundary. The worker's transition to
`handoff_started` locks and verifies a pending, unexpired action in the same
transaction as its pre-provider attempt marker. If a decision/expiry commits
first, the worker observes cancellation and never starts the provider call. If
the marker commits first, an external call may already be in flight and cannot
be retracted; the later decision changes the intent to `cancelled` with a safe
post-start reason and blocks all future recovery. A late provider response is
recorded only on its attempt record and cannot revive the intent or mutate the
action.

The worker itself never changes `pending_actions.status`, extends expiry, or
triggers an executor. If it sees an already-expired but not-yet-swept action,
it cancels only its intent with `action_expired`; the canonical expiry path
performs the domain transition.

### 6. RFC 0021 preservation

This RFC preserves, rather than replaces, RFC 0021:

- One logical action receives one stable notification key. Edits, restarts,
  retries, and duplicate producer calls do not create a new push.
- Quiet hours use the same global Owner Attention Policy interval and store the
  exact first eligible time at admission. A later policy edit does not re-gate
  an existing intent.
- Approval control-plane notifications remain outside the insight daily budget;
  their anti-spam controls are per-action deduplication, quiet hours, and the
  ten-minute burst policy only.
- The first three parks in a window use direct intents; the fourth produces one
  digest; later parks are `collapsed`. The digest links to the dashboard and
  does not weaken a pending action's expiry or decision semantics.
- The generic `deferred_notifications` scheduler, its quiet-hours wake
  recovery work, and its ordinary notification budget policies are not a
  backing queue, claim protocol, or cancellation path for approval intents.

### 7. Retention, audit, and observability

`approval_delivery_attempts` is append-only for the intent lifetime and stores
only attempt number, fence, started/completed times, normalized outcome/reason,
and a bounded opaque provider reference. Intent terminal transitions write a
safe, immutable approval event summary so the existing longer-lived approval
audit spine can prove what happened after mutable intent rows are retained or
pruned.

Nonterminal and ambiguous intents are never deleted by routine retention while
their action is pending. Terminal intent and attempt rows follow the action's
existing terminal-retention horizon; the final safe event remains subject to
the approval-event retention/provenance policy. Cleanup is foreign-key and
retention-order aware and never silently converts an unresolved intent into a
terminal state.

The API/dashboard exposes only `delivery_state`, `mode`, safe
`last_reason_code`, attempt count, next eligible time, and an explicit
`stuck`/`ambiguous` indicator. It must not render a null or failed legacy push
as “never notified” when the durable state is unknown. Metrics and structured
logs include per-schema counts by safe state/reason, oldest due age,
lease-expiry count, ambiguous count, and worker scan/claim/handoff outcomes;
they exclude action arguments, recipients, secret material, message text, and
unbounded error strings.

### 8. Required producer coverage

The single parking admission must cover every current production pending-action
producer, with a source-level contract test that finds new direct pending
inserts. At proposal time the inventory is:

| Producer | Current source | Future contract |
| --- | --- | --- |
| Approval gate | `src/butlers/modules/approvals/gate.py` | Atomic gate parking intent. |
| Email context mismatch | `src/butlers/modules/approvals/email_guard.py` | Atomic email-guard parking intent. |
| Email non-owner recipient | `src/butlers/modules/approvals/email_guard.py` | Atomic email-guard parking intent. |
| Channel-general non-owner recipient | `src/butlers/modules/approvals/email_guard.py` | Atomic recipient-guard parking intent. |
| Missing notification identifier | `src/butlers/core_tools/_notifications.py` | Atomic core-notify parking intent. |
| Calendar overlap | `src/butlers/daemon.py` | Atomic daemon calendar-overlap parking intent. |
| Connector soft disconnect | `src/butlers/api/routers/ingestion_connectors.py` | Atomic dashboard-origin parking intent. |
| Relationship assertion | `roster/relationship/tools/relationship_assert_fact.py` | Atomic relationship parking intent. |
| Memory fact retraction | `roster/relationship/jobs/relationship_jobs.py` | Atomic curation parking intent. |
| Entity merge | `roster/relationship/jobs/relationship_jobs.py` | Atomic semantic-key parking intent. |
| Email identity enrichment | `roster/relationship/jobs/relationship_jobs.py` | Atomic curation parking intent. |
| Memory reclassification | `roster/relationship/jobs/relationship_jobs.py` | Atomic curation parking intent. |

Auto-approved inserts remain outside this contract because they are never
pending and never require owner notification. New producers may not opt out by
omitting a live runtime; admission creates the intent even when the delivery
worker is temporarily unavailable.

## Rollout and rollback

1. Land additive schemas and read compatibility first. No migration backfills
   `approval_push_emissions`, generic deferred rows, historical actions, or
   provider sends.
2. Ship the worker and API/dashboard read path with new writes disabled. Verify
   migration shape, role isolation, metrics, and that legacy rows still render
   as legacy evidence.
3. Enable the atomic writer and notification-only worker for newly parked
   actions only, first in an owner-authorized staging/canary environment, then
   gradually per owning schema. Never dual-send through legacy emission and
   the new intent for one action.
4. Retain legacy projection reads until old rows age out under existing
   retention. No new legacy row is synthesized after the cutover.

Binary rollback is additive: disable new admission before rolling back and do
not drop intent tables. If active, handoff-started, or ambiguous new intents
exist, an older binary is not a notification-recovery substitute; the durable
rows remain visible and recovery resumes only on a compatible binary. Schema
downgrade must fail closed while any intent/attempt/audit data exists, matching
the project’s guarded migration posture. An operator may not “fix” rollback by
deleting, replaying, approving, or executing historical actions.

## Verification contract

Implementation is not accepted without real-PostgreSQL tests for atomic
rollback, concurrent duplicate/semantic-key parks, exact burst admission,
fenced multi-worker claims, lease steal rejection, restart recovery at every
durable boundary, decision/expiry versus handoff races, provider-confirmed
idempotent replay, ambiguous no-resend, quiet-hours exact release/no re-gate,
budget isolation, retention guard, API redaction, and the complete producer
inventory. A source-only static test must reject any new direct
`pending_actions(status='pending')` write outside the shared admission helper.

## Rejected alternatives

- **Keep retrying `approval_push_emissions` from the next park call.** Rejected:
  no later park is guaranteed, so it cannot recover a stranded action.
- **Use generic `deferred_notifications` as the durable intent queue.**
  Rejected: its lifecycle does not bind action decisions, has no provider
  ambiguity fence, and is independently evolving quiet-hours infrastructure.
- **Use PostgreSQL `NOTIFY` as the queue.** Rejected by RFC 0022: it is a
  wake-up hint, not durable work or replay authority.
- **Hold a database transaction over the provider call.** Rejected: it turns
  a network outage into lock contention and still cannot make an external
  provider call transactional.
- **Blindly resend after timeout.** Rejected: an owner control-plane duplicate
  is worse than a visible recovery hold when the provider cannot prove absence.
- **Let the worker expire or approve an action to clear its queue.** Rejected:
  it crosses the approval safety boundary. Domain transitions remain canonical
  decision/expiry operations.
