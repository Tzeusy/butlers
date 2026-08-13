## ADDED Requirements

### Requirement: Recovery delivery idempotency envelope
The `notify.v1` contract SHALL carry a non-secret immutable delivery idempotency key for an approval-recovery request, and Switchboard SHALL validate and forward that key unchanged to the Messenger delivery boundary without placing it in the generic deferred-notification queue.

ID: REQ-core-notify-028
Source: RFC-0023
Scope: v1-mandatory

#### Scenario: Approval worker dispatches a stable key
- **WHEN** an approval-delivery worker renders a due `single` or `burst_digest` intent
- **THEN** its `notify.v1` delivery contains the intent's immutable action key
- **AND** retries, restarts, and reconciliation requests retain exactly that key rather than minting another one

#### Scenario: Ordinary notify behavior remains compatible
- **WHEN** an ordinary non-recovery `notify.v1` caller omits the recovery idempotency key
- **THEN** existing validation and delivery behavior remain unchanged
- **AND** that notification is not silently promoted into approval-recovery tracking

### Requirement: Safe provider-handoff classification
The notify delivery boundary SHALL return a normalized `confirmed`, `safe_retry`, or `ambiguous` handoff classification with only safe reason/reference fields for a recovery-keyed approval request, and SHALL not collapse an unknown post-start provider outcome into a generic retryable failure.

ID: REQ-core-notify-029
Source: RFC-0023
Scope: v1-mandatory

#### Scenario: Source receives confirmed handoff truth
- **WHEN** Messenger confirms provider acceptance or a duplicate-safe reconciliation for an approval action key
- **THEN** Switchboard and the source receive `confirmed` for that same key
- **AND** the result does not assert that the owner read or decided the action

#### Scenario: Timeout after possible provider start is ambiguous
- **WHEN** the boundary loses a result after Messenger may have started a provider call and cannot prove duplicate safety
- **THEN** it returns `ambiguous` with a closed safe reason code
- **AND** the source worker cannot treat that response as `safe_retry` or issue a fresh key

### Requirement: Approval-recovery isolation from generic defer
The notify subsystem SHALL keep approval-delivery intents outside `deferred_notifications`, generic quiet-hours flush coalescing, and generic wake-recovery cohorts while preserving their stored RFC 0021 admission time at the approval boundary.

ID: REQ-core-notify-030
Source: RFC-0021,RFC-0023
Scope: v1-mandatory

#### Scenario: Quiet-hours approval recovery is local to its intent
- **WHEN** an approval action parks during RFC 0021 quiet hours
- **THEN** its approval intent stores and later honors the exact admission release time
- **AND** no generic deferred-notification row, flush claim, or wake cohort is created for that action
