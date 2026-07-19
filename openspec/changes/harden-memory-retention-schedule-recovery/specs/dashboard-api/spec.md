## ADDED Requirements

### Requirement: Memory stats expose complete-or-unknown expired-retention observation

`GET /api/memory/stats` SHALL add the following backward-compatible fields for
the fleet-wide expired-retention observation:

- `data.expired_retained_episodes: int | null` — aggregate rows matching the
  cleanup predicate when every relevant source completed; `null` when coverage
  is incomplete.
- `data.retention_eligible_episodes: int | null` — aggregate rows with
  `expires_at IS NOT NULL` when every relevant source completed; `null` when
  coverage is incomplete.
- `data.expired_retained_ratio: float | null` — numerator divided by eligible
  denominator when coverage is complete and the denominator is non-zero;
  `null` when coverage is incomplete or the denominator is zero.
- `meta.retention_status: 'healthy' | 'degraded' | 'unknown'`.
- `meta.retention_sources: list` with one row per completed relevant memory
  source: its butler identity, resolved memory schema, expired-retained count,
  eligible count, and ratio (or `null` for a zero denominator).
- `meta.retention_pools_failed: string[]` when one or more relevant source
  queries fail. It is absent or empty only when none fail.

The numerator SHALL use the same episode predicate as the cleanup handler,
currently `expires_at < now()`. A pool with no memory schema is absent rather
than failed and is omitted from the observation. A complete source is
`degraded` when its numerator is greater than zero; all complete sources with
zero numerators produce fleet status `healthy`. If any relevant source query
fails, fleet status SHALL be `unknown`, aggregate data fields SHALL be `null`,
and the failed sources SHALL be named even if all completed sources report
zero. Successful per-source rows MAY remain in `meta.retention_sources` as
lower-bound diagnostic evidence.

The retention-specific tracker is independent from `meta.pools_failed` and
`meta.catalog_pools_failed`: a retention-only failure MUST NOT discard valid
ordinary stats or catalog-drift fields, but it MUST never be presented as a
truthful zero or healthy retention result. This endpoint SHALL remain read-only;
the new fields do not authorize or invoke cleanup, schedule changes, or data
mutation.

#### Scenario: Complete sources with no retained expired episodes are healthy

- **WHEN** every relevant memory source completes and every source has zero rows
  matching `expires_at < now()`
- **THEN** the aggregate counts SHALL be non-null zero values
- **AND** `meta.retention_status` SHALL be `healthy`
- **AND** `meta.retention_pools_failed` SHALL be absent or empty

#### Scenario: Complete source with retained expired episodes is degraded

- **WHEN** every relevant memory source completes and at least one source has
  one or more rows matching `expires_at < now()`
- **THEN** `data.expired_retained_episodes` and
  `data.retention_eligible_episodes` SHALL contain the complete aggregates
- **AND** `meta.retention_sources` SHALL identify the degraded source with its
  count and ratio
- **AND** `meta.retention_status` SHALL be `degraded`

#### Scenario: Retention-only pool failure is unknown, not healthy

- **WHEN** one relevant source's expired-retention query fails while other
  memory statistics remain available
- **THEN** the response SHALL name that source in `meta.retention_pools_failed`
- **AND** the aggregate retention count, denominator, and ratio SHALL be `null`
- **AND** `meta.retention_status` SHALL be `unknown`
- **AND** existing `data` statistics and unrelated degraded-source trackers
  SHALL retain their independently computed values

#### Scenario: Pool without memory schema is absent rather than failed

- **WHEN** a candidate butler pool has no memory schema
- **THEN** it SHALL not appear in `meta.retention_sources` or
  `meta.retention_pools_failed`
- **AND** it SHALL not make the fleet retention status unknown

#### Scenario: Zero eligible denominator has no fabricated ratio

- **WHEN** all completed relevant sources have no rows with `expires_at IS NOT NULL`
- **THEN** `data.expired_retained_episodes` and
  `data.retention_eligible_episodes` SHALL be zero
- **AND** `data.expired_retained_ratio` SHALL be `null`
- **AND** each affected per-source ratio SHALL be `null`
