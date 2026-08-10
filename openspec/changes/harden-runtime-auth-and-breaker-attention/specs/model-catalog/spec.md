## MODIFIED Requirements

### Requirement: Dispatch-Outcome Circuit Breaker

The system SHALL exclude a catalog entry from resolution (initial resolve,
effective-tier resolve, and same-tier failover) when its recent dispatch
outcomes show it is systemically failing. Breaker state SHALL be derived
entirely from `public.model_dispatch_attempts` at query time. Qualifying
outcomes SHALL be recorded through one serialized outcome path that uses a
stable attempt-ID tie-breaker when timestamps are equal.

ID: REQ-model-catalog-001
Source: model-catalog Dispatch-Outcome Circuit Breaker; RFC 0001; RFC 0005; runtime-attention-outbox REQ-runtime-attention-outbox-001; design.md Decision 3
Scope: v1-mandatory

#### Scenario: Breaker opens after consecutive systemic failures

- **WHEN** a catalog entry's most recent `_BREAKER_FAILURE_THRESHOLD` (5)
  dispatch attempts with outcome `runtime_failure` or `success` are ALL
  `runtime_failure`
- **AND** the most recent such attempt occurred within
  `_BREAKER_HALF_OPEN_COOLDOWN_MINUTES` (15) minutes
- **THEN** the entry SHALL be excluded from resolution (initial resolve,
  `resolve_model_with_effective_tier`, and `next_same_tier_candidate`) regardless
  of its `enabled` or `last_verified_ok` values
- **AND** outcomes other than `runtime_failure`/`success` (`quota_skip`,
  `suppressed`, `exhausted`) SHALL NOT count toward or reset the
  consecutive-failure window

#### Scenario: Half-open probe restores eligibility

- **WHEN** a breaker-open entry's most recent qualifying attempt is older than
  the half-open cooldown
- **THEN** the entry SHALL become eligible for resolution again — the next
  resolution that selects it IS the probe, with no separate probe-token state
- **AND** if that probe attempt succeeds, the trailing qualifying window stops
  being all failures and the breaker closes
- **AND** if that probe attempt fails, a fresh `runtime_failure` row extends
  the window and the breaker re-opens for another cooldown period

#### Scenario: A breaker opening creates one durable attention episode

- **WHEN** a qualifying `runtime_failure` provenance write changes a catalog
  entry's breaker from closed to open
- **THEN** the same transaction SHALL append the one corresponding durable
  `model_breaker` attention episode defined by
  `runtime-attention-outbox`
- **AND** it SHALL not directly call Telegram, Messenger, the attention ledger,
  or an audit-marker debounce helper

#### Scenario: Concurrent failure writers observe one opening edge

- **WHEN** multiple qualifying failures are recorded concurrently for one
  catalog entry
- **THEN** serialization makes the closed-to-open transition deterministic
  using the dispatch-attempt ID as a timestamp tie-breaker
- **AND** exactly one resulting attention episode is appended

#### Scenario: Verification evidence does not reset the breaker

- **WHEN** a dashboard or scheduled runtime probe updates
  `last_verified_ok=true` for a breaker-open catalog entry
- **THEN** the entry remains excluded until a qualifying routed
  `model_dispatch_attempts.success` outcome closes the derived breaker
- **AND** the probe writes no synthetic routed success provenance

#### Scenario: Breaker state is exposed for operator visibility

- **WHEN** `GET /api/settings/models` is called (see
  `dashboard-model-settings`)
- **THEN** each entry includes `breaker_open` (bool) and
  `breaker_consecutive_failures` (int), computed via `get_breaker_states` in
  one batched query alongside the row list — not N+1 per-entry queries

#### Scenario: Operator spend rule to a breaker-open model is honored, not excluded

- **WHEN** an operator spend routing rule (`apply_spend_routing_rules`) resolves
  to a catalog entry whose dispatch-outcome circuit breaker is open
- **THEN** the rule SHALL be HONORED — the rule-selected model is returned, NOT
  excluded — because an operator spend rule is an explicit human override,
  distinct from automatic tier/failover resolution
- **AND** the resolver SHALL log a WARNING naming the model, its consecutive
  failure count, and the rule, and surface the open `BreakerState` on
  `SpendRoutingResult.breaker_open`
- **AND** the spawner SHALL record ONE informational
  `public.model_dispatch_attempts` row with outcome `breaker_open_override`
  (a `failure_reason` prefixed `Spend rule routed to breaker-open model`) so
  the operator trail shows the breaker was open at rule-resolution time; this
  outcome is NOT `runtime_failure`/`success`, so it neither trips nor resets
  the breaker
- **AND** existing same-tier failover (`next_same_tier_candidate`, which
  excludes breaker-open entries) SHALL still handle any actual dispatch failure
  of the honored model

#### Scenario: Deterministic fallback ordering

- **WHEN** multiple non-attempted candidates remain in the effective tier
- **THEN** fallback ordering SHALL be deterministic by effective priority
  descending, then `created_at ASC`, then `id ASC`
- **AND** the resolver SHALL NOT return an already-attempted candidate

## ADDED Requirements

### Requirement: Runtime-Specific Catalog Model Identifier Validation

The model catalog SHALL validate a model identifier according to the selected
runtime and provider profile rather than impose a global identifier syntax. For
the configured OpenCode Go profile, a stored identifier prefixed
`opencode-go/` is invalid; its provider-native bare model identifier SHALL be
stored and passed to the runtime. Other OpenCode provider forms SHALL not be
silently normalized.

ID: REQ-model-catalog-002
Source: model-catalog Model Catalog Schema; runtime-opencode Model Selection; design.md Decision 2
Scope: v1-mandatory

#### Scenario: Known invalid OpenCode Go prefix is rejected on mutation

- **WHEN** an operator creates or updates an OpenCode Go catalog entry with a
  `model_id` beginning `opencode-go/`
- **THEN** the API rejects the mutation with an actionable provider-native ID
  validation error
- **AND** it does not persist the invalid identifier

#### Scenario: Guarded migration corrects known affected rows only

- **WHEN** the catalog migration encounters an existing OpenCode Go entry with
  the known invalid prefix
- **THEN** it removes exactly that prefix while preserving the rest of the
  identifier and all unrelated catalog fields
- **AND** it does not rewrite non-Go OpenCode provider identifiers or another
  runtime's model IDs
