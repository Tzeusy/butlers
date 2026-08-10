## ADDED Requirements

### Requirement: Runtime Attention Outbox Least-Privilege Authorization

The core migration SHALL grant the public runtime-attention outbox only the
minimum authority needed for its ownership model. Butler runtime roles that
produce breaker or fleet-halt edges may append authorized episodes but SHALL
not select, update, delete, claim, or directly deliver them. Switchboard alone
receives the required select/update authority to claim and transition episodes
through the external delivery boundary. The dashboard operator surface SHALL
receive sanitized read data through its API without granting ordinary runtime
roles access to other producers' episode payloads.

ID: REQ-database-security-007
Source: heart-and-soul/security-and-secrets.md; RFC 0003; RFC 0006; database-security Public Schema Write Authorization Matrix; design.md Decision 4
Scope: v1-mandatory

#### Scenario: Runtime producer has append-only outbox authority

- **WHEN** a butler runtime operating under its `SET ROLE` records a
  qualifying breaker or fleet-halt edge
- **THEN** it can append the corresponding outbox episode and its own dispatch
  provenance in the same transaction
- **AND** direct `SELECT`, `UPDATE`, and `DELETE` attempts against the outbox
  are rejected for that role

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
