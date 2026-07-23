## ADDED Requirements

### Requirement: Canonical DND Mutation and Durable Generation
The system SHALL represent logical DND state through one singleton,
monotonically increasing context-bus guard in `public`. The guard SHALL carry a
non-negative `BIGINT` generation and SHALL be advanced exactly once for each
successful new canonical DND mutation. A logical DND state is the OR of active
RFC 0009 DND rows written by General and Switchboard; it SHALL NOT use a
per-writer row version as its admission fence.

The only canonical DND writers SHALL be General and Switchboard. General's
explicit-context `set_context` and `clear_context` paths, and any future
Switchboard DND path, SHALL route `signal_type="dnd"` through a single
versioned atomic mutation operation. The operation SHALL require an immutable
`mutation_id`, writer identity, operation, and correlation reference. It SHALL
lock the guard, validate authorization, mutate only the caller's DND row,
advance generation, and persist a receipt/audit in one transaction. A committed
observer SHALL never see a DND row change without the corresponding advanced
generation, or an advanced generation without the corresponding row change.

The mutation audit SHALL deduplicate `mutation_id`. An exact replay SHALL
return the original receipt without mutating DND or generation; a replay with
different writer, operation, or payload identity SHALL fail closed as an
idempotency conflict. Mutation receipts and audits SHALL retain generation,
writer, operation, correlation, and timestamps but SHALL NOT copy raw user
message text, optional DND value text, notification content, or provider
payloads.

#### Scenario: General DND set atomically advances the guard
- **WHEN** General submits a new correlated DND set with guard generation `N`
- **THEN** the committed context row is active and the durable receipt records
  generation `N + 1`
- **AND** no reader can observe either committed effect without the other

#### Scenario: Switchboard clear preserves another writer's logical DND
- **WHEN** General and Switchboard both have active DND rows and Switchboard
  clears only its own row
- **THEN** the guard advances exactly once and Switchboard's row is cleared
- **AND** a current DND snapshot remains active because General's row remains
  active

#### Scenario: Exact mutation replay is idempotent
- **WHEN** a canonical writer retries an already committed mutation with the
  same mutation ID and identical identity
- **THEN** it receives the original generation and receipt
- **AND** no second DND row mutation, audit row, or generation increment occurs

#### Scenario: Conflicting mutation replay fails closed
- **WHEN** a caller reuses a persisted mutation ID with a different writer,
  operation, or payload identity
- **THEN** the operation returns an idempotency-conflict error
- **AND** it does not change a DND row, guard generation, or prior receipt

#### Scenario: Concurrent canonical DND writers serialize
- **WHEN** General and Switchboard concurrently submit new DND mutations
- **THEN** their guard updates serialize into contiguous generations with no
  lost update
- **AND** each resulting receipt identifies the generation it committed

### Requirement: DND Snapshot and Serialized Admission
The system SHALL provide a durable DND snapshot containing `generation`,
`dnd_active`, `observed_at` from database time, and `revalidate_at` when a
time-based expiry can change the observed state. A snapshot is evidence only;
it SHALL NOT by itself authorize an external effect.

A consumer that needs to turn an inactive snapshot into a durable admission
SHALL revalidate it inside the same database transaction that writes the
consumer's own local admission record. It SHALL lock the singleton guard with a
share lock, require the captured generation to match, re-read canonical DND
state using database time, and require DND to be inactive while the lock is
held. Canonical writers SHALL take the conflicting update lock before changing
their DND row. The consumer SHALL commit or roll back its local durable effect
before releasing the guard lock; it SHALL NOT hold the lock across MCP or
provider I/O.

Health SHALL own its policy/wake decision and Messenger SHALL repeat this
guarded admission in the transaction that persists any future egress intent.
Switchboard SHALL carry versioned correlation through authenticated MCP packets
only; it SHALL NOT substitute a local SQL check for Health or Messenger, read a
peer queue, or gain a peer-schema grant.

#### Scenario: DND changes after snapshot and before admission
- **WHEN** a consumer captures inactive generation `N` and a canonical DND
  mutation commits generation `N + 1` before the consumer obtains the guard
  lock
- **THEN** the consumer rejects the stale snapshot before writing its durable
  admission record
- **AND** no external effect is authorized from that snapshot

#### Scenario: Local admission wins the guard ordering
- **WHEN** a consumer obtains the guard share lock for inactive generation `N`
  and writes its local durable admission record while a canonical DND writer
  races it
- **THEN** the writer waits until the consumer commits or rolls back
- **AND** a committed writer mutation advances the guard only after that local
  admission boundary

#### Scenario: Messenger performs the final DND check
- **WHEN** Health has supplied a captured DND generation to a future
  wake-recovery delivery path
- **THEN** Messenger revalidates that generation and inactive DND state in the
  transaction that persists its own egress intent
- **AND** a changed or unprovable generation prevents that intent from being
  created

#### Scenario: Admission evidence is unavailable
- **WHEN** the guard row, canonical DND rows, database time, or required
  generation evidence cannot be read or validated
- **THEN** the consumer fails closed and records no durable admission or
  external effect

### Requirement: DND Expiry, Restart, and Generation Failure Closure
An active DND snapshot SHALL set `revalidate_at` to the earliest active DND
expiry calculated with database time. Consumers SHALL not rely on active
snapshot evidence at or after that timestamp; they SHALL re-read under the
guard. Expiry itself SHALL NOT require a background writer or generation bump,
because it only transitions an active row to inactive and a fresh guarded read
observes that state. Any later canonical DND set, refresh, reactivation, or
explicit clear SHALL be a mutation that advances generation.

The guard and mutation audit SHALL be the only recovery source after restart.
No in-memory cache, reconstructed client timestamp, or replayed connector event
shall be authoritative. The generation SHALL never wrap, reset, or be reused.
If a mutation would exceed the `BIGINT` maximum, the operation SHALL fail
before changing DND state, record an operator-visible failure, and require an
explicit migration/recovery procedure.

#### Scenario: Active DND expires without a writer
- **WHEN** an active DND snapshot reaches its `revalidate_at` time without a
  canonical mutation
- **THEN** a consumer rejects the cached active evidence and performs a fresh
  guarded read using database time
- **AND** the fresh read excludes the expired DND row

#### Scenario: Restart reconstructs committed DND state
- **WHEN** a process restarts after a DND mutation commits
- **THEN** it reconstructs the generation and replay receipt from durable guard
  and mutation records plus canonical context rows
- **AND** it does not infer ordering from process memory or client timestamps

#### Scenario: Generation exhaustion fails closed
- **WHEN** the next canonical DND mutation would exceed the guard's `BIGINT`
  maximum
- **THEN** the operation fails before changing context state or emitting a new
  successful receipt
- **AND** it does not wrap, reset, or reuse the generation
