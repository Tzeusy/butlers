## MODIFIED Requirements

### Requirement: Smoke Tests Run In CI As A Fast Gate
The smoke tier SHALL execute in CI (`.github/workflows/ci.yml`) on every push and
pull request as a fast gate, distinct from and faster than the integration tier,
and MUST NOT pull in the E2E suite or any real LLM dependency.

#### Scenario: Dedicated smoke selection in CI
- **WHEN** the CI `check-unit` job runs
- **THEN** smoke tests are selected via `-m smoke` (excluding `e2e` and any real-LLM
  paths) and run before or alongside the heavier `check-integration` job
- **AND** a smoke failure fails `check-unit` and therefore the fail-closed `check`
  fan-in

#### Scenario: No E2E or real-LLM dependency in the smoke gate
- **WHEN** the smoke step runs in CI
- **THEN** it does not require `ANTHROPIC_API_KEY` or the `claude` CLI
- **AND** `tests/e2e` is excluded from the smoke selection, consistent with the
  existing E2E CI-exclusion mechanisms
