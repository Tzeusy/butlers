## ADDED Requirements

### Requirement: Projection Provenance Truth and Source-Ledger Hygiene

The Calendar module SHALL preserve provider events in the workspace projection
while carrying durable provenance needed by downstream analysis. A Google
date-only event (both boundaries use the provider `date` form) SHALL project
with `all_day=true`. A legacy event with `all_day=false` whose duration is at
least 24 hours and whose boundaries are both local midnight in its valid stored
IANA timezone SHALL be recognized as a non-meeting by analysis consumers.

The module SHALL retain provider rows whose `metadata.butler_generated` value
is true in the workspace projection. It SHALL not delete, hide, or change the
provider-authoritative state of those rows merely because they are
butler-generated.

On startup, the module SHALL idempotently delete source-ledger rows with
exactly these source keys: `internal_scheduler:butler`,
`internal_scheduler:butlers`, and `internal_reminders:butlers`. The purge SHALL
use no wildcard or source-name policy and SHALL preserve normal source/event/
instance cascade semantics. Internal source registration SHALL reject an
invalid roster butler name without writing a source row, and SHALL continue to
register valid roster names. All of these projection paths SHALL retain their
existing fail-open behavior when projection tables are unavailable.

#### Scenario: Google date-only event projects as all-day

- **WHEN** a Google event payload has date-only `start.date` and `end.date`
- **THEN** the parsed provider event and its projected `calendar_events` row
  have `all_day=true`
- **AND** the original date boundaries and provider source remain preserved

#### Scenario: Butler-generated provider event remains visible

- **WHEN** a provider event carries `metadata.butler_generated=true`
- **THEN** it is upserted into the existing workspace projection with that
  provenance retained
- **AND** no source or event row is deleted or hidden because of the marker

#### Scenario: Only obsolete internal source keys are purged

- **WHEN** startup ledger hygiene runs with obsolete rows and a valid internal
  source row present
- **THEN** it deletes only `internal_scheduler:butler`,
  `internal_scheduler:butlers`, and `internal_reminders:butlers`
- **AND** the valid source row remains registered with its existing events and
  instances intact

#### Scenario: Invalid roster name cannot create an internal source

- **WHEN** internal source registration is requested for a butler name that is
  not present in the roster
- **THEN** no `calendar_sources` row is written
- **AND** a request for a valid roster name still performs the normal idempotent
  source upsert
