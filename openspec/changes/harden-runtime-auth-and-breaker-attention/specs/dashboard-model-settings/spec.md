## ADDED Requirements

### Requirement: Catalog Test Uses a Runtime Probe, Not a Dashboard-Local Adapter

The Models API's per-entry test and scheduled verification SHALL invoke a
deterministic Switchboard-owned runtime-probe coordinator. The coordinator
SHALL use the same runtime home, authoritative CLI-auth source, adapter
construction, canonical model identifier, runtime-specific execution mapping,
generated runtime configuration, and runtime arguments as a new daemon
invocation, but SHALL expose no domain MCP tools and SHALL not create routed
dispatch provenance. It SHALL be reached only through an authenticated
dashboard-to-Switchboard control-plane command that is not registered in the
generic MCP/LLM tool surface. The command accepts only a catalog entry ID,
enforces owner authorization, bounded timeout, per-entry de-duplication, and a
bounded global concurrency cap, and accepts no credential material, prompt,
model override, or runtime arguments from the dashboard. A successful probe
updates verification evidence only; it does not close an open breaker.

ID: REQ-dashboard-model-settings-001
Source: dashboard-model-settings Catalog Verify-All API and Hourly Automated Verification Sweep; model-catalog REQ-model-catalog-001; design.md Decisions 2 and 6
Scope: v1-mandatory

#### Scenario: Test checks the routed runtime environment

- **WHEN** an operator selects `Test` for a catalog entry or the scheduled
  verification sweep runs
- **THEN** the request is executed by the runtime-probe coordinator using the
  same shared runtime environment, canonical-to-execution mapping, generated
  runtime configuration, and catalog arguments as new daemon work
- **AND** the returned evidence is labelled as a runtime probe rather than a
  routed session result

#### Scenario: Probe control command is not a generic routable tool

- **WHEN** a model session, ordinary MCP client, or unauthenticated caller
  enumerates or invokes Switchboard tools
- **THEN** it cannot discover or invoke the runtime-probe control command
- **AND** only the authorized dashboard control-plane client can request a
  bounded probe by catalog entry ID

#### Scenario: Probe success does not close a breaker

- **WHEN** a breaker-open entry's runtime probe succeeds
- **THEN** the API persists its verification result without inserting
  `model_dispatch_attempts.success`
- **AND** the list response and Models page continue to show the entry as
  breaker-open until a later routed success is recorded

#### Scenario: Probe coordinator unavailability is honest

- **WHEN** the runtime-probe coordinator is unavailable or cannot establish
  the authoritative runtime environment, exceeds its rate/concurrency limit,
  or reaches its bounded timeout
- **THEN** the test response reports the coordinator as unavailable or degraded
  without overwriting the last successful verification evidence
- **AND** the UI does not show a successful model test or a generic provider
  failure for that condition

### Requirement: Model Breaker Attention Episode Visibility and Reissue

The Models list and per-entry detail API SHALL expose the latest relevant
model-breaker attention episode's sanitized lifecycle state, timestamps, and
safe reason independently from verification and breaker facts. The Models page
SHALL make an `uncertain` episode's one permitted manual reissue deliberate:
it presents a confirmation-gated `Send a new alert` control, disables it while
the request is pending or a successor exists, and immediately reports the new
episode result. Every Models endpoint that exposes attention episode data or
permits reissue SHALL use a fail-closed `require_dashboard_owner_control`
server dependency. That dependency SHALL require a configured non-empty
`DASHBOARD_API_KEY` and a constant-time matching `X-API-Key` header, treating a
valid key as the single dashboard-owner principal; it SHALL not inherit the
dashboard's optional general API-auth behavior. No UI visibility rule is an
authorization substitute. No other attention state offers an automatic resend
control.

ID: REQ-dashboard-model-settings-002
Source: heart-and-soul/vision.md Rule 1; RFC 0005; runtime-attention-outbox REQ-runtime-attention-outbox-003; design.md Decision 6
Scope: v1-mandatory

#### Scenario: Independent operational facts are visible

- **WHEN** the Models page renders a catalog entry with verification evidence,
  an open breaker, and an attention episode
- **THEN** it renders those as distinct labelled facts with canonical status
  indicators and safe timestamps/reasons
- **AND** a runtime-probe success explicitly states that it does not clear the
  breaker

#### Scenario: Manual reissue is server-enforced and idempotent

- **WHEN** an operator confirms `Send a new alert` for an `uncertain` episode
- **THEN** the API creates or returns exactly one successor episode for that
  original episode and returns both safe episode identities and states
- **AND** concurrent or retried submissions cannot create additional
  successors for the same original episode

#### Scenario: Owner-control configuration and credentials are required before observation or delivery

- **WHEN** the owner-control key is absent from server configuration and a
  caller requests attention detail or `Send a new alert`
- **THEN** the API returns a safe `503` owner-control-unavailable response
  without exposing the episode, creating a successor, or invoking delivery
- **WHEN** the configured key is present but a caller omits or supplies a wrong
  `X-API-Key`
- **THEN** the API returns `401` without exposing the episode, creating a
  successor, or invoking delivery
- **WHEN** a caller supplies the matching configured `X-API-Key`
- **THEN** it is the authenticated dashboard-owner principal eligible for the
  existing observation/reissue state checks

#### Scenario: Non-uncertain episode cannot be resent from the Models page

- **WHEN** a caller requests a manual reissue for a pending, sending, sent,
  failed, or already-reissued episode
- **THEN** the API rejects it without creating an episode or external delivery
- **AND** the UI keeps the control absent or disabled with an accessible reason

#### Scenario: Attention observation degradation stays truthful

- **WHEN** the API cannot read the model's attention-episode source
- **THEN** the response marks that observation unavailable rather than
  returning no episode as a proven no-alert state
- **AND** existing verification and breaker fields retain their independently
  available values
