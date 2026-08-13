# Durable Approval Delivery Intent Recovery Plan

**Status:** Planning packet only — implementation requires RFC 0023 owner sign-off and a separately authorized implementation gate.

**Goal:** Make every newly parked approval action atomically carry one durable,
idempotent notification-delivery intent; recover owner notification through a
fenced, notification-only worker without ever approving, executing, expiring,
deferring, editing, or otherwise mutating the parked domain action.

**Architecture:** The shared approval parking helper becomes a transactional
outbox boundary in each owning schema. It inserts `pending_actions` plus a
unique `approval_delivery_intents.action_id` row in one transaction while it
also makes RFC 0021 quiet-hours and burst admission durable. A daemon-owned
worker claims due intents through `SKIP LOCKED`, token/fence/lease CAS, and a
pre-provider handoff marker. It renders a deterministic `notify.v1` envelope
only while its local action remains pending, then asks Switchboard/Messenger to
reconcile the immutable action key. Messenger owns the actual provider-handoff
ledger and returns `confirmed`, `safe_retry`, or `ambiguous`; an unknown
post-start provider result is never blindly resent. Terminal action writers
cancel the intent atomically. New state is visible through safe API/metrics
projections and retained until it is safe to clean.

**Governing artifacts:** RFC 0023, OpenSpec change
`durable-approval-delivery-intent-recovery`, RFC 0021, RFC 0017, RFC 0022.

## Hard boundaries

- Planning phase creates no source implementation, migration execution, live
  provider replay, owner message, entity/fact mutation, deploy/restart,
  approval decision/execution, or historical-intent backfill.
- The future worker is deterministic daemon infrastructure. It does not load a
  model, call approval operations, invoke an executor, write a domain action,
  or receive an entity/fact service.
- Pending actions remain the sole authorization boundary. A notification result
  never changes an action from `pending`; only existing authenticated
  decision/expiry paths do that.
- No new approval intent uses `deferred_notifications`, the ordinary deferred
  scheduler, PostgreSQL `NOTIFY`, or the active generic quiet-hours wake
  recovery protocol. Those systems retain their own contracts.
- Recipient identity, callback secret/token, raw message, tool args, raw
  provider payload, and raw exception text are never persisted in the intent
  state, exposed by API/metrics, or copied into a provider-recovery reason.
- No downgrade or emergency rollback deletes/replays new intent data. If a
  compatible worker is unavailable, actions remain pending and dashboard
  decisions remain available.

## Current source trace

`src/butlers/modules/approvals/park.py::park_pending_action()` currently
executes an `INSERT pending_actions(status='pending')` and subsequently calls
`emit_approval_push()`. `approval_push_emissions` is separately reserved, and
quiet-hours delivery may go to generic `deferred_notifications`. Neither is
atomic with the pending action or a recoverable work claim.

The implementation must convert every actual production caller below. The
`core/approvals_hooks.py` wrapper is a forwarding seam, not an additional
pending-row producer, and must preserve the new typed helper contract.

| # | Source | Existing parked operation | Future admission responsibility |
| --- | --- | --- | --- |
| 1 | `src/butlers/modules/approvals/gate.py:866` | Generic gated tool with no eligible rule | `ParkRequest` plus action/intent/audit in one transaction. |
| 2 | `src/butlers/modules/approvals/email_guard.py:281` | Email context mismatch | Same helper; retain existing fail-closed recipient decision. |
| 3 | `src/butlers/modules/approvals/email_guard.py:367` | Non-owner email recipient | Same helper; retain email guard’s audit/allowed behavior. |
| 4 | `src/butlers/modules/approvals/email_guard.py:572` | Non-owner channel-general recipient | Same helper; retain recipient guard behavior. |
| 5 | `src/butlers/core_tools/_notifications.py:667` | Missing entity-channel identifier | Same helper; unavailable runtime may not omit an intent. |
| 6 | `src/butlers/daemon.py:1732` | Calendar overlap override | Same helper; retain calendar-specific action/audit context. |
| 7 | `src/butlers/api/routers/ingestion_connectors.py:1318` | Dashboard soft connector disconnect | Same helper; remove per-request immediate-push dependency. |
| 8 | `roster/relationship/tools/relationship_assert_fact.py:443` | Relationship assertion | Same helper with relationship origin. |
| 9 | `roster/relationship/jobs/relationship_jobs.py:2691` | Memory/fact retraction | Same helper; retain curation dedup/read semantics. |
| 10 | `roster/relationship/jobs/relationship_jobs.py:3219` | Entity merge | Same helper; preserve durable ordered-pair `deduplication_key`. |
| 11 | `roster/relationship/jobs/relationship_jobs.py:3717` | Email identity enrichment assertion | Same helper; retain curation source evidence. |
| 12 | `roster/relationship/jobs/relationship_jobs.py:4069` | Memory reclassification | Same helper; retain curation source evidence. |

The static contract must also scan direct pending `INSERT`s. It explicitly
exempts direct `status='approved'` auto-approval paths because they are not
parked and require no owner notification.

## Target data and state contract

### Schema-local intent

The future `approvals_014`-successor migration (exact revision chosen only at
implementation time after checking live migration heads) adds an additive
schema-local table conceptually shaped as:

| Field | Constraint / purpose |
| --- | --- |
| `id` | UUID primary key. |
| `action_id` | `UNIQUE`, non-null FK to `pending_actions(id)`. |
| `action_key` | `UNIQUE`, immutable `approval:<schema>:<action-id>` string. |
| `origin_butler` | Validated nonempty owning origin. |
| `mode` | Closed `single|burst_digest|collapsed`. |
| `state` | Closed `ready|claimed|handoff_started|retry_wait|delivered|collapsed|cancelled|ambiguous`. |
| `not_before`, `next_attempt_at` | Database-time RFC 0021 admission/retry schedule. |
| `attempt_count` | Monotonic counter for safe attempt observability. |
| `claim_token`, `claim_fence`, `claim_expires_at` | Opaque token, monotonic fence, finite lease. |
| `last_reason_code` | Closed, safe vocabulary only. |
| `created_at`, `updated_at`, `terminal_at` | Auditable lifecycle timestamps. |

`approval_delivery_attempts` is append-only and scoped to the intent. It holds
only attempt sequence, claim fence, start/completion time, normalized outcome,
safe reason, and optional bounded opaque provider receipt reference. It does
not hold raw outbound content or a provider response body. The approval event
vocabulary gains one safe delivery-summary event (or a reviewed, closed small
family) so an immutable record survives the shorter mutable-intent lifetime.

### State machine and race boundary

```text
atomic park
  pending_actions + intent
          |
          +-- RFC 0021 collapsed --> collapsed (no egress)
          |
          +-- due --> ready --claim/fence--> claimed
                                          |
                     safe pre-handoff fail +---> retry_wait --backoff--> ready
                                          |
                action still pending + send-start marker --> handoff_started
                                                   |         |          |
                                             confirmed   safe retry   unknown
                                                   |         |          |
                                              delivered  retry_wait  ambiguous

decision / canonical expiry wins before send-start: pending action + intent -> cancelled
decision after send-start: action terminal; intent -> cancelled (no future recovery)
```

The committed `handoff_started` record is the explicit linearization point:
before it, a terminal decision/expiry transaction wins and prevents egress;
after it, no worker may send again, but an in-flight external call cannot be
retracted. The worker has only intent/attempt write authority in either case.

### Provider boundary

The worker includes `delivery.idempotency_key = action_key` in a recovery
`notify.v1` envelope. Switchboard forwards it unmodified. Messenger, on the
real `route.execute` / channel-adapter path, persists a narrowly wired
handoff ledger keyed by it before provider start:

| Messenger response | Required source effect | Provider rule |
| --- | --- | --- |
| `confirmed` | Mark intent delivered under its fence. | No additional send. |
| `safe_retry` | Back off then reuse the exact same key. | Only if no provider start or adapter proves same-key safety. |
| `ambiguous` | Mark intent ambiguous; reconciliation only. | Never blind resend. |

This replaces neither ordinary `notify.v1` behavior nor Messenger’s retired,
unwired generic tracking tables. Telegram must be treated as no-proof after a
post-start timeout until a real adapter capability proves otherwise.

## Implementation packets

The parent may create/reroute implementation Beads only after owner sign-off.
Each packet below is independently reviewable; no packet grants a live action,
provider, or migration-execution authority by itself.

### Packet A — Contract, migrations, and real-PostgreSQL shape

**Depends on:** owner acceptance of RFC 0023; reviewed provider capability
inventory and constants.

**Files:**

- Add: `src/butlers/modules/approvals/migrations/014_approval_delivery_intents.py`
- Add: `roster/messenger/migrations/004_approval_egress_handoffs.py`
- Modify: `src/butlers/modules/approvals/models.py`
- Modify: `src/butlers/modules/approvals/events.py`
- Add/modify: `tests/modules/test_approvals_migrations.py`
- Add: `tests/integration/test_approval_delivery_intent_migrations.py`

**Work:**

1. Survey both live migration chains immediately before writing revisions;
   retain these planned filenames only if their heads remain `approvals_013` and
   `msg_003`, otherwise renumber without changing the contract, and preserve
   the approvals historical provenance/guarded-downgrade conventions.
2. Add tables, unique action/action-key constraints, checks, due/lease indexes,
   append-only attempt protections, and safe event vocabulary. Use guarded
   `to_regclass` shape checks only where the existing chain requires them.
3. Add a real-provider-boundary Messenger handoff table, not old generic
   `delivery_requests`/attempt/receipt/dead-letter tables.
4. Make downgrade fail closed if any new intent, attempt, or safe audit
   evidence exists; never write a destructive “cleanup” downgrade.

**Acceptance / tests:** Fresh and upgraded real PostgreSQL DBs have the same
schema; old `approval_push_emissions` and generic deferred rows are untouched;
no intent appears for historical pending actions; constraints reject unknown
vocabulary; and downgrade rejects nonempty data.

### Packet B — Atomic parking choke point and all producer conversion

**Depends on:** Packet A.

**Files:**

- Modify: `src/butlers/modules/approvals/park.py`
- Modify: `src/butlers/modules/approvals/notifications.py`
- Modify: `src/butlers/core/approvals_hooks.py`
- Modify: all twelve rows in the current source-trace table
- Add: `tests/contracts/test_approval_pending_action_choke_point.py`
- Add/modify: `tests/integration/test_approval_delivery_intent_admission.py`
- Modify: `tests/integration/test_approval_push_on_park.py`

**Work:**

1. Replace optional `approval_push_runtime` admission behavior with a typed
   `ParkRequest` whose required origin and safe synopsis are validated before
   the transaction.
2. Acquire one connection and use one transaction for action insertion or
   semantic-key resolution, per-schema burst lock/count, quiet-hours
   `not_before`, intent insert, and required queued-event writes.
3. Preserve action semantics specific to each producer; do not make a
   curation job execute/retry the parked work just because it has an intent.
4. Keep `approval_push_emissions` legacy read-only after cutover; no dual
   emission and no historical replay/backfill.
5. Make a robust source/AST test enumerate all production `pending` insertion
   paths, rather than a fragile count-only grep.

**Acceptance / tests:** Inject a failure after each transactional write and
prove all-or-nothing rollback; run concurrent semantic-key and burst admission
against real PostgreSQL; prove every listed producer uses the common helper;
and prove direct auto-approved inserts remain exempt.

### Packet C — Local intent repository and notification-only worker

**Depends on:** Packets A–B.

**Files:**

- Add: `src/butlers/modules/approvals/delivery_intents.py`
- Add: `src/butlers/core/approval_delivery_worker.py`
- Modify: `src/butlers/daemon.py`
- Modify: `src/butlers/background.py` only if lifecycle registration requires it
- Modify: `src/butlers/modules/approvals/notifications.py`
- Add: `tests/core/test_approval_delivery_worker.py`
- Add: `tests/integration/test_approval_delivery_intent_recovery.py`

**Work:**

1. Implement repository methods for due selection, claim, heartbeat, fenced
   pre-handoff marker, safe retry, cancellation observation, completion, and
   reconciliation. Every mutation predicates on the current token/fence.
2. Start/stop the loop under daemon lifecycle only when the Approvals module is
   active. Give it a narrow runtime that can resolve owner/callback data and
   invoke/reconcile notification dispatch, not an approvals/executor object.
3. At dispatch time, read the local action only to verify `pending` and render
   deterministic dossier/digest text. Resolve recipient and callback secret in
   memory; persist neither.
4. Use bounded exponential jittered backoff driven by database time. A stale
   `claimed` lease can be re-claimed; stale `handoff_started` must reconcile,
   not send.

**Acceptance / tests:** Two workers race on one row without a double claim;
stale tokens/fences cannot transition after a successor; crash/restart before
send-start retries exactly the same action key; and worker imports/capability
tests show no calls to approval decision/execution/domain mutation APIs.

### Packet D — Notify/Messenger stable-key handoff

**Depends on:** Packets A and C.

**Files:**

- Modify: `roster/switchboard/tools/routing/contracts.py`
- Modify: `roster/switchboard/tools/notification/deliver.py`
- Modify: `roster/switchboard/modules/tools.py`
- Modify: `src/butlers/core_tools/_notifications.py`
- Modify: `src/butlers/core_tools/_routing.py`
- Modify: Messenger adapter-facing code under `roster/messenger/` as located
  by the provider capability inventory
- Add/modify: `roster/switchboard/tests/test_deliver_unit.py`
- Add/modify: `roster/switchboard/tests/test_contract_models.py`
- Add: `roster/messenger/tests/test_approval_egress_handoffs.py`

**Work:**

1. Extend only recovery-keyed `NotifyDeliveryV1` traffic with a stable
   idempotency key and normalized result class, maintaining backward
   compatibility for ordinary calls.
2. Thread that key across Switchboard into Messenger’s direct provider route.
   Messenger writes its durable pre-call handoff before adapter invocation and
   exposes a same-key reconciliation operation through the existing trusted
   boundary.
3. Define exact adapter capabilities. Only an adapter that demonstrates
   duplicate-safe key reuse or receipt lookup may classify post-start work
   `safe_retry`; otherwise return `ambiguous`.
4. Ensure source result processing cannot create a fresh action key, mutate the
   action, or use a generic retry after an ambiguous response.

**Acceptance / tests:** Confirmed receipt replay triggers one provider call;
pre-start validation failure backoffs safely; timeout after start with no
provider proof becomes ambiguous and survives restart without a second call;
all results are redacted/safe.

### Packet E — Terminal transition fencing, retention, and safe UI truth

**Depends on:** Packets A–D.

**Files:**

- Modify: `src/butlers/modules/approvals/operations.py`
- Modify: `src/butlers/modules/approvals/module.py`
- Modify: `src/butlers/api/routers/approvals.py`
- Modify: `src/butlers/api/models/approval.py`
- Modify: `src/butlers/modules/approvals/retention.py`
- Modify: `frontend/src/api/types.ts`
- Modify: `frontend/src/pages/ApprovalsPage.tsx`
- Modify: `frontend/src/pages/ApprovalsPage.test.tsx`
- Modify/add: `tests/modules/test_approvals_retention.py`,
  `tests/api/test_approvals.py`, `tests/integration/test_approval_delivery_intent_recovery.py`

**Work:**

1. Refactor approve, reject, stale-expiry, explicit expiry, and all future
   pending-to-terminal writers through a shared action-then-intent
   transactional transition helper. Audit direct `UPDATE pending_actions` SQL.
2. Make `handoff_started` an explicit race boundary. A decision before it
   prevents dispatch; a decision after it stops future recovery but does not
   fabricate that the provider effect was retracted.
3. Add retention-order checks and immutable safe delivery summaries. Never
   remove active/retrying/claimed/handoff-started/ambiguous intent rows while
   the action is pending.
4. Replace authoritative `push_outcome` UI logic with a safe delivery status
   projection and mark legacy outcomes as legacy. Surface retry, delayed,
   collapsed, ambiguous, cancelled, and stuck truth without secrets/targets.
5. Add metrics/read-model fields for per-safe-state count, oldest due age,
   expired lease count, and ambiguous/stuck count; no operator control may
   mutate the parked action outside normal decision endpoints.

**Acceptance / tests:** Real-PostgreSQL races cover decision-first and
send-start-first; a worker cannot write `pending_actions`; retention and
downgrade preserve unresolved evidence; API/frontend snapshot/contract tests
prove exact safe display and redaction.

### Packet F — End-to-end validation and staged release

**Depends on:** Packets A–E, independent review, owner-authorized staging
drill.

**Files:**

- Modify: implementation test files above only as gaps emerge
- Modify: `docs/` rollout/runbook content only if review identifies an
  operational omission

**Work:**

1. Run the complete fault matrix below on a migrated real PostgreSQL database.
2. Deploy additive schema and read paths with writer/worker disabled; verify
   old rows remain legacy-only and no dual send happens.
3. In a staging/canary environment with synthetic newly parked actions only,
   exercise quiet hours, multi-worker lease steal, restart at every durable
   boundary, provider duplicate proof, ambiguous no-resend, and decision race.
4. Enable new writers/workers progressively per owning schema only after
   metrics/read-model evidence is reviewed. Do not use a historical replay to
   “catch up.”
5. Treat application rollback as additive: disable new admission first, retain
   schema/data, and wait for a compatible worker. Do not downgrade while any
   intent/attempt/evidence rows exist.

## Required real-PostgreSQL test matrix

| Area | Fault/concurrency proof | Expected invariant |
| --- | --- | --- |
| Atomic admission | Raise after action insert, after burst reservation, after intent insert, and on semantic-key conflict. | No orphan action/intent; duplicate resolves one pair. |
| Producer coverage | Invoke all 12 producer seams and source/AST scan all direct pending writes. | Every pending action has exactly one intent; auto-approved exception remains explicit. |
| Burst / quiet policy | Concurrent parks across first-three/fourth/later; quiet interval/DST boundary; post-admission policy edit. | One digest, collapsed evidence, exact stored release, no re-gate, no generic deferred row/budget use. |
| Claims | Two pools/workers, `SKIP LOCKED`, lease expiry, heartbeat, fence/token mismatch. | One current owner; stale worker cannot write/send. |
| Crash/restart | Stop at claim, marker, Messenger handoff record, provider accepted before source response, result persistence. | Safe retry only before/proven-safe start; otherwise reconcile/ambiguous; no duplicate provider call. |
| Provider classes | Fake proof-bearing provider and Telegram-like no-proof adapter. | Same-key confirmed dedup; unknown post-start no resend. |
| Decision race | Approve/reject/expiry before marker and marker before each decision. | Domain transaction cancels when it wins; worker never mutates action; late result cannot revive. |
| Retention / rollback | Pending/ambiguous and terminal rows; binary rollback; migration downgrade. | Unresolved data retained; downgrade fails closed; no replay/delete. |
| API/UI | New, delayed/retry/collapsed/ambiguous/cancelled, and legacy rows. | Truthful safe state; no secret/recipient/raw error leakage or “never attempted” fabrication. |

## Verification sequence for the future implementation PR

Run from the exact implementation head after each relevant packet; do not
claim completion from planned tests alone.

1. `openspec validate durable-approval-delivery-intent-recovery --strict`
2. Run `uv run pytest tests/modules/test_approvals_migrations.py tests/modules/test_approval_push_notifications.py tests/modules/test_approvals_retention.py`.
3. Run the focused real-PostgreSQL suite with Docker available, including
   `uv run pytest -m integration tests/integration/test_approval_delivery_intent_admission.py tests/integration/test_approval_delivery_intent_recovery.py`.
4. Run Switchboard/Messenger contract tests and the source coverage test:
   `uv run pytest roster/switchboard/tests/test_contract_models.py roster/switchboard/tests/test_deliver_unit.py roster/messenger/tests/test_approval_egress_handoffs.py tests/contracts/test_approval_pending_action_choke_point.py`.
5. Run focused API/frontend tests using the repository’s current frontend
   package scripts, then typecheck/lint the touched surfaces.
6. Run the broader affected approval/notify/scheduler regression suite; inspect
   all required and full hosted check rollups from the exact pushed head.
7. Re-fetch/rebase the PR on live `origin/main`, rerun changed-head gates,
   obtain independent exact-head review, and use the repository’s exact-base
   merge helper only if a separately authorized owner asks to merge.

## Rollout and rollback decision table

| Stage | New writer / worker | Legacy data | Rollback posture |
| --- | --- | --- | --- |
| Additive schema/read deploy | Disabled | Read as legacy; no backfill/replay | Safe to remove binary, retain schema. |
| Staging/canary | Enabled only for synthetic new actions | Untouched | Disable admission; preserve active intent evidence. |
| Progressive production enable | Per schema after evidence | Legacy rows age out normally | Do not fall back to immediate legacy push for new intents. |
| Emergency binary rollback | Disabled before rollback if possible | Intents remain visible | Old binary is not a recovery worker; return compatible binary, never delete/replay/approve. |
| Schema downgrade | Never routine | New rows block it | Fail closed while any intent/attempt/audit row exists. |

## Completion gate

Implementation can be proposed as complete only when all RFC 0023/OpenSpec
requirements have real-PostgreSQL evidence, provider capability claims are
demonstrated rather than assumed, every producer is covered, no unsafe state is
exposed, exact-head CI/review is green, and an owner has separately authorized
any live rollout. This planning packet alone grants none of those execution
actions.
