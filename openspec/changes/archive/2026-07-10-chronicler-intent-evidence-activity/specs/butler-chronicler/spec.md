# Butler Chronicler — Spec delta for chronicler-intent-evidence-activity

## MODIFIED Requirements

### Requirement: Storage Shape

Episodes and point events SHALL retain their existing shape, with two additions:
every episode MUST carry a `layer` (`intent` | `evidence` | `activity`) and every
`activity`-layer episode MUST carry a `confidence` (`high` | `medium` | `low`) and
`evidence_refs[]`. Overlapping episodes SHALL remain permitted.

#### Scenario: Episode records its layer and confidence

- **WHEN** an inferred activity is stored
- **THEN** its `layer` is `activity`
- **AND** it carries a `confidence` and links to its corroborating evidence

#### Scenario: Overlapping episodes permitted

- **WHEN** two episodes from different sources cover overlapping time
- **THEN** both SHALL be stored
- **AND** neither SHALL be merged or discarded at storage time

### Requirement: Calendar Scheduled Blocks Are Not Attendance Assertions

Calendar blocks SHALL project to the `intent` layer and MUST NOT be counted as
lived time on their own. Lived time SHALL be counted only from the `activity`
layer; a calendar block contributes time to an aggregate solely when an
independent activity corroborates it, attributed to that activity's lane.

#### Scenario: Calendar block never asserts attendance

- **WHEN** a calendar block is projected
- **THEN** it is layer `intent`
- **AND** it is excluded from lived-time totals unless an activity corroborates
  it
- **AND** corroborated time is attributed to the activity's lane, not "calendar"

## Source References

- Non-Negotiable Rules (vision.md): schema isolation; MCP-only inter-butler
  communication.
- RFC 0014 (Chronicler Time Butler).
