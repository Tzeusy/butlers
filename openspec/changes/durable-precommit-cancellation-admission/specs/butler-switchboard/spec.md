## ADDED Requirements

### Requirement: Switchboard-Mediated Wake-Recovery Cancellation
Switchboard SHALL be the only cross-butler relay for a future wake-recovery
precommit cancellation. It SHALL validate the local Scheduler/Health decision
against the durable current-fence run, snapshot participant set, frozen cohort,
and release action before it calls Messenger. It SHALL relay the exact stable
cancellation action key, request correlation, DND-generation evidence, and
opaque decision reference without inventing a replacement action or reading a
peer schema.

At prepare time, Switchboard SHALL persist the immutable ordered per-origin
frozen-subset manifest that `cohort_digest` commits to. After a Messenger
`accepted_precommit` receipt, it SHALL collect same-fence finalization receipts
from every participant before it sends authenticated
`wake_recovery.cancel_publish.v1` packets. Each packet carries the recipient's
own origin-frozen-subset digest/count as well as the global participant/cohort and
finalization commitments, with a stable per-origin action/request identity.
Switchboard SHALL retain every publish receipt and replay the exact packet after
a timeout or restart; it SHALL not infer success from the cohort digest.

On a durable Messenger `rejected_blocked_dnd` receipt, Switchboard SHALL persist
a same-fence fanout record and invoke the parent
`strict-owner-telegram-wake-recovery` `abort.v1(reason=blocked_dnd)` operation
for every current participant. It SHALL retain/replay each parent abort until
every participant returns its parent receipt and every origin has its
parent-defined `release_retained_dnd` result. It SHALL not send
`cancel_publish.v1`, query DND for an origin, read a peer queue, request a
partial cancellation, recompute the cohort, or dispatch a provider action.
Other rejected/ambiguous results retain the same action and remain
scheduler-ineligible.

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

#### Scenario: DND rejection fans out only through the parent retained path
- **WHEN** Messenger returns a durable `rejected_blocked_dnd` receipt for the
  current cancellation action
- **THEN** Switchboard replays the same-fence parent `abort.v1(reason=blocked_dnd)`
  operation to every current participant until each has its parent receipt and
  every origin has the parent-defined retained result
- **AND** no origin receives `cancel_publish.v1` or a direct DND-derived SQL
  state change
