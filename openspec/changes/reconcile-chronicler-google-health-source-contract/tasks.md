## 1. Contract reconciliation

- [x] 1.1 Amend RFC 0014's Health source table and non-goal boundary to record
  the shipped read-only `health.facts` projections and the absent connector
  workout ingest.
- [x] 1.2 Add matching OpenSpec deltas for Chronicler, source compatibility,
  and the Google Health connector without changing runtime behavior.

## 2. Verification and handoff

- [x] 2.1 Validate the change strictly, inspect active-delta overwrite safety,
  and run the source-contract regression tests that prove the documented
  registry, adapter, connector-resource, and wellness-ingest boundaries.
- [x] 2.2 Review the documentation diff for scope containment: no ACL,
  migration, connector, credential, deployment, or PR #3897 change.
