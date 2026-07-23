## ADDED Requirements

### Requirement: DND Guard Least-Privilege Mutation Boundary
The DND generation guard and its mutation audit SHALL live in the shared
`public` schema as context-bus infrastructure. Runtime roles may read the
guard only as required for a context snapshot or their own guarded admission.
Only General and Switchboard may invoke the canonical DND mutation operation;
Health, Messenger, connectors, and all other butlers SHALL have no DND mutation
authority.

The core migration SHALL prevent direct DND inserts, updates, clears, and
deletes against `public.user_context` from bypassing the canonical operation,
while preserving the existing authorized non-DND context paths. It SHALL grant
only the minimum execute/select privileges required by the canonical writers
and admission readers. It SHALL NOT grant Health, Messenger, or Switchboard
read access to another butler's private schema, a shared DSN, or a peer queue.

The mutation operation SHALL validate the effective writer identity in addition
to its caller-supplied writer field. Development-mode absence of `SET ROLE` may
not silently widen DND authority: if the operation cannot prove its required
authorization and atomic guard boundary, it SHALL fail closed.

#### Scenario: Health may read but cannot mutate DND
- **WHEN** Health reads a DND generation snapshot for its policy admission
- **THEN** it reads only the public context-bus guard and canonical public DND
  state
- **AND** an attempt to invoke a DND mutation is rejected before any row,
  generation, or audit change

#### Scenario: Generic direct DND DML is rejected
- **WHEN** any runtime role attempts to insert, update, clear, or delete a DND
  context row without the canonical mutation operation
- **THEN** the database rejects the operation
- **AND** it does not create an unversioned DND state transition

#### Scenario: Authorized writer uses the guarded operation
- **WHEN** General or Switchboard invokes the canonical DND mutation operation
  with its own verified role and valid correlation
- **THEN** it receives only the mutation receipt permitted by the context-bus
  contract
- **AND** it gains no access to Health, Messenger, or any other private schema

#### Scenario: Admission remains schema-local
- **WHEN** Messenger performs the final guarded DND admission for a future
  egress intent
- **THEN** it holds the public guard while writing only its own durable record
- **AND** it does not obtain SQL access to an origin butler's deferred queue
