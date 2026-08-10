## ADDED Requirements

### Requirement: Runtime Attention Outbox Least-Privilege Authorization

The core migration SHALL grant the public runtime-attention outbox only the
minimum authority needed for its ownership model. Butler runtime roles that
produce breaker or fleet-halt edges SHALL have no raw `INSERT`, `SELECT`,
`UPDATE`, or `DELETE` permission on outbox rows. They may only `EXECUTE` a
narrow fixed-search-path `SECURITY DEFINER` producer operation that derives the
safe payload, immutable source key, and deduplication key from a validated
qualifying dispatch attempt or fleet-halt evidence, and verifies the current
runtime role owns that evidence. The operation SHALL reject caller-controlled
recipient, payload, delivery state, source key, and arbitrary deduplication
data. Switchboard alone receives the required select/update authority to claim
and transition episodes through the external delivery boundary. The dashboard
operator surface SHALL receive sanitized read data through its API without
granting ordinary runtime roles access to other producers' episode payloads.

ID: REQ-database-security-007
Source: heart-and-soul/security-and-secrets.md; RFC 0003; RFC 0006; database-security Public Schema Write Authorization Matrix; design.md Decision 4
Scope: v1-mandatory

#### Scenario: Runtime producer has only validated append authority

- **WHEN** a butler runtime operating under its `SET ROLE` records a
  qualifying breaker or fleet-halt edge
- **THEN** it can invoke the authorized producer operation that appends the
  corresponding outbox episode and its own dispatch provenance in one
  transaction
- **AND** direct `INSERT`, `SELECT`, `UPDATE`, and `DELETE` attempts against
  the outbox are rejected for that role

#### Scenario: Producer cannot forge another runtime's attention episode

- **WHEN** a runtime role supplies an attempt, fleet window, recipient,
  lifecycle state, or payload that is not server-derived from its authorized
  source evidence
- **THEN** the producer operation rejects the call without appending an
  episode
- **AND** no arbitrary role with `EXECUTE` can create a Switchboard-pageable
  attention record for another runtime

#### Scenario: Switchboard can claim without peer-schema access

- **WHEN** Switchboard operates under its runtime role to process pending
  runtime-attention episodes
- **THEN** it can select and transition public outbox rows required for its
  durable claim and delivery lifecycle
- **AND** it gains no read or write grant to a producer's private schema

#### Scenario: Unrelated runtime and connector roles cannot inspect episodes

- **WHEN** a non-producing runtime role or `connector_writer` attempts to read
  or mutate runtime-attention episodes
- **THEN** the database rejects the attempt
- **AND** the migration does not grant a shared privileged DSN or broad
  cross-schema access as a workaround
