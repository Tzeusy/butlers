## ADDED Requirements

### Requirement: Restore-Drill Bootstrap Privilege Boundary
The managed database bootstrap process SHALL grant `CREATEDB` only to the
configured migration/connecting role that the restore-drill command uses. Every
`butler_*_rw` runtime role and `connector_writer` SHALL remain `NOCREATEDB`,
and no runtime configuration, dashboard/API response, or credential surface
shall expose an alternative privileged database connection for a drill.

ID: REQ-database-security-006
Source: RFC 0006 § Database Connection Scoping; heart-and-soul/security.md § Schema Isolation
Scope: v1-mandatory

#### Scenario: Bootstrap grants only the connecting role
- **WHEN** `scripts/init-db.sql` runs for a configured migration/connecting role
- **THEN** that role has `CREATEDB` after the idempotent bootstrap completes
- **AND** every `butler_*_rw` role and `connector_writer` remains `NOCREATEDB`
- **AND** the bootstrap process does not create a second login role or a new
  privileged credential solely for the restore drill

#### Scenario: Runtime role cannot create a scratch database
- **WHEN** a connection has assumed any `butler_*_rw` role or `connector_writer`
- **THEN** an attempt to create a database is denied by PostgreSQL
- **AND** the denial does not cause the runtime connection to shed its `SET ROLE`
  restriction or acquire a broader role

#### Scenario: Privilege repair requires the managed bootstrap path
- **WHEN** an operator encounters a restore-drill `CREATEDB` prerequisite failure
- **THEN** the documented recovery path directs the operator to the managed
  bootstrap process
- **AND** it does not direct the operator to run ad hoc `ALTER ROLE`, pre-create
  a scratch database, or expose a superuser connection through the application

### Source References

- Non-Negotiable Rule 1 (`about/heart-and-soul/vision.md`): owner-controlled
  infrastructure remains recoverable without widening runtime privileges.
- Non-Negotiable Rule 3 (`about/heart-and-soul/vision.md`): database boundaries
  are structural, not a convenience bypass.
- RFC 0006 § Database Connection Scoping: runtime `SET ROLE` enforces the
  schema-scoped least-privilege model.
