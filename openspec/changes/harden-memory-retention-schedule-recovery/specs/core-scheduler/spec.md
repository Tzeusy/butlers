## ADDED Requirements

### Requirement: Module-default recovery respects TOML provenance and operator disables

The scheduler SHALL distinguish a removed TOML override from an active TOML
schedule before a module-default registration can recover a row. TOML schedule
synchronization SHALL establish the current TOML membership before module-default
recovery is evaluated. A module-default recovery candidate MUST be both:

- a name explicitly registered by the owning module as one of its defaults; and
- the same-named `scheduled_tasks` row with `source='toml'` and `enabled=false`
  after that TOML synchronization.

Recovery SHALL set only that candidate's `source` to `db` and `enabled` to
`true`. It MUST preserve the existing cron, dispatch mode, prompt/job name, job
arguments, complexity, and `next_run_at`. A row with `source='db'` MUST NOT be
re-enabled, rewritten, or audited by module-default recovery, regardless of its
`enabled` state. The scheduler SHALL NOT infer module ownership from a name
prefix, a dashboard request, or arbitrary database state.

#### Scenario: Active TOML default remains TOML-owned

- **WHEN** a registered module default is also present in the active
  `[[butler.schedule]]` configuration
- **THEN** TOML synchronization SHALL own its cadence and enablement
- **AND** module-default recovery SHALL not change its `source` or emit a
  recovery audit entry

#### Scenario: Removed TOML default is recovered after synchronization

- **WHEN** a registered module default has been removed from TOML and the
  synchronized same-named row is `source='toml'` and `enabled=false`
- **THEN** module-default recovery SHALL set that row to `source='db'` and
  `enabled=true`
- **AND** the row's cron, dispatch payload, complexity, and `next_run_at` SHALL
  remain the values it had before the recovery

#### Scenario: Disabled DB-owned schedule remains operator-owned

- **WHEN** a same-named registered default has `source='db'` and `enabled=false`
- **THEN** module-default registration SHALL leave every column unchanged
- **AND** it SHALL not emit a module-default recovery audit entry

#### Scenario: Missing default schedule is created normally

- **WHEN** no same-named row exists for a registered module default after TOML
  synchronization
- **THEN** registration SHALL insert the ordinary enabled `source='db'` default
  using its registered definition
- **AND** the insertion SHALL not be reported as a reclaimed TOML schedule

### Requirement: Module-default recovery and audit are atomic and idempotent

Each successful module-default recovery SHALL append exactly one canonical
`public.audit_log` entry in the same SQL transaction as its conditional schedule
transition. The audit entry MUST use
`action='scheduler.module_default_recovered'`, target `schedule:<name>`, and
control-plane-only metadata containing the prior source, prior enabled state,
and registered default name. It MUST NOT include prompt text, job arguments,
episode content, or any other runtime payload.

The conditional state transition's returned row is the only authority to append
this audit record. If no row transitions, no recovery audit is written. If the
audit insert fails, the transaction SHALL roll back the schedule transition.
Concurrent recovery attempts SHALL result in at most one transitioned row and
at most one committed audit record. A later registration pass after a committed
recovery SHALL be a no-op.

#### Scenario: Recovered row has one durable audit entry

- **WHEN** one eligible TOML-owned disabled module default is recovered
- **THEN** the committed `scheduled_tasks` row SHALL be DB-owned and enabled
- **AND** exactly one committed `public.audit_log` row with
  `action='scheduler.module_default_recovered'` and target `schedule:<name>`
  SHALL describe that transition

#### Scenario: Audit failure rolls back recovery

- **WHEN** the eligible schedule transition is attempted and the canonical
  audit append fails
- **THEN** the transaction SHALL roll back
- **AND** the schedule SHALL retain its pre-transition source and enabled state
- **AND** no `scheduler.module_default_recovered` audit row SHALL exist

#### Scenario: Concurrent recovery attempts produce one transition

- **WHEN** two startup paths concurrently attempt to recover the same eligible
  schedule
- **THEN** at most one attempt SHALL receive the transitioned row
- **AND** at most one recovery audit entry SHALL commit
- **AND** the losing attempt SHALL be a no-op rather than an error or duplicate
  audit event

#### Scenario: Restart after committed recovery is idempotent

- **WHEN** a daemon restarts after a module-default recovery has committed
- **THEN** the now DB-owned enabled row SHALL remain unchanged
- **AND** no additional recovery audit entry SHALL be appended
