## ADDED Requirements

### Requirement: Authenticated recovery presentation envelope
The `notify.v1` contract SHALL carry an immutable recovery subject (a direct
action key or a cohort key) plus a generation-specific presentation key only in
a recovery-only approval-request shape. Switchboard SHALL derive the issuer and
owning schema from the authenticated daemon transport, validate the claimed
subject/schema/mode against that trusted identity and a non-caller-serializable
source-schema subject/presentation attestation, and forward trusted context to
Messenger without placing recovery work in the generic deferred-notification
queue or granting cross-schema reads.

ID: REQ-core-notify-028
Source: RFC-0023
Scope: v1-mandatory

#### Scenario: Approval worker dispatches a stable presentation key
- **WHEN** an approval-delivery worker renders a due `single` action presentation or cohort `burst_digest` presentation
- **THEN** its recovery request contains the stable direct-action or cohort subject key and its immutable current presentation key
- **AND** retries, restarts, and reconciliation requests retain exactly that presentation key rather than minting another one

#### Scenario: Dashboard defer advances only the presentation generation
- **WHEN** authenticated dashboard defer atomically schedules an action's next presentation
- **THEN** its later recovery request retains the same logical action key and carries the next deterministic presentation key
- **AND** no ordinary retry, worker, or generic notification control can advance that generation

#### Scenario: Ordinary notify behavior remains compatible
- **WHEN** an ordinary non-recovery `notify.v1` caller omits recovery fields
- **THEN** existing validation and delivery behavior remain unchanged
- **AND** that notification is not silently promoted into approval-recovery tracking

#### Scenario: Claimed recovery identity is not authority
- **WHEN** a caller supplies an action/cohort subject or presentation key, origin, owning schema, or mode that differs from the transport-authenticated issuer and registered owning schema
- **THEN** Switchboard rejects it before generic delivery logging, recovery-ledger persistence, or a Messenger/provider call
- **AND** an ordinary caller that adds recovery-shaped fields is rejected rather than treated as a recovery worker

### Requirement: Safe provider-handoff classification
The notify delivery boundary SHALL return a normalized `confirmed`, `safe_retry`, or `ambiguous` handoff classification with only safe reason/reference fields for a trusted recovery presentation, and SHALL not collapse an unknown post-start provider outcome into a generic retryable failure.

ID: REQ-core-notify-029
Source: RFC-0023
Scope: v1-mandatory

#### Scenario: Source receives confirmed handoff truth
- **WHEN** Messenger confirms provider acceptance or a duplicate-safe reconciliation for an approval presentation key
- **THEN** Switchboard and the source receive `confirmed` for that same presentation key
- **AND** the result does not assert that the owner read or decided the action

#### Scenario: Timeout after possible provider start is ambiguous
- **WHEN** the boundary loses a result after Messenger may have started a provider call and cannot prove duplicate safety
- **THEN** it returns `ambiguous` with a closed safe reason code
- **AND** the source worker cannot treat that response as `safe_retry` or issue a fresh presentation key

### Requirement: Approval-recovery isolation from generic defer
The notify subsystem SHALL keep approval-delivery presentations outside `deferred_notifications`, generic quiet-hours flush coalescing, and generic wake-recovery cohorts while preserving their stored RFC 0021 admission or authenticated-defer time at the approval boundary.

ID: REQ-core-notify-030
Source: RFC-0021,RFC-0023
Scope: v1-mandatory

#### Scenario: Quiet-hours approval recovery is local to its presentation
- **WHEN** an approval action parks during RFC 0021 quiet hours
- **THEN** its approval presentation stores and later honors the exact admission release time
- **AND** no generic deferred-notification row, flush claim, or wake cohort is created for that action

### Requirement: Recovery isolation from generic notification controls and history
The generic Switchboard notification table, history/list/read models, aggregate counts, acknowledgement, retry, escalation, and stored-envelope reconstruction SHALL exclude recovery-keyed approval presentations. The protected recovery path SHALL expose only the approvals read model's safe projection and SHALL never persist callback material or a full recovery envelope in generic notification metadata.

ID: REQ-core-notify-031
Source: RFC-0023
Scope: v1-mandatory

#### Scenario: Generic retry and escalation cannot bypass the fence
- **WHEN** a generic notification retry, escalation, acknowledgement, or envelope-reconstruction path is given a recovery-keyed row or identifier
- **THEN** it returns an uninformative no-control result before reconstructing an envelope or calling delivery
- **AND** only the fenced approval-delivery worker can reconcile that presentation through the trusted recovery path

#### Scenario: Generic history cannot leak a recovery envelope
- **WHEN** a generic notification list, butler-scoped history, detail/read projection, or stats query encounters recovery delivery evidence
- **THEN** the recovery record is excluded from that generic surface and aggregate
- **AND** no response includes its recipient, message, action/cohort subject or presentation key, callback token, callback secret, raw provider response, or stored recovery envelope
