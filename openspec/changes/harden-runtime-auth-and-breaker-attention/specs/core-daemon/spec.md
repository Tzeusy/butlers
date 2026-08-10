## ADDED Requirements

### Requirement: Authoritative CLI-Auth Restore at Runtime Startup

The daemon SHALL construct and retain an explicit system-global CLI-auth
authority before CLI-auth restore. Every daemon and connector startup restore
that can populate a shared provider runtime home SHALL use that authority,
rather than its schema-local credential namespace or an implicit fallback
pool. The startup path SHALL preserve the current ordering in which CLI-auth
restore completes before a provider runtime is invoked.

ID: REQ-core-daemon-001
Source: RFC 0001 startup phases; heart-and-soul/security-and-secrets.md; design.md Decision 1
Scope: v1-mandatory

#### Scenario: Daemon startup restores from one selected authority

- **WHEN** a daemon reaches its CLI-auth restore phase
- **THEN** it passes the explicit system-global CLI-auth authority to the
  restoration path
- **AND** it does not select a schema-local document merely because that
  document exists first in a layered store

#### Scenario: Flat topology remains explicit

- **WHEN** a deployment has one database pool serving both the local and
  system-global stores
- **THEN** the daemon supplies that pool as the explicit authority
- **AND** authority reads and writes do not degrade into local fallback
  semantics

#### Scenario: Authority loss is reported without stale credential recovery

- **WHEN** the daemon cannot obtain the required authority during restore
- **THEN** it emits safe degraded-startup evidence identifying the unavailable
  authority channel
- **AND** it does not repopulate the provider runtime home from a local
  schema-specific CLI-auth value
