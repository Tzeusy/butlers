## ADDED Requirements

### Requirement: Durable Runtime Attention Episodes

The system SHALL represent model-breaker and fleet-halt owner pages as durable,
public runtime-attention episodes. A producer SHALL append an immutable,
safe-payload episode in the same database transaction that establishes the
corresponding operational state edge. Each episode SHALL have a stable ID and
a unique deduplication key, source, lifecycle state, timestamps, sanitized
error classification, and optional lineage to an explicitly reissued episode.
It SHALL store neither credential values nor raw provider error payloads.

ID: REQ-runtime-attention-outbox-001
Source: heart-and-soul/vision.md Rule 3 and Rule 4; RFC 0001; RFC 0011 Amendment 1; design.md Decisions 3-5
Scope: v1-mandatory

#### Scenario: A breaker opening atomically creates one episode

- **WHEN** recording a qualifying `runtime_failure` changes one catalog
  entry's derived breaker from closed to open
- **THEN** that transaction appends exactly one `model_breaker` attention
  episode keyed to the immutable triggering dispatch-attempt ID
- **AND** a transaction rollback persists neither the qualifying outcome nor
  its episode

#### Scenario: Concurrent breaker failures cannot create duplicate episodes

- **WHEN** concurrent qualifying failures target the same catalog entry
- **AND** one transaction has already established the closed-to-open breaker
  edge
- **THEN** every other transaction observes the resulting breaker state before
  it can append an episode
- **AND** only the edge-triggering dispatch attempt has an episode

#### Scenario: A failed half-open probe is a new episode

- **WHEN** a cooldown-expired breaker entry is selected as a half-open probe
- **AND** that routed probe records a qualifying failure that reopens the
  breaker
- **THEN** the new closed-to-open edge creates one new episode
- **AND** its deduplication key is distinct from the earlier opening episode

#### Scenario: Existing incidents are not re-paged during migration

- **WHEN** the outbox migration is deployed while a breaker is already open or
  a calendar-month fleet halt is already active
- **THEN** it creates no retrospective episode or external page
- **AND** historical dispatch, ledger, notification, and audit evidence
  remains readable and unchanged

### Requirement: Switchboard-Owned At-Most-Once Attention Delivery

Switchboard SHALL be the sole external delivery claimant for runtime-attention
episodes. Producers may append their authorized rows but SHALL not claim,
mutate, inspect other producers' payloads, or call Messenger directly. Before
external transport may begin, Switchboard SHALL durably claim the episode as
`sending`. A confirmed send transitions it to `sent`; a definitive rejection
transitions it to `failed`; an ambiguous send outcome transitions it to
`uncertain` and is never retried automatically.

ID: REQ-runtime-attention-outbox-002
Source: heart-and-soul/vision.md Rule 3; RFC 0003; RFC 0011 Amendment 1; design.md Decisions 4-5
Scope: v1-mandatory

#### Scenario: Claim precedes external transport

- **WHEN** Switchboard selects a pending episode for delivery
- **THEN** it durably records `sending` before it invokes Messenger or a
  transport adapter
- **AND** concurrent workers cannot claim the same episode

#### Scenario: Proven pre-send failures may use bounded backoff

- **WHEN** a claimed episode fails before any external transport can have
  started
- **THEN** Switchboard MAY return it to pending with a bounded next-attempt
  time and safe failure context
- **AND** it SHALL not consume a new deduplication key or create a duplicate
  attention episode

#### Scenario: Ambiguous transport is never replayed automatically

- **WHEN** an episode is `sending` and Switchboard times out, loses a
  connection, or recovers after a process death without proof that transport
  was not attempted
- **THEN** the episode becomes terminal `uncertain`
- **AND** no worker, recovery loop, or dashboard refresh sends it again

#### Scenario: Post-send bookkeeping cannot reverse delivery

- **WHEN** Messenger confirms delivery and a later routing-log, registry,
  notification-log, audit, or attention-ledger write fails
- **THEN** the episode remains `sent`
- **AND** the bookkeeping failure is recorded as safe observability evidence
  without creating another send attempt

### Requirement: Explicit Uncertain-Episode Reissue

The system SHALL permit an operator to explicitly reissue an `uncertain`
runtime-attention episode only after a confirmation-gated action. The action
SHALL create a new pending
episode with immutable lineage to the original; it SHALL never overwrite the
original state, reset a breaker, or cause an automatic replay.

ID: REQ-runtime-attention-outbox-003
Source: heart-and-soul/vision.md Rule 1 and Rule 4; RFC 0005; design.md Decisions 4 and 6
Scope: v1-mandatory

#### Scenario: Confirmed manual reissue creates a distinct episode

- **WHEN** an operator confirms a reissue for an `uncertain` episode
- **THEN** the system creates one new pending episode with a fresh ID and
  deduplication key and a reference to the original episode
- **AND** the original remains `uncertain` with its original timestamps and
  safe error evidence

#### Scenario: Reissue does not alter routing eligibility

- **WHEN** an operator reissues a model-breaker attention episode
- **THEN** the model's breaker state remains derived only from qualifying
  routed dispatch outcomes
- **AND** a runtime probe, reissue, or outbox state transition does not write a
  synthetic routed success or close the breaker
