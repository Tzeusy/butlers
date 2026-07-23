## ADDED Requirements

### Requirement: Fenced Wake-Recovery Cohorts Are Scheduler-Ineligible
The ordinary deferred-notification scheduler SHALL select only rows whose
status is `pending`. A row reserved by a valid wake-recovery prepare fence or
committed to a valid wake-recovery run SHALL be scheduler-ineligible until the
run's durable recovery path resolves it. The scheduler SHALL NOT re-evaluate
Owner Attention Policy, recalculate `deliver_at`, re-resolve a target, or append
a late row when it encounters a wake-recovery-related record.

An uncommitted abort MAY return only its same-fence reservation to `pending`.
A committed, delivered, blocked, or ambiguous cohort SHALL be recovered under
the wake-recovery protocol rather than silently converted to ordinary scheduler
work. Rows admitted after an origin-local prepare cutoff SHALL remain `pending`
and SHALL be eligible only for a later accepted wake or their normal stored
delivery path.

#### Scenario: Scheduler skips a prepared cohort
- **WHEN** a due row has been moved from `pending` to a valid
  `release_prepared` state by an origin-local prepare transaction
- **THEN** the ordinary scheduler does not select or send it
- **AND** it does not re-gate the stored envelope or recalculate its delivery
  decision

#### Scenario: Late row does not join a frozen run
- **WHEN** a matching quiet-hours hold is admitted after an origin has recorded
  its prepare cutoff for a wake run
- **THEN** the row remains `pending` and outside that run's manifest
- **AND** the scheduler does not change the stored row merely because the wake
  run is in progress

#### Scenario: Committed ambiguity never falls back to ordinary flush
- **WHEN** a committed wake cohort reaches `egress_ambiguous`
- **THEN** its rows remain bound to the wake-recovery action and recovery audit
- **AND** the ordinary scheduler cannot send them as an independent fallback
