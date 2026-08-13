## 1. Contract and additive persistence

- [ ] 1.1 Confirm the owner-approved RFC 0023 constants: closed state/reason vocabulary, action-key format, lease/backoff/stuck SLOs, and the per-provider idempotency/reconciliation capability inventory.
- [ ] 1.2 Add guarded Approvals migrations for `approval_delivery_intents`, append-only attempts, safe terminal event vocabulary, due/lease indexes, foreign keys, and fail-closed downgrade checks; do not backfill legacy rows.
- [ ] 1.3 Add the narrowly wired Messenger approval-handoff migration keyed by delivery idempotency key, with pre-provider start persistence and non-destructive downgrade checks; do not restore retired generic tracking tables.
- [ ] 1.4 Add real-PostgreSQL migration tests proving fresh/upgrade shape, legacy `approval_push_emissions` preservation, no historical intent creation, safe check constraints, and downgrade refusal while recovery data exists.

## 2. Atomic parking admission and producer conversion

- [ ] 2.1 Refactor `src/butlers/modules/approvals/park.py` into the sole typed transaction helper that validates origin/dossier inputs, inserts or resolves the action, computes RFC 0021 admission, and inserts one intent/action key atomically.
- [ ] 2.2 Move burst reservation from independent `approval_push_emissions` work into the helper's same-transaction admission path, preserving the first-three / digest / collapsed result and leaving legacy emissions read-only.
- [ ] 2.3 Convert the gate and all three recipient/email guard paths to the new helper without changing their fail-closed approval decision behavior.
- [ ] 2.4 Convert the core notify missing-identifier path, daemon calendar-overlap path, and dashboard connector-disconnect path to the new helper.
- [ ] 2.5 Convert relationship assertion plus memory fact retraction, entity merge, email identity enrichment, and memory reclassification curation paths to the new helper, preserving each producer's semantic deduplication contract.
- [ ] 2.6 Add a source-level producer inventory/AST contract that rejects every direct `pending_actions(status='pending')` insert outside the helper while allowing explicitly auto-approved paths.

## 3. Fenced notification-only recovery worker

- [ ] 3.1 Implement the schema-local intent repository and state machine with due selection, `FOR UPDATE SKIP LOCKED` claims, token/fence/lease CAS transitions, safe attempt recording, and deterministic database-time backoff.
- [ ] 3.2 Add a daemon-owned approval-delivery lifecycle loop that starts only for active Approvals schemas and receives a narrow notification runtime, never approval operations, executor, entity/fact, or generic deferred-queue authority.
- [ ] 3.3 Render `single` and `burst_digest` envelopes deterministically at dispatch time using current verified owner resolution and callback-secret lookup in memory only; make `collapsed` terminal without a provider call.
- [ ] 3.4 Implement stale-claim recovery, `handoff_started` reconciliation, derived stuck status, and safe no-retry handling for unknown post-start outcomes.

## 4. End-to-end handoff idempotency

- [ ] 4.1 Extend `NotifyDeliveryV1`, Switchboard delivery forwarding, and normalized response models for recovery delivery idempotency keys and `confirmed` / `safe_retry` / `ambiguous` result classes while preserving ordinary `notify.v1` compatibility.
- [ ] 4.2 Implement Messenger's real route.execute/provider-boundary handoff ledger, same-key reconciliation, receipt/duplicate-safe response, and explicit ambiguity handling for adapters without proof-bearing idempotency.
- [ ] 4.3 Wire the source worker to persist a fenced pre-provider marker, send/reconcile only the immutable action key, and forbid a fresh key or provider call after an ambiguous outcome.
- [ ] 4.4 Add adapter-capability tests showing confirmed same-key duplicate suppression, safe pre-start retry, and Telegram-style unknown post-start no-resend behavior.

## 5. Decision, expiry, retention, and operator truth

- [ ] 5.1 Introduce a shared action-then-intent terminal transition helper and use it in approve, reject, explicit/stale expiry, and any future pending-to-terminal path; preserve executor and defer behavior.
- [ ] 5.2 Ensure the worker only observes action eligibility and writes intent/attempt evidence; cover the send-start-versus-decision linearization race and late-result no-revival rule.
- [ ] 5.3 Extend approval retention and immutable safe delivery-summary audit events so unresolved/ambiguous intents survive while their action is pending and terminal cleanup follows the established provenance contract.
- [ ] 5.4 Extend approval API models, router joins, frontend types, and Approvals page rendering with safe delivery-state truth, legacy evidence labeling, and no “never attempted” fabrication.
- [ ] 5.5 Add safe metrics/logs/read-model aggregation for due age, retry/lease backlog, ambiguous/stuck counts, and closed reason dimensions without sensitive labels or action-mutating controls.

## 6. Real-PostgreSQL fault, concurrency, and compatibility verification

- [ ] 6.1 Add real-PostgreSQL transaction tests for action-plus-intent rollback, semantic-key duplication, concurrent burst admission, and complete production callsite coverage.
- [ ] 6.2 Add multi-worker real-PostgreSQL tests for `SKIP LOCKED` claims, stale lease fencing, token mismatch, heartbeat/terminal-write rejection, and restart recovery before send start.
- [ ] 6.3 Add crash-injection tests at claim, pre-handoff marker, Messenger handoff persistence, provider acceptance before source result, terminal-result persistence, and daemon restart boundaries.
- [ ] 6.4 Add decision/expiry race tests proving cancellation before handoff prevents send, handoff-first blocks future recovery only, and the worker never mutates a parked domain action.
- [ ] 6.5 Add RFC 0021 regression tests for exact quiet-hours release/no re-gate, control-plane budget isolation, and concurrent first-three/digest/collapsed behavior outside generic deferred delivery.
- [ ] 6.6 Add API/frontend redaction and truthful-state tests plus retention/downgrade/stuck-observability tests, then run focused and required broader quality gates from the exact head.

## 7. Additive rollout and rollback gate

- [ ] 7.1 Ship additive schema/read compatibility and metrics with new writers/workers disabled; verify legacy rows are not backfilled, replayed, or dual-sent.
- [ ] 7.2 Execute an owner-authorized staging/canary drill using synthetic newly parked actions only, including worker restart, provider ambiguity, quiet-hours, and decision-race reconciliation.
- [ ] 7.3 Enable new writers/workers schema-by-schema only after the canary evidence and dashboard truth review; monitor stuck/ambiguous/oldest-due metrics.
- [ ] 7.4 Document binary rollback as additive and block schema downgrade/drop while any intent/attempt/audit data exists; do not delete, replay, approve, execute, or backfill historical actions.
