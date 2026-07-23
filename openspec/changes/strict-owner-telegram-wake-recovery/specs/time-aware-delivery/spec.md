## ADDED Requirements

### Requirement: Fenced Wake-Recovery Cohorts Are Scheduler-Ineligible
The ordinary deferred-notification scheduler SHALL select only rows whose
status is `pending`. A row reserved by a valid wake-recovery prepare fence or
committed to a valid wake-recovery run SHALL be scheduler-ineligible until the
run's durable recovery path resolves it. The scheduler SHALL NOT re-evaluate
Owner Attention Policy, recalculate `deliver_at`, re-resolve a target, or append
a late row when it encounters a wake-recovery-related record.

`abort.v1` SHALL persist a reason-specific run and row outcome before it
releases any reservation. An `ordinary_preprepare_cancel` may terminate only a
current-fence `claimed` or `preparing` run before any durable prepare result,
cutoff, or `release_prepared` row exists and before a DND or retained outcome
has won. It records `aborted_preprepare` with an empty cohort audit, changes no
row status, and makes a late same-fence prepare request return the terminal
abort.

This parent packet defines no scheduler-visible post-prepare cancellation
route. Once any row is `release_prepared`, an ordinary cancellation SHALL NOT
return it to `pending`, make it eligible for a generic scheduler scan, or
authorize a partial send. The frozen cohort remains protocol-bound under its
run and fence. `bu-qs702` owns the future durable Scheduler/Messenger
post-prepare cancellation-admission contract; `bu-12iab` owns canonical DND
versioning/invalidation. This packet does not prescribe either prerequisite's
fields or state transitions.

Every other wake-recovery abort or recovery remains scheduler-ineligible:

| Outcome | Durable run and row state | Scheduler and replay rule |
|---|---|---|
| No durable prepare result | `ordinary_preprepare_cancel` records current-fence `aborted_preprepare` with an empty cohort audit and no row transition. | No scheduler eligibility changes. A late same-fence prepare/replay returns the terminal abort; it cannot reserve a row after cancellation. |
| Post-prepare ordinary cancellation | This parent packet defines no cancellation transition after a durable prepare result. The frozen cohort keeps its protocol state and fence. | No row becomes `pending`; no generic scheduler scan or partial send is allowed. The future durable admission contract belongs to `bu-qs702`. |
| DND block | Explicit abort records `aborted_dnd`; the full uncommitted cohort becomes `release_retained_dnd` with its old run/fence evidence. | No row becomes `pending`. Same-fence replay returns the DND outcome; only DND clear plus a later qualifying accepted direct owner DM may open a higher-fence successor that adopts the complete cohort. |
| Retained unavailable or oversize | The run remains `retained_unavailable` or `retained_oversize` for same-fence recovery, or records reason-tagged `aborted_retained` / `release_retained_*` on explicit abandonment. | No row becomes `pending`. Replay uses the frozen cutoff, participant responses, and manifest; it cannot add a late row, omit a participant, or mint another action. |
| Retained target mismatch | The run remains `retained_mismatch` or records `aborted_retained` / `release_retained_mismatch` with its exact target evidence. | No row becomes `pending`. Replay returns the mismatch; recovery may not default-resolve a target or release a partial cohort. |
| Committed, delivered, or ambiguous egress | Rows remain `release_committed` and bound to the action key; delivery is immutable `egress_delivered` audit; uncertainty is `egress_ambiguous` with provider-attempt evidence. | No row becomes `pending`. Same-fence replay returns the recorded action/receipt, and ambiguity requires explicit reconciliation with no automatic resend or scheduler fallback. |

Rows admitted after an origin-local prepare cutoff SHALL remain `pending` and
SHALL be eligible only for a later accepted wake or their normal stored delivery
path. They are not aborted cohort rows and SHALL NOT be appended to the frozen
run.

#### Scenario: Scheduler skips a prepared cohort
- **WHEN** a due row has been moved from `pending` to a valid
  `release_prepared` state by an origin-local prepare transaction
- **THEN** the ordinary scheduler does not select or send it
- **AND** it does not re-gate the stored envelope or recalculate its delivery
  decision

#### Scenario: Post-prepare cancellation remains protocol-bound
- **WHEN** an ordinary cancellation is requested after any participant has
  durably prepared a row or frozen a cutoff
- **THEN** this parent packet makes no row scheduler-visible `pending` and
  does not create a partial-send route
- **AND** the cohort remains fenced until its existing retained, commit, or
  prerequisite-defined recovery path applies

#### Scenario: Pre-durable-prepare cancellation does not change scheduling
- **WHEN** `ordinary_preprepare_cancel` records `aborted_preprepare` before any
  durable prepare result or row reservation at the current fence
- **THEN** no row changes from `pending` and the scheduler receives no new
  eligibility transition
- **AND** a late same-fence prepare cannot reserve a row after the cancellation

#### Scenario: DND and retained aborts stay outside the scheduler
- **WHEN** a `blocked_dnd`, unavailable, oversize, or target-mismatch cohort is
  aborted or retried
- **THEN** its rows remain reason-tagged wake-recovery records rather than
  scheduler-visible `pending`
- **AND** DND requires a later qualifying owner DM after DND clears, while a
  retained retry preserves its same-fence all-or-nothing cutoff and manifest

#### Scenario: Late row does not join a frozen run
- **WHEN** a matching quiet-hours hold is admitted after an origin has recorded
  its prepare cutoff for a wake run
- **THEN** the row remains `pending` and outside that run's manifest
- **AND** the scheduler does not change the stored row merely because the wake
  run is in progress

#### Scenario: Committed ambiguity never falls back to ordinary flush
- **WHEN** a committed wake cohort reaches `egress_ambiguous`
- **THEN** its rows remain bound to the wake-recovery action and recovery audit
- **AND** neither `abort.v1` nor the ordinary scheduler can send them as an
  independent fallback or return them to `pending`
