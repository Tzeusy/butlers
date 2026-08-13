## ADDED Requirements

### Requirement: Atomic pending-action delivery admission
The system SHALL commit every new pending approval action and exactly one schema-local durable delivery intent in the same PostgreSQL transaction, with a unique foreign-keyed `action_id` and immutable end-to-end action key; a failed admission SHALL commit neither record.

ID: REQ-approval-delivery-intent-recovery-001
Source: RFC-0023
Scope: v1-mandatory

#### Scenario: Transaction failure rolls back action and intent
- **WHEN** an insertion or validation failure occurs after a pending action is staged but before its delivery intent commits
- **THEN** the owning schema contains neither the new pending action nor an intent/attempt row for its action key
- **AND** a successful duplicate semantic-key admission returns the pre-existing action/intent pair without a second key

#### Scenario: Runtime availability does not remove the intent
- **WHEN** a valid producer parks an action while its notification worker or Switchboard client is unavailable
- **THEN** the action and its delivery intent still commit atomically in a sendable or policy-terminal state
- **AND** no caller may omit the intent by passing a null live runtime

### Requirement: Closed intent state, reason, and ownership boundary
The system SHALL persist approval-delivery state only as `ready`, `claimed`, `handoff_started`, `retry_wait`, `delivered`, `collapsed`, `cancelled`, or `ambiguous`, and SHALL persist only an allowlisted safe reason code without recipient, callback material, raw provider payload, raw exception, rendered message, or domain-action mutation authority.

ID: REQ-approval-delivery-intent-recovery-002
Source: RFC-0023
Scope: v1-mandatory

#### Scenario: Unknown state or reason is rejected
- **WHEN** a writer attempts to create or transition an intent with a state or reason outside the closed vocabulary
- **THEN** schema and repository validation reject the write
- **AND** API, metric, and log projections expose only the safe normalized value

#### Scenario: Worker has notification-only authority
- **WHEN** the approval-delivery worker processes an associated pending action
- **THEN** it may read that action and write only its local intent, attempt, and safe audit-observability records
- **AND** it has no path to approve, reject, expire, defer, execute, edit, or otherwise mutate `pending_actions`

### Requirement: Fenced claim and at-least-once recovery
The system SHALL claim due sendable intents with a monotonic fence, opaque claim token, finite lease, and compare-and-set writes, and SHALL retry only safely unstarted or provider-idempotent work with bounded backoff until the action becomes terminal or the outcome is ambiguous.

ID: REQ-approval-delivery-intent-recovery-003
Source: RFC-0023
Scope: v1-mandatory

#### Scenario: A stale worker cannot write after lease succession
- **WHEN** one worker's lease expires and a second worker obtains a higher fence for the same intent
- **THEN** every renewal or transition from the stale token/fence is rejected
- **AND** only the successor may make a new pre-handoff transition

#### Scenario: Restart recovers an unstarted claim
- **WHEN** a process crashes after claiming an intent but before recording provider handoff start
- **THEN** a later worker reclaims the expired claim and retries the same immutable action key after its scheduled backoff
- **AND** no duplicate action or intent is created

### Requirement: Idempotent and ambiguous provider handoff
The system SHALL persist a fenced pre-provider handoff marker and require the actual Messenger boundary to classify the immutable action key as `confirmed`, `safe_retry`, or `ambiguous`; it SHALL never blindly resend an uncertain post-start handoff.

ID: REQ-approval-delivery-intent-recovery-004
Source: RFC-0023
Scope: v1-mandatory

#### Scenario: Confirmed same-key replay is idempotent
- **WHEN** the source worker repeats a delivery request whose Messenger handoff ledger has a confirmed receipt for the same action key
- **THEN** Messenger returns a confirmed duplicate-safe result and the intent is or remains `delivered`
- **AND** the provider adapter is not invoked a second time

#### Scenario: Post-start timeout is quarantined without proof
- **WHEN** a provider call may have started but the source or Messenger loses the outcome and the adapter cannot reconcile the action key
- **THEN** the intent becomes `ambiguous` with a safe reason code
- **AND** restart, lease recovery, and retry scans do not issue another provider send for that key

### Requirement: Decision and expiry cancellation fencing
The system SHALL couple every transition out of `pending` to cancellation of its delivery intent in the same local transaction, using a fixed action-then-intent lock order and treating the committed handoff-start marker as the final cancellation-safe boundary.

ID: REQ-approval-delivery-intent-recovery-005
Source: RFC-0023
Scope: v1-mandatory

#### Scenario: Decision wins before send start
- **WHEN** an authenticated approval/rejection or canonical expiry transaction commits before a worker's handoff-start transaction
- **THEN** the terminal action transition and intent cancellation commit together
- **AND** the worker cannot start a provider call or revive the cancelled intent

#### Scenario: Send start wins the unavoidable race
- **WHEN** a worker commits its fenced handoff-start marker before a later decision or expiry transaction
- **THEN** the later domain transition cancels future recovery without changing the already-started action attempt
- **AND** a late provider result is append-only evidence and never changes the action or makes the intent sendable again

### Requirement: RFC 0021 policy preservation
The system SHALL preserve RFC 0021 one-key-per-action, exact quiet-hours admission, no re-gate behavior, control-plane budget exemption, and first-three/single-digest/later-collapse burst semantics without using the generic deferred-notification queue.

ID: REQ-approval-delivery-intent-recovery-006
Source: RFC-0021
Scope: v1-mandatory

#### Scenario: Quiet-hours intent releases at its admitted time
- **WHEN** an action parks within an end-exclusive RFC 0021 quiet-hours interval
- **THEN** its sendable intent stores the exact configured interval end as `not_before`
- **AND** a later policy change does not re-gate or recalculate that already-admitted intent

#### Scenario: Burst policy creates durable collapsed evidence
- **WHEN** more than three actions park concurrently within one schema's ten-minute burst window
- **THEN** the first three have `single` intents, exactly one later action has a `burst_digest` intent, and remaining actions have terminal `collapsed` intents
- **AND** all pending actions retain one unique action key and none are written to `deferred_notifications`

### Requirement: Retention and stuck-intent observability
The system SHALL retain nonterminal and ambiguous intents while their action remains pending, append safe attempt and terminal-summary evidence, and expose derived stuck/ambiguous backlog truth without deleting, replaying, or mutating historical parked actions.

ID: REQ-approval-delivery-intent-recovery-007
Source: RFC-0023
Scope: v1-mandatory

#### Scenario: Retention does not erase unresolved delivery work
- **WHEN** routine approval retention encounters a pending action with a retrying, leased, handoff-started, or ambiguous intent
- **THEN** it retains the intent and attempts rather than deleting or terminalizing them
- **AND** terminal intent cleanup follows the action's existing retention order and preserves the safe immutable approval-event summary

#### Scenario: Operators can see a stuck recovery path safely
- **WHEN** a due retry exceeds the recovery SLO, a lease is expired, or an intent is ambiguous
- **THEN** metrics and the approval read model report state/count/oldest-age and safe reason information
- **AND** they omit action arguments, recipient, callback material, message body, raw provider response, and raw exception text

### Requirement: Complete pending-action producer coverage
The system SHALL route every production `pending_actions(status='pending')` admission through the shared atomic helper and SHALL mechanically reject any new direct pending insert outside that helper while allowing deliberately auto-approved inserts.

ID: REQ-approval-delivery-intent-recovery-008
Source: RFC-0023
Scope: v1-mandatory

#### Scenario: Existing producers share the one admission path
- **WHEN** the gate, recipient guards, core notify guard, calendar overlap, connector disconnect, relationship assertion, and relationship curation producers park an action
- **THEN** each call uses the same atomic pending-action-plus-intent admission path
- **AND** no producer creates a pending action whose action key lacks an intent

#### Scenario: A future direct pending insert is caught
- **WHEN** source code introduces a direct `INSERT` of a `pending_actions` row with status `pending` outside the approved helper
- **THEN** the producer-coverage contract test fails
- **AND** direct inserts whose status is auto-approved remain explicitly excluded from the notification requirement
