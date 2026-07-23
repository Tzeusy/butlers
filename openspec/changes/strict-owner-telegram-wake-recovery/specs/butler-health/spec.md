## ADDED Requirements

### Requirement: Health-Owned Policy-Sleep Wake Commit
Health SHALL participate in a valid wake-recovery run only by validating and,
at fenced commit, superseding its own active deterministic `sleeping` context
whose durable metadata identifies the Owner Attention Policy producer and the
same canonical policy window. Health SHALL validate the authenticated
Switchboard caller, accepted-event/run identity, participant digest, and fence
for prepare, commit, and abort replay safety.

Health SHALL NOT clear explicit DND, a non-policy sleep context, another
butler's context, or any generic user context because of a direct Telegram DM.
If explicit DND is active or wins the final guarded transition, Health SHALL
retain its policy-sleep context and report a DND block without authorizing
egress.

#### Scenario: Matching policy sleep is superseded only at commit
- **WHEN** Health receives a valid fenced prepare followed by a valid commit
  for its active Owner Attention Policy sleep record in the same window
- **THEN** prepare leaves the sleep context intact
- **AND** commit supersedes only that matching Health-owned policy-sleep record

#### Scenario: Non-policy context remains untouched
- **WHEN** Health receives any wake-recovery request while DND is active or
  its `sleeping` context was created by a source other than the deterministic
  Owner Attention Policy producer
- **THEN** Health does not clear or supersede that context
- **AND** it reports the appropriate block or mismatch to Switchboard
