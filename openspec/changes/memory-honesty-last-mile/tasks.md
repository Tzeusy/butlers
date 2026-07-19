## 1. Episode consolidation lifecycle

- [ ] 1.1 Add failing module-memory regressions for pending claims, failed rows
  before and after their retry timestamp, expired leases, dead-letter exclusion,
  and concurrent claimant safety.
- [ ] 1.2 Update the schema-qualified episode claimant to select only eligible
  pending/failed rows, preserve ordered `FOR UPDATE SKIP LOCKED` grouping, and
  never automatically select `dead_letter` or `consolidated` rows.
- [ ] 1.3 Complete lifecycle persistence for failed, terminal, and successful
  outcomes: sanitized errors/reasons, bounded retry timing, lease clearing, and
  truthful public-field reset behavior.
- [ ] 1.4 Add focused lifecycle-event regressions proving terminal failure and
  owner requeue event payloads contain no raw runtime, prompt, credential, or
  lease data.

## 2. Memory API truth and bounded requeue

- [ ] 2.1 Extend episode response projections and frontend API types to carry
  only the approved lifecycle dossier fields; do not expose worker lease
  internals.
- [ ] 2.2 Add API regressions for episode/fact/rule detail resolution: found
  rows win over unrelated degraded pools, clean misses are 404, and unresolved
  named failures are source-named 503s.
- [ ] 2.3 Make episode, fact, rule, and inspect `meta.total` exact after their
  filters, independent of the bounded globally merged page; retain named
  `meta.pools_failed` for genuine source failures and test healthy/degraded
  counts, ordering, and `has_more`.
- [ ] 2.4 Implement `POST /api/memory/episodes/{id}/requeue` behind the
  dashboard owner guard, with schema-qualified target resolution and a
  parameterized conditional dead-letter-to-pending transaction that writes one
  sanitized lifecycle event.
- [ ] 2.5 Add API/auth/race regressions for requeue success, malformed UUID,
  clean 404, named 503, non-owner 403, non-dead-letter 409, and two concurrent
  calls yielding exactly one queued outcome/event.
- [ ] 2.6 Prove the requeue request never invokes a spawner, consolidation
  runner, scheduler run-now path, MCP tool, or bulk replay path; keep migrations
  and direct operator SQL out of this implementation.

## 3. Truthful and accessible dashboard surfaces

- [ ] 3.1 Update EpisodeDetailPage, FactDetailPage, and RuleDetailPage so only
  true 404s render not-found copy; render named 503 and other query failures as
  visible retryable errors, with focused regression coverage.
- [ ] 3.2 Add the episode lifecycle dossier and owner/dead-letter-only requeue
  control, including queued-not-running, conflict, and failure landing states;
  test keyboard operation, visible focus, disabled-in-flight behavior, and live
  announcements.
- [ ] 3.3 Render `SourceDegradedNote` for episode/fact/rule registers and
  inspect search whenever `meta.pools_failed` is non-empty, including a
  zero-row partial response, while retaining healthy true-empty behavior.
- [ ] 3.4 Route SearchResults through the shared query boundary and implement
  URL-backed inspect paging from exact API metadata, including qualified ranges
  while sources are degraded; test loading, error, clean empty, filter, and
  back/forward page behavior.
- [ ] 3.5 Add local accessible success/failure feedback to the Fact detail
  Confirm and Retract footer without changing request payloads or optimistic
  rollback/cache semantics; test both actions, rollback, retryability, and
  non-duplicated screen-reader announcements.

## 4. Cross-contract verification and handoff

- [ ] 4.1 Run the focused module-memory, dashboard API, frontend, and
  accessibility regression suites named above; expand to the repository's
  required quality gates in proportion to the merged implementation risk.
- [ ] 4.2 Validate that public copy, API types, and tests jointly preserve the
  no-run-now/no-bulk/no-MCP boundary and do not widen into activity, entities,
  or re-embedding surfaces.
- [ ] 4.3 Run `openspec validate memory-honesty-last-mile --strict`, review the
  final diff against the proposal/design/spec scenarios, and record the actual
  verification evidence before implementation reconciliation.
