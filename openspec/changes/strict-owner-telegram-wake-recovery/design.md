## Context

`notify()` now persists a full resolved `notify.v1` envelope in the originating
butler schema when an eligible routine owner-default send is held by the Owner
Attention Policy or a suppressing context. The ordinary scheduler later reads
due `pending` rows, composes rows only by the stored `(channel, recipient)`
target, and sends them without recalculating policy. That is intentionally a
local, durable queue: Switchboard and Messenger do not have permission to scan
another butler's `deferred_notifications` table.

The existing ingress authority is also intentionally narrow. The Switchboard
commits a `switchboard.message_inbox` row and matching
`public.ingestion_events` row in one deduplicated transaction. The latter's
UUID7 is the accepted request reference. Telegram updates can be replayed and
provider sends can time out after a side effect, so neither connector receipt
nor a successful in-memory callback is enough to authorize or prove a release.

This design applies the owner decision without relaxing the doctrine: only
Switchboard may coordinate cross-butler work, Health owns its `sleeping`
context, Messenger owns Telegram egress, and each origin retains its own
notification content. The packet defines future persistent records and MCP
tools only; it creates none in this change.

## Goals / Non-Goals

**Goals:**

- Release exactly one composed, exact-target cohort only from a durable,
  qualifying owner Telegram-bot event.
- Make duplicates, stale workers, participant loss, observed DND blocks,
  process crashes, and ambiguous provider outcomes safe and observable; defer
  the canonical cross-writer DND race contract to its prerequisite.
- Preserve origin-schema content ownership and MCP-only cross-butler
  communication.
- Make all owner choices fail closed when required evidence or configuration is
  absent.

**Non-Goals:**

- No HA, OwnTracks, location, Telegram user-client, group/channel, callback,
  attachment, caption, service event, or generic context event can release a
  cohort.
- No briefing, combined briefing, insight catch-up, schedule/cron change,
  secret-lifecycle release, retention change, user-visible acknowledgement, or
  normal notification behavior is added.
- No generic `user_context` clear is introduced. A wake event does not make an
  owner "awake" for any purpose other than this fenced protocol.
- No provider-exactly-once claim is made. Telegram cannot safely prove that a
  timed-out `sendMessage` did not take effect.

## Decisions

### D1 — A qualifying wake is an accepted-event proof, not a raw Telegram update

The coordinator runs only after the normal Switchboard ingestion transaction
has committed both the inbox and `public.ingestion_events` records. It creates
one immutable `WakeAcceptedEvent` snapshot with:

- `ingestion_event_id` / `request_id`, dedupe key, external Telegram update ID,
  and committed acceptance timestamp;
- canonical owner entity ID and the primary Telegram-bot identity that matched
  at acceptance, resolved through the existing owner-only definer path;
- exact source tuple `(telegram_bot, telegram, bot endpoint identity, sender
  chat ID, direct-thread identity)`;
- proof that the incoming Telegram message is a private/direct native-text
  message, plus a normalized-text SHA-256 digest; and
- the owner-policy timezone and the computed local release-floor decision.

The snapshot stores no message body and is immutable after commit. A unique
constraint on `ingestion_event_id` makes an accepted duplicate return the same
candidate/run rather than opening a second release. A different event is still
rejected unless all of the following are true at acceptance:

1. source channel/provider are exactly `telegram_bot`/`telegram`;
2. the event is a direct/private chat from the canonical owner primary Telegram
   bot channel, not a group, channel, forum/topic, forwarded/service/edit, or
   callback; and
3. the source is a non-empty native text message with no attachment/caption
   substitution.

The owner-local earliest release floor is an explicit,
timezone-bound Owner Attention Policy value. It has no guessed default: absent,
invalid, or not-yet-reached means `not_eligible_before_floor`, no release run,
and no delayed timer. The owner may send a later qualifying direct DM after the
floor. This keeps the packet strict while the decision records a floor without
inventing an hour.

**Alternative considered:** trigger from the connector immediately after
receiving an update. Rejected because connector retries, dedupe, identity
changes, and failed persistence would make raw receipt a non-durable authority.

### D2 — Owner/window claims and runs are the durable coordination boundary

Switchboard owns a durable `WakeRecoveryRun` with an active
`(owner_entity_id, policy_window_key)` claim. The window key is a canonical
policy-timezone interval, not a wall-clock label; it cannot collide across DST
changes. A run includes `run_id`, monotonic owner/window `fence`, accepted-event
reference, participant-set digest, release target, lifecycle state, and only
bounded hashes / counts outside origin schemas. A release-action key is assigned
only once a non-empty compatible composition manifest is final, then remains
immutable for that run/fence.
Only one run may hold the active owner/window claim at a time; terminal run
history remains immutable for audit and reconciliation.

The accepted-event uniqueness rule always returns the same run for an exact
event replay. A later qualifying event while a run is active records no second
action. A later accepted direct DM may open a successor with a higher
owner/window fence only after a `blocked_dnd` run has been explicitly aborted
to its durable DND outcome, DND is no longer active, and the old fence has
released its reservations into a retained, scheduler-ineligible state. The
successor must atomically adopt the complete retained cohort; it cannot expose
those rows as ordinary scheduler work. This preserves the requirement for
fresh owner intent after DND. A stale worker whose fence no longer matches
cannot prepare, commit, abort, or release.

`retained_unavailable` and `retained_oversize` are different from DND: they
retain the same run's uncommitted reservations for a same-fence recovery retry.
That retry reuses every persisted cutoff and prepared response and can only ask
an unresolved participant to prepare; it cannot add a late row or create a
second release action. A target mismatch is likewise retained, but its fixed
target may not be recomputed or default-resolved on retry. An explicit retained
abort records a reason-tagged durable retained/abandoned outcome; it never
returns any cohort row to ordinary scheduler work or permits a silent partial
send.

The participant set is snapshotted from the explicit registry of butlers that
can own v1 quiet-hours holds. An unavailable registered participant is a
failure, never a reason to omit that origin. This is what makes
all-or-nothing meaningful without granting Switchboard SQL access to origin
queues. A compatible all-zero participant response is a durable `empty` run;
it performs no Health mutation and creates no Messenger egress intent.

**Alternative considered:** let Switchboard scan every schema and build a
best-effort list. Rejected because it violates schema isolation, makes a down
origin invisible, and permits a partial release.

### D3 — Cohorts are frozen by origin-local prepare transactions, not inferred later

Only a post-protocol hold with immutable admission provenance is eligible. Its
record contains a hold kind of `owner_attention_quiet_hours`, policy-window
key, admission sequence, fully resolved Telegram target tuple, resolved
envelope hash, and the original stored `deliver_at`. Existing rows that lack
this provenance are never guessed into a wake cohort; their current scheduler
behavior remains intact.

For every participant, `wake_recovery.prepare.v1` atomically obtains its local
release lock, verifies the run fence, selects its eligible rows in deterministic
admission order, records the local cutoff sequence, and moves them from
`pending` to `release_prepared`. A row committed after that local cutoff is
late: it remains pending for a future accepted wake and cannot be appended to
the current run. A row already prepared or committed for another fence is not
eligible. The ordinary scheduler reads only `pending` rows, so it cannot race a
prepared cohort into an independent send.

The cohort boundary is intentionally the successful origin-local prepare
linearization point. That is the only strict boundary possible without a
cross-schema queue transaction; the accepted event authorizes the run, while
each origin atomically defines the pre-existing rows it owns.

**Alternative considered:** infer a pre-wake cohort from timestamps or
attention-ledger rows. Rejected because transaction-start timestamps, missing
legacy provenance, and ledger best-effort writes cannot prove durable queue
membership.

### D4 — Prepare, commit, abort, and release are authenticated MCP operations

Switchboard invokes every cross-origin operation through its existing trusted
MCP path. No daemon receives another butler's pool, DSN, or direct table grant.
Every request carries `schema_version`, `run_id`, `fence`, owner/window keys,
accepted-event reference, participant digest, and a request/action correlation
ID. Receivers persist enough local state to return the same response when a
call is repeated with the same fence and reject lower or conflicting fences.

| Phase | Caller and receiver | Durable receiver effect | Failure rule |
|---|---|---|---|
| `prepare.v1` | Switchboard → Health, each origin, Messenger | Health validates but does not clear its policy-sleep; origins freeze rows; Messenger validates target/action-key admission without egress | Any refusal, mismatch, unavailable participant, or oversize result prevents commit and retains every prepared row. |
| `commit.v1` | Switchboard → Health, each origin, Messenger | Health supersedes only its matching policy-sleep record; origins mark the same frozen rows `release_committed`; Messenger persists one unsent egress intent | CAS/fence mismatch resumes or blocks the same run; it never starts a partial fallback send. |
| `abort.v1` | Switchboard → every current-fence participant with protocol state | Persists a reason-specific replay-safe outcome. A zero-cohort pre-durable-prepare cancellation records `aborted_preprepare` at every participant so late prepare cannot reserve a row. Once any durable prepare result exists, this parent packet defines no ordinary cancellation route back to `pending`; DND and retained outcomes remain protocol-bound. `bu-qs702` owns any future durable post-prepare cancellation contract. | It never silently converts a blocked, retained, committed, delivered, or ambiguous cohort into ordinary scheduler work. |
| `release.v1` | Switchboard → Messenger | Messenger performs/reconciles the one egress intent | The same action key is replayed; an ambiguous provider result is not blindly resent. |

The coordinator builds the message only after every `prepare.v1` response is
available. It sorts entries by `(origin_butler, admission_sequence,
notification_id)`, labels their origin deterministically, applies the fixed
v1 byte/item limits before commit, and uses the exact target from the accepted
event. Every selected row must have the same fully resolved target tuple;
`recipient=None`, a default-owner re-resolution, a different bot endpoint,
or a different chat/thread is a `target_mismatch` and retains the whole cohort.
The composed `notify.v1` has an explicit Telegram recipient and no fresh target
resolution.

**Alternative considered:** have each origin send its own prepared rows.
Rejected because it creates partial output, loses single-composition semantics,
and makes egress idempotency impossible to reason about as one action.

### D5 — Health policy-sleep and explicit DND have different safety boundaries

The wake protocol may supersede only a currently active `sleeping` context
written by Health whose durable metadata identifies the deterministic Owner
Attention Policy sleep producer and the same policy window. Health remains the
only writer/clearer for that signal and validates the Switchboard caller plus
run fence. A different Health sleep source, any other butler's sleep signal,
and every non-sleep context remain untouched.

Explicit `dnd` is an absolute safety veto, and a direct owner DM never clears
it. When Health observes DND as active while evaluating its matching
policy-sleep operation, it blocks the run without superseding policy sleep or
permitting the coordinator to proceed to egress; the full cohort remains
retained for a fresh accepted wake after DND clears. A DND state change after
an irreversible send-start marker cannot retract that external call, and the
existing action-key rules prohibit a speculative resend.

This parent packet deliberately does not add Messenger DND validation, define
canonical DND versioning/invalidation, or claim a final cross-writer DND race
guarantee. `bu-12iab` owns that prerequisite contract without this packet
prescribing its storage, MCP fields, or replay rules. It also deliberately
defines no scheduler-visible post-prepare cancellation route: a frozen cohort
cannot return a member to `pending`, a generic scheduler scan, or a partial-send
path merely because an ordinary cancellation is requested. `bu-qs702` owns that durable
Scheduler/Messenger cancellation-admission contract without this packet
prescribing its state transitions.

**Alternative considered:** clear all context on a direct owner message.
Rejected because a Telegram interaction is not authority to cancel DND,
actual-sleep, meeting, or any other user context.

### D6 — One action key governs every retry, but ambiguous Telegram sends fail closed

Switchboard generates `release_action_key` once from the immutable run ID,
fence, accepted event ID, exact target tuple, and canonical composition-manifest
digest. It never regenerates the key for retry. The key is carried in the
run, origin commit receipts, composed `notify.v1` release metadata, Messenger
delivery request, attempt/receipt rows, attention/audit references, and any
provider reconciliation record.

Messenger persists the action before an external call. A restart before its
durable `send_started_at` marker may safely reissue the same action. A confirmed
Telegram response stores the provider message ID and makes all repeats return
that terminal result. A crash or timeout after `send_started_at` without a
receipt becomes `egress_ambiguous`: it records the action key and evidence,
does not automatically resend, and requires explicit evidence-based
reconciliation. This is stable end-to-end idempotency plus at-most-one
unconfirmed provider attempt; it deliberately favors avoiding duplicate owner
messages over speculative liveness.

**Alternative considered:** retry every timeout with the same internal key.
Rejected because Telegram does not offer a general send idempotency API and the
first request may already have reached the chat.

### D7: Abort is a reason-specific durable recovery transition

`abort.v1` is not generic reservation cleanup. It records the deciding reason,
the current run/fence, the participant digest, and the before/after local row
states atomically before releasing any reservation. There is no abort path from
an unfenced `candidate`: cancellation before the owner/window CAS is a rejected
candidate with no run, cohort, row, or scheduler mutation.

An explicit `ordinary_preprepare_cancel` is a distinct zero-cohort path. It is
valid only from `claimed` or `preparing` at the current fence, before any
participant has durably returned a prepare result, frozen a cutoff, or moved a
row to `release_prepared`, and before DND or a retained reason has won. It
records terminal `aborted_preprepare` with the current run/fence and an empty
cohort audit. It changes no row state or scheduler eligibility; a late
`prepare.v1` request at that fence must return the terminal abort rather than
reserve a row.

Once any participant preparation has durably linearized, this parent packet has
no ordinary cancellation transition. The full cohort remains fenced,
protocol-bound, and scheduler-ineligible; no abort can return an individual row
to `pending`, start a generic scheduler scan, or authorize a partial send.
`bu-qs702` owns any future durable post-prepare cancellation-admission
contract. Every DND, retained, committed, delivered, or ambiguous outcome
remains replay-safe under its existing reason and fence.

| Abort or recovery reason | Durable run and row outcome | Scheduler / successor rule |
|---|---|---|
| Ordinary pre-durable-prepare cancellation | A current-fence `claimed` or `preparing` run becomes terminal `aborted_preprepare` only with no durable prepare receipt, cutoff, or `release_prepared` row; its cohort audit is empty. | No row becomes `pending` because no row left it, and no scheduler eligibility changes. Same-fence late prepare/replay returns the terminal abort; a later qualifying accepted event may seek a successor fence after the claim is released. |
| Post-prepare ordinary cancellation | This parent packet defines no cancellation transition after a durable prepare result; the full cohort keeps its protocol state and fence. | No row becomes `pending`; a generic scheduler cannot select a member, and no partial send is allowed. The future durable admission contract belongs to `bu-qs702`. |
| `blocked_dnd` | Explicit abort becomes terminal `aborted_dnd`; every uncommitted cohort row becomes reason-tagged `release_retained_dnd`, released from the old reservation but retained with the old run/fence evidence. | Rows remain scheduler-ineligible. Only after DND clears may a **later qualifying accepted direct owner DM** create a higher-fence successor, which atomically adopts the entire retained cohort; no automatic retry or partial adoption is allowed. |
| `retained_unavailable` or `retained_oversize` | The run remains `retained_*` for same-fence recovery, or an explicit abandonment becomes `aborted_retained`; rows remain `release_prepared` during recovery or reason-tagged `release_retained_*` after abandonment. | Neither state is scheduler-eligible. Same-fence replay reuses the persisted cutoff, participant responses, and manifest; it cannot add late rows, mint another action, or start a successor while the retained run is active. |
| `retained_mismatch` | The run remains `retained_mismatch` or becomes reason-tagged `aborted_retained`; rows remain `release_retained_mismatch` with their exact target and cutoff evidence. | Neither state is scheduler-eligible. Replay returns the same mismatch; explicit reconciliation must operate on the whole cohort and may not default-resolve a target or release a partial cohort. |
| Committed but unsent | The run stays `release_ready` and rows stay `release_committed`, bound to one action key. | `abort.v1` cannot return them to `pending`; same-fence replay resumes or reports the committed action only through the protocol. |
| Delivered or ambiguous egress | `egress_delivered` keeps each `release_committed` row's immutable delivery audit; `egress_ambiguous` keeps those committed rows, the action key, and provider-attempt evidence until explicit reconciliation. | Both are scheduler-ineligible. Delivery replay returns the receipt; ambiguity cannot auto-resend, fall back to the scheduler, or be displaced by a later wake event. |

The durable terminal/retained record is therefore the recovery handoff, not a
best-effort status note. Any implementation test that observes a
protocol-bound row as ordinary `pending` after a durable prepare result has
found a fence violation in this parent contract.

## State Machine Matrix

| State | Entry condition | Allowed next states | Invariant |
|---|---|---|---|
| `candidate` | qualifying event snapshot persisted | `not_eligible_before_floor`, `claimed`, `rejected` | No cohort or context mutation exists. |
| `claimed` | owner/window CAS claim succeeds | `preparing`, `blocked_dnd`, `retained_unavailable`, `aborted_preprepare` only before any durable prepare result | One current fence owns the window. |
| `preparing` | all participant prepare calls started | `prepared`, `blocked_dnd`, `retained_unavailable`, `retained_oversize`, `retained_mismatch`, `aborted_preprepare` only before any durable prepare result | Prepared rows are scheduler-ineligible; a partial durable prepare cannot use the zero-cohort abort path. |
| `prepared` | all participants supplied a compatible snapshot | `committing`, `blocked_dnd`, or a retained outcome | Composition manifest and exact target are immutable. This parent packet defines no ordinary post-prepare cancellation transition, and every selected row remains scheduler-ineligible. |
| `empty` | every compatible participant prepared zero eligible rows | terminal | No Health mutation or Messenger egress intent exists. |
| `committing` | component checks permit the fenced commit | `release_ready`, `retained_commit_error`, `blocked_dnd` | No external send has started. Canonical DND race protection is deferred to `bu-12iab`. |
| `release_ready` | all commit receipts persisted | `egress_sending`, `egress_delivered`, `egress_ambiguous` | Every selected row remains `release_committed`, bound to this action key, and scheduler-ineligible. |
| `egress_sending` | Messenger persisted send-start marker | `egress_delivered`, `egress_ambiguous` | No automatic second provider call is allowed. |
| `egress_delivered` | provider receipt is durable | terminal | All committed rows have one delivered/coalesced audit outcome and never become scheduler work. |
| `egress_ambiguous` | post-start result is unknown | terminal until explicit reconciliation | No automatic egress retry or scheduler fallback is allowed. |
| `blocked_dnd` | DND blocks a protocol operation | explicit `aborted_dnd`; only then may a new accepted direct DM after DND clears create a higher-fence successor | Rows remain retained and scheduler-ineligible; no partial send or generic context mutation occurs. |
| `retained_*` | unavailable participant, oversize, target mismatch, or commit failure | same-fence recovery only where its persisted cutoffs/manifest permit, or explicit `aborted_retained` | Rows remain protocol-bound and scheduler-ineligible; no partial send; late rows never join the retained cohort. |
| `aborted_preprepare` | explicit current-fence cancellation before any durable prepare result or row reservation | terminal | Empty cohort audit, no row transition, and no scheduler eligibility change; late prepare/replay returns the terminal abort. |
| `aborted_dnd` | explicit abort of a DND-blocked run | terminal until a fresh qualifying accepted direct DM after DND clear opens a successor | Retained rows are never ordinary `pending`; a successor adopts the complete cohort under a higher fence. |
| `aborted_retained` | explicit abandonment of a retained unavailable, oversize, mismatch, or commit-error run | terminal until explicit compatible recovery | Reason-tagged retained rows never become ordinary `pending`; recovery cannot omit participants or recompute a mismatched target. |
| `rejected` / `not_eligible_before_floor` | wake authority or floor check fails | terminal | No prepared row, Health mutation, or egress intent exists. |

## Threat Matrix

| Threat | Protocol control | Durable evidence / expected result |
|---|---|---|
| Forged or non-owner Telegram update | Post-commit canonical-owner, primary-channel, direct-text validation | Rejected candidate reason; no run. |
| Connector replay or duplicate delivery | Ingestion-event uniqueness and owner/window claim | Existing candidate/run is returned; no second action key. |
| Cross-origin partial release | Snapshotted participant registry plus all prepare receipts | Any unavailable/mismatch/oversize participant retains all rows. |
| Scheduler races a cohort | Origin-local state/fence and scheduler `pending` filter | Prepared/committed rows have no scheduler send attempt. |
| Generic abort loses a safety-bound cohort | Reason-specific durable abort records plus scheduler exclusion | Only zero-cohort `aborted_preprepare` is defined in this parent packet; after a durable prepare result, DND, retained, committed, delivered, and ambiguous rows remain protocol-bound and cannot return to `pending` through an ordinary cancellation. |
| Late held row leaks into composition | Per-origin prepare cutoff sequence | Late row stays pending and is absent from manifest. |
| DND changes during release | Health blocks an observed active DND before the protocol proceeds; existing send-start/idempotency evidence prevents speculative resend | A post-send-start state change cannot retract the external call. Canonical versioning/invalidation and any final egress check are deferred to `bu-12iab`. |
| Ordinary cancellation after prepare | No parent post-prepare scheduler route | The cohort stays fenced and scheduler-ineligible. `bu-qs702` owns the future durable cancellation-admission contract. |
| Generic context is cleared | Health-specific policy-sleep RPC and ownership validation | Non-policy sleep/DND/other contexts are unchanged. |
| Coordinator/participant restart | Persisted run/receiver state plus fence CAS | Same fence resumes idempotently; stale fence is rejected. |
| Telegram timeout after send | Durable send-start marker and no blind retry | `egress_ambiguous`, one action key, manual reconciliation path. |
| Content/target mix-up | Exact accepted target + per-row resolved target equality | `retained_mismatch`; no content is sent to a recomputed default target. |
| Privilege expansion | MCP-only data exchange and minimal role grants | No Switchboard SELECT on origin queues; no origin DSN exposure. |

## Verification Matrix

| Contract | Primary proof | Required negative proof |
|---|---|---|
| Wake authority | Switchboard integration test commits an accepted private owner text DM and opens one run | Raw, duplicate, group, user-client, callback, attachment/caption, non-owner, and pre-floor inputs open no run. |
| Provenance and claims | Migrated-DB test asserts immutable accepted-event fields and unique event/window fencing | Stale fence / changed identity cannot mutate an existing run. |
| Cohort preparation | Per-origin integration test freezes deterministic rows and returns one manifest | Legacy, explicit-target, retry, context-only, and post-cutoff rows are excluded. |
| Exact-target composition | Contract test validates one explicit target and deterministic ordering | Mixed bot/chat/thread/default-recipient inputs reject the whole run. |
| DND safety | Component tests prove an observed active DND blocks the relevant operation and a direct DM never clears DND | DND never creates a partial send or generic context clear. Canonical writer races are verified in `bu-12iab`, not by this parent packet. |
| Reason-specific abort fencing | Transition tests prove zero-cohort `claimed`/`preparing` → `aborted_preprepare` and a same-fence late prepare rejection | Any durable prepared row rules out the pre-prepare path and cannot return to `pending` through a parent ordinary cancellation; retained, committed, delivered, and ambiguous cohorts preserve all-or-nothing recovery. `bu-qs702` verifies its future cancellation-admission behavior. |
| Crash recovery | Restart tests at every durable state replay the same fence/action key | Post-send-start timeout cannot invoke a second provider send. |
| Egress idempotency | Messenger DB test observes one delivery request/receipt for repeated release RPCs | Ambiguous send becomes non-retryable until reconciled. |
| ACL and topology | Migrated role test plus MCP caller-auth test | Switchboard cannot SQL-read origin queues; origins/Messenger cannot invoke privileged peers directly. |
| Documentation boundary | `openspec validate --strict` and change diff review | No source, migration, roster schedule, connector, or runtime artifact changes in this planning PR. |

## Risks / Trade-offs

- **A run can retain messages longer than the ordinary scheduler path** → This
  is intentional once a fenced all-or-nothing run starts; retries are durable
  and visible rather than silently falling back to partial sends.
- **An owner receives no automatic retry after an ambiguous send** → The
  protocol favors duplicate prevention; the action key and attempt evidence
  make explicit reconciliation possible.
- **The current queue lacks required provenance/state fields** → Legacy rows
  remain on their existing behavior; the implementation migration gates wake
  eligibility to new, explicitly marked holds.
- **A required participant can be temporarily unavailable** → The registry
  makes this visible and blocks the whole cohort rather than omitting it.
- **An unset release floor disables wake release** → This is fail-closed and
  avoids inventing a personal wake time; it is surfaced in run audit status.

## Migration Plan

This OpenSpec-only packet performs no migration. Its implementation is bounded
into the following future delivery order:

1. Add versioned hold provenance/state and ordinary-scheduler exclusion with
   migration/legacy preservation tests; no wake trigger yet.
2. Add Switchboard accepted-event/run records, owner/window fencing, and
   authenticated prepare/abort contracts with negative ingress tests.
3. Land `bu-12iab`'s canonical DND versioning/invalidation contract before an
   implementation relies on a final cross-writer DND race guarantee.
4. Land `bu-qs702`'s durable post-prepare Scheduler/Messenger cancellation
   admission contract before any cancellation route can return a frozen cohort
   to ordinary work.
5. Add the Health policy-sleep prepare/commit contract and Messenger action-key
   persistence, receipt reconciliation, and ambiguous-send handling; prove no
   duplicate provider attempt.
6. Wire the coordinator only after every component contract and cross-role ACL
   test passes; then perform an owner-authorized staging drill before any live
   rollout.

Rollback keeps all durable holds and runs. A newer binary may resume an
uncommitted run with the same fence. A downgrade must not reinterpret
`release_prepared`, `release_retained_*`,
`release_committed`, `aborted_preprepare`, `aborted_dnd`, `aborted_retained`,
or `egress_ambiguous` as ordinary `pending` work; an explicit recovery
procedure either resumes the new protocol or retains the cohort until a
compatible binary returns.

## Open Questions

None for the v1 protocol. The implementation must expose the owner-selected
floor as an explicit policy value and fail closed until it is configured; this
is a configuration value, not an additional release trigger or schedule.
