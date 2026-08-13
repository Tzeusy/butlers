## ADDED Requirements

### Requirement: Truthful approval-delivery recovery projection
The approvals API and dashboard SHALL project a pending action's durable delivery state, mode, safe reason, attempt count, next eligible time, and derived stuck/ambiguous status without exposing recipient identity, callback material, action key, raw provider response, raw error, or a false claim that uncertain delivery was never attempted.

ID: REQ-dashboard-approvals-001
Source: RFC-0023
Scope: v1-mandatory

#### Scenario: Retry and quiet-hours state render honestly
- **WHEN** a pending action has a `ready`, `retry_wait`, or quiet-hours-delayed delivery intent
- **THEN** list and detail responses identify its delivery state and safe timing/reason truth
- **AND** the dashboard distinguishes waiting/retrying from confirmed notification delivery

#### Scenario: Ambiguous state is visible without unsafe detail
- **WHEN** an approval delivery intent is `ambiguous` or derived stuck
- **THEN** the action detail visibly marks notification recovery as uncertain or needing attention
- **AND** neither the API nor UI includes the provider error text, recipient, callback token, secret, or provider payload

#### Scenario: Legacy emission data remains explicitly legacy
- **WHEN** an action predates new intent admission and only has an `approval_push_emissions` outcome
- **THEN** the API identifies that outcome as legacy evidence rather than authoritative recovery state
- **AND** the UI does not claim “never attempted” solely because that legacy outcome is null or failed

### Requirement: Safe delivery-recovery observability
The approvals service SHALL expose aggregate delivery-recovery counts, oldest-due age, expired-lease count, ambiguous count, and safe state/reason dimensions for operator observability without adding a dashboard action that approves, executes, replays, or mutates a parked domain action.

ID: REQ-dashboard-approvals-002
Source: RFC-0023
Scope: v1-mandatory

#### Scenario: Stuck backlog is measurable without sensitive labels
- **WHEN** a schema contains overdue retry work, expired claims, or ambiguous intents
- **THEN** its metrics/read-model aggregation reports the safe count and age dimensions needed to detect the condition
- **AND** labels and responses exclude tool arguments, message content, recipient, callback material, and raw transport data

#### Scenario: Observability does not create a domain-action bypass
- **WHEN** an operator views delivery-recovery detail or a stuck-intent aggregate
- **THEN** the surface provides no control that approves, rejects, expires, executes, or replays the parked domain action
- **AND** normal authenticated approval decision endpoints remain the only domain-action path
