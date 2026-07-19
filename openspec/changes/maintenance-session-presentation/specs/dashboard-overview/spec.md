## ADDED Requirements

### Requirement: Internal maintenance rollup in Dashboard Now

Dashboard Now SHALL remain owner-focused by default and SHALL not use
successful maintenance runs as ordinary recent activity. It SHALL provide the
same accessible, URL-backed Internal lens as the Timeline. When enabled,
Dashboard Now SHALL render compact per-butler maintenance rollups from the
Timeline event machine class and link them to the Timeline with its Internal
lens enabled. Failed maintenance sessions SHALL remain visible as error
activity while the lens is disabled.

#### Scenario: Dashboard Now defaults to owner activity

- **WHEN** Dashboard Now receives successful maintenance Timeline events and
  the URL does not include `internal=1`
- **THEN** it does not render those events as ordinary activity rows
- **AND** it continues to render owner activity and error rows

#### Scenario: Internal Dashboard Now lens groups maintenance by butler

- **WHEN** the operator enables the Internal lens and multiple loaded
  maintenance events belong to the same butler
- **THEN** Dashboard Now renders one maintenance rollup with the exact loaded
  event count for that butler
- **AND** its link opens the Timeline with `internal=1`
