## ADDED Requirements

### Requirement: Versioned Precommit Cancellation Request
The system SHALL expose `wake_recovery.cancel_admit.v1` only as an
authenticated Switchboard-to-Messenger MCP operation for a complete,
already-prepared wake-recovery cohort. The request SHALL contain immutable
`run_id`, `fence`, `participant_digest`, `cohort_digest`, and
`release_action_key`; a stable `cancellation_action_key` and
`cancellation_request_id`; a versioned request fingerprint; an opaque
authorized decision source/reference and reason; and canonical inactive-DND
snapshot evidence consisting of `expected_dnd_generation`, `dnd_observed_at`,
and `dnd_revalidate_at`.

The coordinator SHALL bind every field to its persisted current-fence run
before forwarding it. It SHALL reject a request whose run/fence/digests/action
do not exactly match the frozen cohort and SHALL NOT create a new cancellation
action key on retry. Health and origin Schedulers SHALL provide only their own
local decision evidence to Switchboard; they SHALL NOT call Messenger directly.

#### Scenario: Complete current-fence request reaches Messenger
- **WHEN** an authorized local decision matches the coordinator's persisted
  prepared run, participant set, cohort digest, and release action
- **THEN** Switchboard invokes Messenger with one matching
  `wake_recovery.cancel_admit.v1` packet
- **AND** the packet contains no notification content, raw DND payload, or
  peer-schema record

#### Scenario: Partial or changed request is rejected before admission
- **WHEN** a request omits a frozen participant or changes its run, fence,
  participant/cohort digest, release action, or cancellation action key
- **THEN** the coordinator rejects it without invoking a changed cancellation
  admission
- **AND** no participant row becomes scheduler-visible

### Requirement: Durable Messenger Cancellation Decision
Messenger SHALL persist one private cancellation-admission record keyed by
`cancellation_action_key` before it returns any result. The record SHALL retain
the schema version, semantic request fingerprint, immutable run/fence/digests/
release-action binding, opaque correlation and decision evidence, captured and
observed DND generations, decision state/code, release-gate state, and database
decision timestamp. It SHALL NOT retain notification content, raw DND
value/metadata, canonical DND mutation fingerprints, or copied provider payload.

An exact replay SHALL return the original durable receipt without changing the
record or release gate. Reusing an action key or request ID with a different
semantic request SHALL fail closed as `idempotency_conflict`. A distinct
cancellation action for the same `(run_id, fence, release_action_key)` SHALL
fail closed as `conflicting_cancellation_action`.

#### Scenario: Exact cancellation replay returns the original receipt
- **WHEN** Messenger receives a retry with the same cancellation action key
  and identical request fingerprint after a terminal decision
- **THEN** it returns the original receipt and decision state
- **AND** it does not create a second cancellation record, egress intent, or
  provider attempt

#### Scenario: Conflicting replay changes no durable state
- **WHEN** a caller reuses a cancellation action key or request ID with a
  changed fence, digest, release action, decision reference, reason, or DND
  evidence
- **THEN** Messenger returns `idempotency_conflict`
- **AND** it leaves the existing cancellation record and release gate unchanged

### Requirement: Guarded No-Egress Precommit Admission
Messenger SHALL decide a new cancellation inside one local transaction. It
SHALL authenticate the Switchboard caller, lock the matching private
prepared-release gate with `FOR UPDATE`, and use the canonical RFC 0009 DND
admission helper on the same connection. The helper SHALL lock the public guard
with `FOR SHARE`, require the captured generation to match, and require a
database-time inactive DND state while Messenger writes its local decision.

Messenger SHALL accept cancellation only when the immutable prepared binding is
valid and it proves that no wake-recovery egress intent, `send_started_at`
marker, provider receipt, provider-attempt ambiguity, or incompatible terminal
release state exists. An accepted decision SHALL durably prevent every later
same-fence commit/release from creating an egress intent. The operation SHALL
not hold either lock across MCP, origin-finalization, provider I/O, or retry
delay.

#### Scenario: Cancellation wins the prepared-release gate
- **WHEN** a matching cancellation acquires the private prepared-release gate
  before a same-fence commit/release operation and DND evidence is current and
  inactive
- **THEN** Messenger persists `accepted_precommit` before returning its receipt
- **AND** the later commit/release rejects before creating an egress intent or
  send-start marker

#### Scenario: Commit wins the prepared-release gate
- **WHEN** a same-fence commit operation has already persisted an egress intent
  before cancellation locks the gate
- **THEN** Messenger persists `rejected_egress_present`
- **AND** cancellation does not remove the intent, publish scheduler work, or
  invoke a provider action

### Requirement: DND Mismatch and Uncertainty Fail Closed
Messenger SHALL record `rejected_blocked_dnd` when the expected DND generation
has changed, current DND is active, or the required guard/database-time/snapshot
evidence is stale, missing, or unprovable. That result SHALL keep the entire
cohort retained as `blocked_dnd`; no member may become `pending` or enter an
egress path from that cancellation request.

Messenger SHALL record `ambiguous` when it cannot prove a coherent local
release/attempt state or recover a prior decision after timeout or restart. A
timeout without a durable receipt SHALL never be treated as accepted. A
send-start marker, provider receipt, or ambiguous provider attempt SHALL never
be rewritten into cancellation success and SHALL prohibit automatic resend.

#### Scenario: DND generation changes before effective admission
- **WHEN** a local decision carries inactive generation `N` and a canonical
  DND writer commits generation `N + 1` before Messenger obtains the guard
- **THEN** Messenger records `rejected_blocked_dnd` before any egress intent
- **AND** the complete cohort remains retained and scheduler-ineligible

#### Scenario: Lost response is recovered by exact replay
- **WHEN** Messenger commits a cancellation decision but its MCP response is
  lost or the process restarts
- **THEN** Switchboard retries the same action key and receives the durable
  receipt
- **AND** neither side infers acceptance from the timeout or creates a new
  cancellation action

### Requirement: All-Cohort Scheduler Return Requires Complete Finalization
An `accepted_precommit` Messenger receipt SHALL begin, not complete, a
same-fence all-cohort cancellation finalization. Each origin SHALL verify the
complete matching local prepared subset and move it atomically to a
scheduler-ineligible cancellation-ready state. Switchboard SHALL collect a
compatible finalization receipt from every snapshotted participant and derive a
durable finalization digest before it sends replay-safe
`wake_recovery.cancel_publish.v1` packets.

Only a publish packet carrying the accepted decision and complete finalization
digest may move an origin's matching cancellation-ready rows to the
prerequisite-defined scheduler return state. A partial, stale, different-fence,
or changed-digest packet SHALL be rejected. An origin Scheduler and final
Messenger egress admission SHALL preserve the published run/fence/DND evidence;
the parent wake release and legacy unguarded flush SHALL NOT consume it.

#### Scenario: Missing participant prevents scheduler publication
- **WHEN** Messenger has accepted cancellation but one current-fence participant
  has not produced a compatible finalization receipt
- **THEN** every unfinalized participant remains prepared or cancellation-ready
  and scheduler-ineligible
- **AND** replay retries only the same cancellation action and participant set

#### Scenario: Complete finalization publishes only the matching cohort
- **WHEN** Switchboard has persisted compatible finalization receipts for every
  snapshotted participant under one run, fence, action, and cohort digest
- **THEN** each matching origin accepts the same finalization digest and moves
  all of its cancellation-ready rows through the defined scheduler-return path
- **AND** no individual row, late row, or subset can be published independently
