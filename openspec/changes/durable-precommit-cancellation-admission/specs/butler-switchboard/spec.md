## ADDED Requirements

### Requirement: Switchboard-Mediated Wake-Recovery Cancellation
Switchboard SHALL be the only cross-butler relay for a future wake-recovery
precommit cancellation. It SHALL validate the local Scheduler/Health decision
against the durable current-fence run, snapshot participant set, frozen cohort,
and release action before it calls Messenger. It SHALL relay the exact stable
cancellation action key, request correlation, DND-generation evidence, and
opaque decision reference without inventing a replacement action or reading a
peer schema.

After a Messenger `accepted_precommit` receipt, Switchboard SHALL collect
same-fence finalization receipts from every participant before it publishes the
complete finalization digest. It SHALL retain and replay the same action when a
participant is unavailable, a receipt conflicts, or Messenger returns a
rejected/ambiguous result; it SHALL not request a partial cancellation,
recompute the cohort, or dispatch a provider action.

#### Scenario: Switchboard forwards only a durable current-fence decision
- **WHEN** Health or an origin Scheduler supplies cancellation evidence for the
  current wake run
- **THEN** Switchboard verifies the immutable run/fence/digests/action binding
  before it calls Messenger
- **AND** a stale or changed local decision reaches no participant or egress
  surface

#### Scenario: Unavailable participant preserves the exact cancellation action
- **WHEN** Messenger accepts cancellation but a required participant is
  unavailable during finalization
- **THEN** Switchboard retains the cohort and retries the same action and
  participant set
- **AND** it does not publish scheduler work or create a replacement action key
