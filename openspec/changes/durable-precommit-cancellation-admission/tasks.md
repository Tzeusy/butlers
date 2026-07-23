## 1. Durable private and origin-local state

- [ ] 1.1 Add Messenger-owned prepared-release-gate and
  cancellation-admission records keyed by the immutable cancellation action
  key, with request fingerprints, DND evidence, decision states, and no raw
  notification/DND/provider payload retention.
- [ ] 1.2 Add origin-local cancellation-ready/frozen-subset/publish receipts,
  plus Switchboard-owned current-fence finalization and DND-abort-fanout
  receipts, without granting any peer queue or Messenger table access.
- [ ] 1.3 Add migrations and actual-runtime-role ACL tests proving Messenger
  owns its private admission record, Health reads only public DND evidence, and
  Switchboard cannot SQL-read an origin queue or Messenger release gate.

## 2. Authenticated cancellation and guard admission

- [ ] 2.1 Implement validated `wake_recovery.cancel_admit.v1` and
  `wake_recovery.cancel_publish.v1` request/receipt schemas, caller
  authentication, stable cancellation/publish action and request identifiers,
  global cohort plus per-origin frozen-subset bindings, and semantic replay
  fingerprints.
- [ ] 2.2 Serialize Messenger cancellation, commit, and release through the
  same prepared-release gate, enforcing the no-egress-intent/no-send-start
  predicate before `accepted_precommit` is recorded.
- [ ] 2.3 Invoke the canonical RFC 0009 DND admission helper on Messenger's
  transaction connection; map changed/active/unprovable evidence to a durable
  `rejected_blocked_dnd` receipt and same-fence Switchboard fanout through the
  parent `abort.v1(reason=blocked_dnd)` / `release_retained_dnd` path rather
  than a scheduler return.
- [ ] 2.4 Implement exact replay, conflicting replay, stale/cross-run fence,
  egress-present, and ambiguous-state behavior without inventing replacement
  action keys or provider retries.

## 3. All-cohort finalization and Scheduler gate

- [ ] 3.1 Implement same-fence origin finalization that proves each immutable
  local frozen subset and moves every matching local prepared row to
  scheduler-ineligible cancellation-ready state only from an accepted Messenger
  receipt.
- [ ] 3.2 Persist and validate the complete participant finalization digest in
  Switchboard before any origin accepts a `cancel_publish.v1` authorization;
  reject partial, changed-global-or-local-digest, stale, cross-origin, or
  mismatched publication.
- [ ] 3.3 Make the deferred-notification Scheduler reject prepared,
  cancellation-ready, DND-blocked, egress-present, and ambiguous cohorts, and
  preserve cancellation evidence through any later final Messenger admission.

## 4. Behavior-executing verification and rollout

- [ ] 4.1 Add PostgreSQL concurrency tests for DND-writer-before-admission,
  admission-before-writer, cancellation-versus-commit gate ordering, exact and
  conflicting replay, and no egress intent/send-start on accepted cancellation.
- [ ] 4.2 Add MCP/integration tests for direct-caller rejection, complete versus
  partial participant digests, per-origin frozen-subset proof without peer
  schema access, `cancel_publish.v1` exact/conflicting replay across restart,
  DND-abort fanout/replay, stale/cross-run requests, timeout/restart recovery,
  and no scheduler visibility before complete publication or retained DND abort.
- [ ] 4.3 Add send-start/provider-receipt/ambiguous-attempt tests proving no
  cancellation success, scheduler fallback, or automatic resend after egress
  evidence exists.
- [ ] 4.4 Run strict OpenSpec validation, focused role/contract/integration
  tests, repository quality gates, and a staged recovery drill before enabling
  a parent wake-recovery cancellation path.
