## ADDED Requirements

References: `frontend/src/components/qa/QaKpiStrip.tsx`, `frontend/src/pages/QaOverviewPage.tsx`.

### Requirement: QA summary and case rail source honesty

The QA overview SHALL distinguish an unavailable summary or case source from a successful empty result.

#### Scenario: Summary unavailable

- **WHEN** the QA summary is loading or errors without cached data
- **THEN** KPI context names the summary as unavailable and MUST NOT claim no repairs or a calm zero

#### Scenario: Case rail unavailable

- **WHEN** the case rail query errors
- **THEN** it renders a named degraded note with retry
- **AND** a successful empty query continues to render "Nothing in the dossier."

## Source References

- Doctrine rule: `about/craft-and-care/review-and-documentation.md` -- failure states must remain diagnosable.
- RFC: `about/legends-and-lore/` source-honesty and degraded-envelope conventions.
