## ADDED Requirements

### Requirement: Tracker-Host Export Boundary and Minimal Active Projection

The system SHALL obtain Beads data only through a deterministic exporter in an
operator-authorized tracker-host management workload. The exporter SHALL read
the tracker locally, publish only through a TLS-authenticated,
least-privilege PostgreSQL writer identity, and expose no listener or tracker
operation to a normal runtime container, dashboard request, or prompted LLM.
Beads/Dolt SHALL remain authoritative.

The exporter SHALL project only active `open`, `in_progress`, and `blocked`
issues and their active dependency edges. It SHALL allowlist issue id, title,
status, issue type, priority, created/updated/deadline timestamps, labels, and
the dependency endpoint/type/timestamp fields required by the decision
escalation. It SHALL retain a source description only for an eligible non-epic
decision-labeled issue and only normalized decision options/default plus a
structured-detail availability/reason. It SHALL NOT persist Beads notes,
comments, history, raw metadata, attachments, raw export blobs, tracker
credentials, host paths, or raw failures.

#### Scenario: Runtime has no tracker capability

- **WHEN** a runtime reader, dashboard request, or prompted LLM needs decision
  data
- **THEN** it accesses the explicitly selected source only through
  `BeadReadProvider`
- **AND** it has no `bd` command, Dolt endpoint, tracker credential, tracker
  host route, or `.beads` directory mount
- **AND** explicit JSONL compatibility mode may retain only the existing
  read-only `issues.export.jsonl` file mount until separately authorized
  retirement

#### Scenario: Candidate normalization discards arbitrary metadata

- **WHEN** an active source issue contains arbitrary metadata, notes, history,
  or a non-decision description
- **THEN** the candidate projection stores none of those fields
- **AND** an eligible decision retains only its source description and the
  validated normalized decision fields required by the Decisions contract

#### Scenario: Invalid candidate does not publish raw input

- **WHEN** a local export has malformed JSON, duplicate ids, an invalid active
  dependency endpoint, a malformed required timestamp, or an over-bound field
- **THEN** the exporter records only a categorical failed-run outcome
- **AND** it persists neither the raw export nor the invalid candidate rows
- **AND** it leaves the active snapshot unchanged

### Requirement: Atomic Complete Snapshot Publication and Retention

The projection SHALL use a dedicated `beads_projection` schema with completed
snapshot metadata, snapshot-keyed issue/dependency/lint rows, a singleton
active-snapshot pointer, and categorical sync-run metadata. A publisher SHALL
hold a dedicated PostgreSQL advisory lock and SHALL insert candidate rows,
mark the snapshot complete, and update the active pointer in one transaction.
A failed export, parse, validation, lock, or database write SHALL NOT move the
pointer.

The system SHALL retain the active completed snapshot plus exactly two prior
completed snapshots. It SHALL retain categorical metadata for failed runs for
30 days, without raw export content or raw error text, and SHALL prune older
failed-run metadata safely.

#### Scenario: Publisher crash preserves the previous snapshot

- **WHEN** the exporter crashes or the database transaction fails before the
  active pointer update commits
- **THEN** readers continue to see the previously active complete snapshot
- **AND** no candidate issue, edge, or lint row becomes visible through the
  runtime reader surface

#### Scenario: Successful publication atomically advances the pointer

- **WHEN** a candidate has passed structural validation
- **THEN** its metadata, issues, dependencies, normalized lint state, and
  active pointer commit in one transaction
- **AND** the pointer names that completed candidate only after all of its
  rows are visible

#### Scenario: Retention preserves rollback evidence

- **WHEN** a fourth newer completed snapshot has become active
- **THEN** the active snapshot and its two immediate completed predecessors
  remain readable to the privileged retention process
- **AND** only older complete snapshots are eligible for pruning
- **AND** failed-run rows older than 30 days are eligible for categorical
  metadata cleanup

### Requirement: Bounded Atomic BeadReadProvider and Freshness Classification

`BeadReadProvider` SHALL be the only runtime-facing projection reader. It
SHALL return a typed, bounded snapshot envelope containing availability, source,
snapshot id, completed/source timestamps, freshness state, target-met state,
unavailable reason, active allowlisted issues, dependency edges, and normalized
lint state. Runtime roles SHALL have `USAGE` plus `SELECT` only on the bounded
active-snapshot views; they SHALL NOT receive direct table, history, pointer,
failed-run, sequence, or writer privileges.

The provider SHALL use one `REPEATABLE READ, READ ONLY` transaction and
runtime-facing views rooted at the active pointer. It SHALL verify that every
selected row carries the chosen snapshot id and SHALL fail closed if the
pointer is absent/non-singleton, a required view is unavailable, or a row
belongs to another snapshot.

The provider SHALL classify a completed snapshot age at or below five minutes
as target-fresh, over five through ten minutes as readable-but-target-missed,
over ten through fifteen minutes as `warning`, and over fifteen minutes as
`unavailable`. Missing, unreadable, or schema-mismatched projection data SHALL
also be unavailable with a stable categorical reason. A warning remains
readable but SHALL be observable to consumers. The provider SHALL expose
whether the five-minute target is met separately from warning freshness, so a
readable five-to-ten-minute target miss is observable; unavailable data SHALL
never be represented as an empty snapshot.

#### Scenario: Pointer flip cannot create a mixed snapshot

- **WHEN** publication advances the active pointer while a provider read is in
  progress
- **THEN** that read returns rows from exactly one snapshot id under its
  repeatable-read transaction
- **AND** it returns unavailable rather than combining pointer and row ids if
  the reader surface is inconsistent

#### Scenario: Target miss remains readable before warning

- **WHEN** the active snapshot is more than five and no more than ten minutes
  old
- **THEN** the provider returns its typed rows with `available=true`,
  `freshness=fresh`, and `target_met=false`
- **AND** the target miss is available for consumer status or metrics without
  presenting the source as warning-stale

#### Scenario: Warning freshness remains visible and readable

- **WHEN** the active snapshot is more than ten and no more than fifteen
  minutes old
- **THEN** the provider returns its typed rows with `available=true` and
  `freshness=warning`
- **AND** it includes the completed timestamp and warning classification for
  every consumer to surface

#### Scenario: Hard-stale snapshot is not an all-clear

- **WHEN** the active snapshot is more than fifteen minutes old
- **THEN** the provider returns `available=false` with a stable stale reason
- **AND** it returns no synthetic empty issue list as a successful snapshot

### Requirement: Preserved Decision Lint and Dependency Semantics

The exporter SHALL evaluate the existing strict decision convention semantics
against the candidate's active records, including label-based discovery and
unlabeled legacy title markers. It SHALL store a normalized lint result as
`clean`, `violations`, or `unavailable`; it SHALL preserve bounded violation
ids, titles, and category codes and SHALL never normalize an unavailable lint
into a clean result.

The normalized dependency projection SHALL preserve every active edge needed
to identify an open P1 bug or deploy-marked issue blocked by an eligible
decision. `decision_review` SHALL retain ownership of label-only classification,
structured-detail state, and escalation ordering as pure deterministic logic
over the provider snapshot.

#### Scenario: Lint violation remains an owner-visible finding

- **WHEN** a candidate contains an active title-marker decision without the
  required label or other decision-convention violation
- **THEN** the snapshot carries `lint_status=violations` and the bounded
  violation result
- **AND** the scheduled review path records that result without mutating the
  tracker or reporting a clean audit

#### Scenario: P1 dependency escalation survives projection

- **WHEN** an eligible open decision has an active `blocks` relationship to an
  open P1 bug or deploy-marked issue for more than 48 hours
- **THEN** the provider snapshot yields the same decision id, blocked id,
  kind, and oldest-first escalation result as the equivalent JSONL input

#### Scenario: Lint execution failure is not a clean result

- **WHEN** structural candidate validation succeeds but decision-lint
  evaluation is unavailable
- **THEN** the snapshot carries `lint_status=unavailable` with a categorical
  reason
- **AND** the scheduled review path records the named failure rather than an
  empty clean lint result

### Requirement: Shadow Parity, Explicit Cutover, and Explicit JSONL Rollback

The system SHALL keep runtime readers in an explicitly selected JSONL mode
while the projection runs in shadow mode. For 14 full consecutive days, each
successful shadow cycle SHALL compare legacy JSONL and projection semantic
results for decision order, structured-detail availability/reason, ordered
dependency escalations, and lint state. A mismatch or unavailable source SHALL
emit a bounded operator signal and reset the consecutive-clean counter.

After the fourteen-day parity gate and separate owner authorization, both the
Switchboard and Decisions dashboard SHALL change source mode together to
projection. For those Decisions consumers, JSONL SHALL remain available for
seven calendar days only as an explicit deployment-level rollback selection.
The system SHALL NOT silently fall back between sources or retire JSONL
automatically.

#### Scenario: Shadow mismatch prevents cutover

- **WHEN** a shadow cycle differs in any decision, structured-detail,
  escalation, or lint semantic result
- **THEN** the cycle records a bounded mismatch signal and resets parity
  progress
- **AND** runtime readers remain in explicit JSONL mode

#### Scenario: Explicit rollback is visible

- **WHEN** an owner-authorized post-cutover rollback selects JSONL within the
  seven-day rollback window
- **THEN** both consumers use JSONL on the next deployment/configuration load
- **AND** their provenance identifies `jsonl` rather than hiding the rollback
  as a provider fallback

#### Scenario: JSONL retirement needs separate authority

- **WHEN** the seven-day rollback window expires
- **THEN** JSONL mounts, parser code, and export materialization remain intact
  until a separate owner authorization explicitly retires them

### Requirement: JSONL Consumer Inventory Gates Retirement

The system SHALL treat the selected projection and its cutover as
Decisions-only. `GET /api/beads/{id}` SHALL remain an explicitly retained JSONL
consumer: RFC 0007 Amendment 2's `BeadSnapshotReader` detail contract requires
bounded data including `design` and `acceptance_criteria` that the
Decisions-only active projection does not store. A future retirement packet
SHALL begin with a complete JSONL consumer inventory, and every entry SHALL be
either migrated with contract and regression proof or explicitly retained with
its mount/parser/materialization rationale. Any expansion or migration of
`GET /api/beads/{id}` SHALL require separately scoped security review and is
outside this change.

ID: REQ-beads-projection-005
Source: RFC 0023 §9; RFC 0007 Amendment 2
Scope: v1-mandatory

#### Scenario: Decisions cutover retains the current Bead detail reader

- **WHEN** the fourteen-day Decisions parity gate passes and an authorized
  deployment selects projection mode for the decision consumers
- **THEN** only the Switchboard decision-review jobs and `GET /api/decisions`
  change their selected source
- **AND** `GET /api/beads/{id}` continues through its existing
  `BeadSnapshotReader` JSONL mount/parser/materialization path

#### Scenario: Later retirement packet proves every consumer disposition

- **WHEN** a later packet proposes retirement of a JSONL mount, parser, or
  export materialization path
- **THEN** it includes a complete JSONL consumer inventory
- **AND** every inventory entry is either migrated with contract and regression
  proof or explicitly retained with a documented rationale
- **AND** the proposal cannot treat owner authorization, parity success, or a
  green CI run as a substitute for that evidence

#### Scenario: Bead detail expansion remains separately reviewed

- **WHEN** a later change proposes expanding or migrating
  `GET /api/beads/{id}` beyond RFC 0007 Amendment 2's JSONL contract
- **THEN** it is separately scoped and receives separately scoped security
  review before any detail field, reader, mount, or parser changes
