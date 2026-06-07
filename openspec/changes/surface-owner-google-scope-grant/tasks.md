# Tasks

This change is **spec-only**. The tasks below are spec-authoring tasks;
implementation is tracked as beads under epic `bu-lmrzg`.

## 1. Spec authoring

- [x] 1.1 Author `specs/dashboard-google-accounts/spec.md` delta:
  - `MODIFIED` Requirement: Per-Account Scope Set Picker — bind to route
    `/secrets?focus=u:google`; add "Picker reachable without a manual identity
    parameter" scenario.
  - `ADDED` Requirement: Owner-Default Google Account Discoverability — with
    "Primary Google account appears", "Multi-account leak prevention", and "No
    Google account connected" scenarios.
- [x] 1.2 Each requirement has at least one `#### Scenario:` with WHEN/THEN/AND.
- [x] 1.3 `proposal.md` and `design.md` record the why, the route binding, the
      primary-only decision, and the boundary with
      `add-connector-oauth-scope-surface`.

## 2. Validation

- [x] 2.1 `openspec validate surface-owner-google-scope-grant --strict` passes.

## 3. Implementation handoff (NOT part of this change — tracked in beads)

- [ ] 3.1 `bu-2kejb` — backend owner-default projection (primary-only) +
      exclusion unit test. Links to §Owner-Default Google Account
      Discoverability.
- [ ] 3.2 `bu-3gekd` — frontend owner `/secrets` Google card + `Google Health`
      grant CTA. Links to §Per-Account Scope Set Picker.
- [ ] 3.3 `bu-hh875` — status card + test-mode banner. Links to §Google Health
      Connector Status Card and §Test-Mode Pre-Verification Warning.
- [ ] 3.4 `bu-fodms` — e2e: owner grants Health from `/secrets`; connector
      clears `scope_missing`.
