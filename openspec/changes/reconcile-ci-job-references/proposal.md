## Why

PR #3946 splits the hosted Python gate across `check-unit` and
`check-integration`, with the historic `check` status retained as a fail-closed
coverage fan-in. The testing capability and several operational references
still describe smoke, unit, and integration tests as steps of the legacy
single `check` job. Those claims erase the distinction between the jobs that
execute tests and the status that aggregates their results.

## What Changes

- Modify the testing capability's smoke-gate requirement so its CI scenario
  names `check-unit`, the job that executes the smoke selection.
- Reconcile the identified testing and agent guidance with the three-job
  fan-out/fan-in topology.
- Preserve the distinction between local convenience targets and the hosted
  `check-unit` / `check-integration` lanes.
- Leave workflow execution behavior unchanged.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `testing`: identify `check-unit` as the hosted smoke-test job while retaining
  the existing smoke selection, E2E exclusion, and failure guarantees.

## Impact

- Documentation and one OpenSpec delta only; no runtime, workflow, database,
  API, or test-selection behavior changes.
- The baseline `openspec/specs/testing/spec.md` remains untouched until this
  change is archived, avoiding a direct-edit race with OpenSpec's whole-
  requirement replacement semantics.
