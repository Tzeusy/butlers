## ADDED Requirements

### Requirement: Retention recovery and observation never authorize historical deletion

Memory retention recovery SHALL be limited to the scheduler control-plane
transition defined by `core-scheduler` and the read-only expired-retention
observation defined by `dashboard-api`. An expired-retention observation MUST
not invoke cleanup, toggle a schedule, enqueue a backfill, change an episode's
expiry, delete a row, send a notification, or mutate provenance/evidence.

The retention observation SHALL use the exact eligibility predicate of ordinary
episode cleanup, currently `expires_at < now()`, rather than a separate expiry
definition. A row with `expires_at IS NULL` is not eligible for this
observation's denominator or numerator. The approved v1 threshold is zero
rows matching the cleanup predicate: a complete source with one or more such
rows is retention-degraded.

Any historical episode operation remains outside this capability until the
separate provenance contract establishes durable-evidence or truthful
source-expired behavior for affected readers and links. A switchboard
historical drain additionally requires explicit owner/ops authorization,
verified backup/restore evidence, a fixed-cutoff dry run, bounded atomic
batches, and the applicable retention-disposition decision. The ordinary
cleanup handler SHALL NOT be repurposed as an unbounded historical backfill.

#### Scenario: Expired-retention observation uses the cleanup population

- **WHEN** a memory source reports its expired-retained episode statistics
- **THEN** its numerator SHALL count exactly rows matching `expires_at < now()`
- **AND** its eligible denominator SHALL count rows with `expires_at IS NOT NULL`
- **AND** the observation SHALL not inspect or return episode content or IDs

#### Scenario: Observation does not trigger cleanup

- **WHEN** the expired-retention count is non-zero or exceeds the approved
  threshold
- **THEN** the statistics path SHALL remain read-only
- **AND** it SHALL not invoke `memory_episode_cleanup`, re-enable a cleanup
  schedule, alter a retention policy, or delete an episode

#### Scenario: Historical drain remains fenced by provenance and owner authorization

- **WHEN** a retained historical episode is selected only because it matches
  the cleanup predicate
- **THEN** this retention-recovery capability SHALL not delete, quarantine, or
  otherwise mutate that episode
- **AND** no historical drain SHALL begin until the separate provenance
  contract and explicit owner/ops gate have both been satisfied

#### Scenario: Ordinary scheduled cleanup remains distinct from a backfill

- **WHEN** an operator has not separately authorized a bounded historical drain
- **THEN** the ordinary cleanup handler SHALL retain its normal scheduled
  behavior only
- **AND** it SHALL not be called as an unbounded catch-up mechanism for the
  historical population observed by this capability
