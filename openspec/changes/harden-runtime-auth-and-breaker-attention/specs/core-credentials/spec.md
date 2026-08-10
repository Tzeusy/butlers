## MODIFIED Requirements

### Requirement: Live Codex Device-Auth Reconciliation

The runtime SHALL treat an explicitly supplied system-global Tier 1
`cli-auth/codex` authority as the authoritative Codex device-auth state in
every topology. In flat topology the authority pool MAY be the same object as
the local pool, but callers SHALL still select it explicitly rather than
deriving authority from fallback order. Before a new Codex subprocess is
launched, the runtime SHALL reconcile that DB-backed authority to the
canonical local `~/.codex/auth.json` path when the contents differ. The
reconciliation SHALL never log credential content, SHALL write a replacement
atomically with mode `0600`, and SHALL refresh the local rotation baseline
after a DB-originated write.

All `cli-auth/codex` restore, live Codex reconciliation, Codex
runtime-originated rotation persistence, Codex dashboard device authentication,
Codex runtime probes, and Codex-dependent connector startup paths SHALL use the
explicit authority channel. They SHALL not read a schema-local
`cli-auth/codex` row as a fallback or bootstrap source. Ordinary domain
credentials and existing other-provider CLI-auth authority behavior retain
their existing resolution behavior.

ID: REQ-core-credentials-001
Source: heart-and-soul/security-and-secrets.md; RFC 0006; core-credentials Live Codex Device-Auth Reconciliation; design.md Decision 1
Scope: v1-mandatory

#### Scenario: Dashboard refresh takes effect on the next invocation

- **WHEN** the dashboard stores a newer authoritative `cli-auth/codex` value
  while a daemon remains running with a different local `auth.json`
- **THEN** the next Codex invocation SHALL use the authoritative value without
  requiring a daemon restart
- **AND** no completed or already-running session SHALL be changed or replayed

#### Scenario: A schema-local row cannot shadow authority

- **WHEN** a schema-isolated daemon has an older local `cli-auth/codex` row
  and the explicit authority contains a newer dashboard credential
- **THEN** restoration, reconciliation, and runtime-originated persistence use
  the authority value
- **AND** the local row neither reaches a shared runtime file nor prevents the
  authoritative credential from reaching the next invocation

#### Scenario: Multiple shared-volume writers converge on authority

- **WHEN** multiple in-process daemons sharing a Codex runtime filesystem
  restore CLI auth during startup
- **THEN** each writes the same authoritative document or reports authority
  unavailability
- **AND** startup order cannot make a schema-local credential the final shared
  file contents

#### Scenario: Matching local token is left untouched

- **WHEN** the authoritative `cli-auth/codex` value exactly matches the
  canonical local `auth.json`
- **THEN** reconciliation SHALL not replace the file
- **AND** it SHALL record the existing file as the rotation baseline

#### Scenario: Unavailable authority fails closed for new auth-dependent work

- **WHEN** the authority is absent, unavailable, exceeds the bounded
  synchronization wait, or is malformed
- **THEN** reconciliation SHALL log only safe context and SHALL not expose a
  raw credential value
- **AND** it SHALL not launch a new Codex subprocess by falling back to a
  schema-local credential or an unverified local auth file
- **AND** it SHALL not change or replay an already-running session

#### Scenario: Concurrent reconciliation cannot expose a partial file

- **WHEN** multiple local runtime invocations reconcile the same Codex
  auth-file path concurrently
- **THEN** every visible file state SHALL be a complete credential document
- **AND** the final file mode SHALL remain `0600`

#### Scenario: A stale runtime rotation cannot overwrite a dashboard refresh

- **WHEN** a Codex subprocess was launched with an older authority snapshot
  and the dashboard writes a newer `cli-auth/codex` value before that process
  finishes
- **THEN** post-invocation rotation persistence SHALL perform a conditional
  update using the launch snapshot
- **AND** its update SHALL be skipped when the authority value has changed

#### Scenario: A stale runtime health result cannot affect a dashboard replacement

- **WHEN** a Codex subprocess launched on an older authority reports an auth
  failure after the dashboard has stored a replacement credential
- **THEN** its credential health update SHALL be conditional on the exact
  credential bytes used by that subprocess
- **AND** it SHALL not mark the replacement credential failing

#### Scenario: Value replacement atomically clears prior health state

- **WHEN** a runtime health update for credential A obtains the row lock before
  a dashboard refresh or a winning runtime rotation replaces A with B
- **THEN** the value-changing write SHALL clear the prior test status, code,
  message, and verification timestamp in the same database statement
- **AND** B SHALL not inherit A's healthy or failing state

#### Scenario: Dashboard runtime probe binds to the canonical authority it tests

- **WHEN** a dashboard-requested runtime probe begins with authoritative
  credential B while the canonical local auth file still contains A
- **THEN** the runtime-probe coordinator SHALL reconcile the canonical file to
  B before running the provider command
- **AND** it SHALL persist health, probe history, and audit evidence only when
  that file still matches B and the authority value remains B
- **AND** a concurrent replacement or local-file change SHALL leave the
  operator response intact while withholding its durable health result

#### Scenario: Absent authority is never implicitly bootstrapped

- **WHEN** the shared Codex credential is absent, revoked, unavailable, or
  malformed while a canonical local auth file exists
- **THEN** a runtime preflight or post-operation finalizer SHALL NOT create or
  recreate the authority from that local file
- **AND** explicit dashboard device authentication remains the supported
  bootstrap path for a new authority value

#### Scenario: Direct dispatcher authority is explicit

- **WHEN** a direct `DiscretionDispatcher` has only a schema-local model pool
- **THEN** it SHALL not construct a Codex credential authority from that pool
- **AND** callers with a known system-global credential authority SHALL pass it
  explicitly to the runtime adapter

#### Scenario: Ignored local CLI-auth evidence is safe and diagnostic only

- **WHEN** a local CLI-auth row differs from the explicit authority
- **THEN** the runtime MAY record safe, value-free diagnostic metadata that the
  local scope was ignored
- **AND** it SHALL not reveal either credential, token fingerprint, or raw
  serialized auth document

## ADDED Requirements

### Requirement: Non-Enumerable Runtime-Probe Control Capability

The system SHALL use a distinct infrastructure control secret named
`RUNTIME_PROBE_CONTROL_TOKEN` to authenticate the private Dashboard/Scheduler
to Switchboard runtime-probe control plane. It SHALL be delivered through a
dedicated deployment-secret mount readable only by the dashboard control
client, registered verification scheduler, and Switchboard. It SHALL NOT be
stored in a schema-local or `public.butler_secrets` credential row, resolved by
`CredentialStore`, or supplied through an environment-value fallback. It SHALL
not be exposed to a browser, generic MCP client, model session, normal MCP
client manager, telemetry, audit note, log, or generic Secrets API inventory,
detail, mutation, or fingerprint response. The generic Secrets API SHALL reject
this reserved control-secret key rather than creating a shadow DB credential.
Missing, malformed, or unavailable mounted secret state SHALL make the control
plane unavailable; it SHALL not fall back to an unauthenticated command.

ID: REQ-core-credentials-002
Source: heart-and-soul/security-and-secrets.md; RFC 0003; dashboard-model-settings REQ-dashboard-model-settings-001; design.md Decision 2
Scope: v1-mandatory

#### Scenario: Missing mounted control secret fails closed before runtime work

- **WHEN** the dashboard control client, scheduler, or Switchboard cannot
  read `RUNTIME_PROBE_CONTROL_TOKEN` from its dedicated deployment-secret mount
- **THEN** the requested runtime probe reports the control plane unavailable
  without catalog lookup, runtime launch, or verification persistence
- **AND** it does not use a credential-store value, local value, environment
  fallback, or generic MCP route as a substitute

#### Scenario: Private control token remains outside browser, MCP, and generic Secrets surfaces

- **WHEN** the dashboard requests a runtime probe or the scheduler runs one
- **THEN** the server-side dedicated control client supplies the token only on
  the internal control-plane request
- **AND** the browser payload, generic MCP tool list/call, runtime prompt,
  telemetry, logs, and generic Secrets API inventory/detail/mutation/audit
  responses contain no token value or token-derived fingerprint

#### Scenario: Generic Secrets API cannot create a shadow control token

- **WHEN** a browser-facing generic Secrets API caller inventories, fetches,
  mutates, or attempts to create `RUNTIME_PROBE_CONTROL_TOKEN`
- **THEN** the key is absent from inventory/detail responses and mutation is
  rejected as reserved for deployment-secret control use
- **AND** no token value or fingerprint is added to an API or audit response
