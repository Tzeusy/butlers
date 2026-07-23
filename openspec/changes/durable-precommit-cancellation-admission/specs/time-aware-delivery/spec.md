## ADDED Requirements

### Requirement: Fenced Cancellation Return Is All-Cohort and Guarded
The ordinary deferred-notification Scheduler SHALL keep all
`release_prepared` and cancellation-ready wake-recovery rows scheduler-ineligible.
It SHALL allow a future cancellation-return state only after receiving a
matching `wake_recovery.cancel_publish.v1` receipt whose run, fence,
participant/cohort digests, release action, cancellation action key, accepted
Messenger decision, and complete finalization digest exactly match the row's
durable provenance.

The Scheduler SHALL reject partial, stale, changed-digest, DND-blocked,
egress-present, or ambiguous cancellation outcomes. It SHALL not append late
rows, recalculate a target, re-gate the parent wake release, or use the legacy
unguarded flush path for a cancelled cohort. Future effective egress SHALL
preserve the receipt's DND evidence and complete its own Messenger admission.

#### Scenario: Cancellation-ready row remains invisible to ordinary flush
- **WHEN** an origin has recorded the accepted cancellation receipt but has not
  received a complete finalization digest and publish authorization
- **THEN** its rows remain scheduler-ineligible
- **AND** the ordinary deferred-notification flush neither selects nor sends them

#### Scenario: Changed publish evidence cannot expose a subset
- **WHEN** a publish request carries a different fence, cohort digest, release
  action, cancellation action key, or incomplete finalization digest
- **THEN** the Scheduler rejects it without changing row eligibility
- **AND** no individual row becomes ordinary pending work
