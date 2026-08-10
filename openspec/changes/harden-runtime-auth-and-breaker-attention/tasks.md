## 1. Durable state and authorization foundations

- [ ] 1.1 Add a guarded core migration for `public.runtime_attention_outbox`, its safe lifecycle constraints, uniqueness/indexes, append-only producer grants, Switchboard claim grants, and the known OpenCode Go identifier data correction; write migration tests for upgraded, core-only, and role-enforced databases.
- [ ] 1.2 Add a single serialized qualifying-dispatch outcome recorder used by Spawner failure/success provenance, including stable attempt-ID ordering, per-catalog-entry transaction serialization, and same-transaction breaker-edge episode append; replace direct model-breaker alert invocation.
- [ ] 1.3 Move the fleet-halt breach-edge producer onto the same recorder/outbox facility and remove its direct audit-marker/ledger/notification debounce path without backfilling historic breaches.

## 2. Canonical CLI-auth authority

- [ ] 2.1 Extend `CredentialStore` with an explicit system-global authority channel and strict CLI-auth read/write operations that cannot silently fall back to a schema-local value; preserve existing local-first behavior for ordinary domain credentials.
- [ ] 2.2 Refactor CLI-auth persistence, lifecycle restoration, daemon construction, live Codex reconciliation, dashboard device-auth/probe paths, and connector startup to pass and use the explicit authority; retain only safe local-conflict diagnostics.
- [ ] 2.3 Add focused credential and runtime tests covering stale local versus fresh authority, flat topology, multiple daemons sharing one Codex home, unavailable authority, conditional rotation/health fencing, atomic file writes, and no credential-content logging.

## 3. Provider-native model execution and verification

- [ ] 3.1 Implement runtime/provider-specific catalog validation for the known OpenCode Go prefix, surface actionable API validation errors, and update OpenCode adapter tests to preserve provider-native/bare versus qualified identifiers correctly.
- [ ] 3.2 Implement the deterministic Switchboard-owned runtime-probe coordinator using the resolved catalog entry, shared runtime home, authoritative credentials, adapter construction, and runtime args without domain MCP tools or routed dispatch provenance.
- [ ] 3.3 Route per-model Test, verify-all, and scheduled verification through the coordinator; preserve verification history semantics, return an honest unavailable state, and prove probe success never closes a breaker.

## 4. Switchboard-owned operational attention delivery

- [ ] 4.1 Implement the outbox repository and Switchboard worker with durable `pending` claim, `sending` pre-transport commit, bounded proven-pre-send retry, terminal `sent`/`failed`/`uncertain` transitions, recovery behavior, and safe structured observability.
- [ ] 4.2 Refactor Switchboard notification routing so a confirmed Messenger send remains confirmed when routing-log, registry, notification-log, audit, or attention-ledger bookkeeping fails; preserve clear not-attempted versus uncertain outcomes.
- [ ] 4.3 Add role-isolation and concurrency integration tests proving producer append-only authority, Switchboard-only claim/delivery, one edge episode under concurrent breaker failures, no automatic replay after an ambiguous send, and no delivered-message retry after a post-send ACL error.

## 5. Operator-facing truth and deliberate recovery

- [ ] 5.1 Extend the Models API with safe latest-attention-episode observation, explicit runtime-probe semantics, and a server-enforced idempotent endpoint that creates at most one successor for a confirmed uncertain episode.
- [ ] 5.2 Update `SettingsModelsPage` and its tests to render verification, routing eligibility, breaker state, and attention state independently; add an accessible confirmation-gated `Send a new alert` action only for eligible uncertain episodes.
- [ ] 5.3 Keep Spend fleet-halt visibility intact while reflecting the new durable attention evidence where available; ensure degraded outbox/attempt sources are shown as unavailable rather than no-alert/no-denial states.
- [ ] 5.4 Add safe logs, counters, and operator diagnostics for authority selection, ignored local CLI-auth scope, breaker-edge episodes, delivery outcomes, and coordinator availability without secret or raw provider-error disclosure.

## 6. Contract, regression, and runtime verification

- [ ] 6.1 Add requirement-ID citations to the focused unit, API, migration, ACL, concurrency, adapter, and frontend tests introduced by this change; run the relevant tests first, then the affected backend/frontend suites.
- [ ] 6.2 Reconcile the changed capability specifications and implementation documentation, including the corrected OpenCode Go bootstrap examples and the Models-page distinction between a runtime probe and breaker recovery.
- [ ] 6.3 After code review and deployment authorization, validate the exact deployed runtime: authority provenance without revealing values, one shared Codex auth restore result, provider-native OpenCode resolution, one alert per breaker edge, no automatic ambiguous resend, `/api/health`, and the Models/Spend API/UI truth surfaces.
