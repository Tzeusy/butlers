## 1. Bootstrap-only privilege and operator boundary

- [ ] 1.1 Update `scripts/init-db.sql` so its configured migration/connecting
  role receives `CREATEDB` idempotently, while every `butler_*_rw` role and
  `connector_writer` is explicitly kept `NOCREATEDB`; do not add a second
  login role, privileged credential, dashboard setting, or runtime override.
- [ ] 1.2 Add `tests/config/test_init_db_restore_drill_role_boundary.py` to
  prove the bootstrap SQL grants the intended connecting role and preserves the
  runtime/connector `NOCREATEDB` boundary, including an initially NOCREATEDB
  login role. Cite `REQ-database-security-006` in the test.
- [ ] 1.3 Update `docs/operations/backup-restore.md` to name the managed
  bootstrap prerequisite, fixed scratch lifecycle, single-executor assumption,
  no-live-database-mutation rule, and rollback boundary; remove the ad hoc
  `ALTER ROLE` and manually pre-created scratch-database workaround.
- [ ] 1.4 Run the focused bootstrap/docs checks and review the rendered command
  examples to confirm they neither disclose a credential nor direct a live role
  mutation.

## 2. Truthful restore result, retry, and attention provenance

- [ ] 2.1 Extend `src/butlers/jobs/backup_health.py` so
  `RestoreDrillResult` carries stable failure stage/code plus bounded sanitized
  detail; make a pass contingent on successful post-cleanup, and classify the
  `createdb` permission-denied path as `createdb_permission_denied` at stage
  `create` without retaining raw subprocess output.
- [ ] 2.2 Change `run_restore_drill_check()`, `get_last_restore_drill()`, and
  `_restore_drill_overdue()` in `src/butlers/jobs/backup_health.py` to persist
  and read structured audit metadata, schedule no result immediately, pass at
  seven days, and failure at 24 hours; compute the contiguous failure epoch
  from persisted result order and never parse detail text for policy.
- [ ] 2.3 Add
  `alembic/versions/core/core_179_restore_drill_attention_source.py` from this
  base's `core_178` head (renumber/rechain it if a concurrent core migration
  lands first) to admit `source="restore_drill"` in
  `public.attention_ledger`; preserve existing rows and, on downgrade, remove
  only that source before restoring the narrower constraint.
- [ ] 2.4 Extend `src/butlers/core/attention_ledger.py` and the failed-drill
  path to record a best-effort `restore_drill`/`failed` event after the audit
  result is durable, with null notification provenance and only sanitized
  structured metadata; a ledger failure must not alter audit persistence or
  retry scheduling.
- [ ] 2.5 Expand `tests/jobs/test_backup_health.py` for every classified
  failure stage/code, no-result/pass/fail/recovery cadence, failure-epoch reset,
  cleanup failure, and audit-write versus ledger-write failure independence.
  Cite `REQ-system-overview-page-006` in the new coverage.
- [ ] 2.6 Add migration and reader regression coverage in
  `tests/migrations/test_restore_drill_attention_source_migration.py`,
  `tests/core/test_attention_ledger.py`, and
  `tests/api/test_attention_ledger.py` for the new source constraint,
  `restore_drill` filter, null notification reference, and separate failed
  outcome. Cite `REQ-core-notify-026` and `REQ-core-notify-008`.

## 3. System API and dashboard truthfulness

- [ ] 3.1 Extend `RestoreDrillFacts`, `_read_restore_drill_facts()`, and
  `GET /api/system/backups` in `src/butlers/api/routers/system.py` with
  additive `failure_code`, `failure_stage`, and `failing_since` fields; return
  them only from durable drill records and return null provenance/age for pass,
  pending, and degraded states.
- [ ] 3.2 Update `frontend/src/api/types.ts` and
  `frontend/src/components/system/BackupTile.tsx` so a current failed drill
  renders an accessible `Failed since` age alongside its verdict and secondary
  code/detail, while pass, pending, and degraded states render no stale age.
- [ ] 3.3 Update `frontend/src/components/system/SystemVerdictBanner.tsx` so its
  restore-drill problem reflects the same current failure/recovery contract and
  never suggests an owner notification or a historical failure is current.
- [ ] 3.4 Extend `tests/api/test_system.py`,
  `frontend/src/components/system/BackupTile.test.tsx`, and
  `frontend/src/pages/SystemPage.test.tsx` for failed-only failure age,
  reset-after-pass, pending/degraded null behavior, and semantic failed text.
  Cite `REQ-system-overview-page-005` in the backend regression tests.

## 4. Environment-proof PostgreSQL integration evidence

- [ ] 4.1 Add `tests/integration/test_restore_drill_postgres.py`, marked
  `integration`, using the shared `postgres_container`/migration helpers and
  real PostgreSQL client binaries. Seed data, create a real compressed
  plain-SQL dump, invoke the production restore-drill command path, and assert
  restored non-system data plus final absence of the scratch database.
- [ ] 4.2 In the same integration module, create a disposable NOCREATEDB login
  role and prove the real command path reports stage `create` and code
  `createdb_permission_denied`; exercise a controlled cleanup-error path and
  assert the NOCREATEDB failure leaves no scratch database while the cleanup
  error never reports a pass. The fixture teardown must remove any scratch
  state intentionally left by the controlled cleanup-error case.
- [ ] 4.3 Give the integration module an explicit Docker/client-binary
  prerequisite guard that skips only when those real prerequisites are absent;
  do not substitute subprocess mocks, print dump content, or log credentials.
  Cite `REQ-testing-031` in the module.

## 5. Verification and operational handoff

- [ ] 5.1 Run focused Python coverage:
  `uv run pytest tests/config/test_init_db_restore_drill_role_boundary.py tests/jobs/test_backup_health.py tests/api/test_system.py tests/core/test_attention_ledger.py tests/api/test_attention_ledger.py tests/migrations/test_restore_drill_attention_source_migration.py -q`.
- [ ] 5.2 Run the real integration proof:
  `uv run pytest tests/integration/test_restore_drill_postgres.py -m integration -q`;
  record an explicit prerequisite skip if Docker or a PostgreSQL client is
  intentionally unavailable.
- [ ] 5.3 Run focused frontend coverage and production checks:
  `cd frontend && npx vitest run --configLoader runner src/components/system/BackupTile.test.tsx src/pages/SystemPage.test.tsx`, then
  `npm run lint` and `npm run build`.
- [ ] 5.4 Run `uv run ruff check src/ tests/ roster/ conftest.py`,
  `uv run ruff format --check src/ tests/ roster/ conftest.py`, and the
  repository's final `make test-qg` gate after the targeted failures are fixed.
- [ ] 5.5 Run `openspec validate restore-drill-recovery-truthfulness --strict`
  and `uv run /home/tze/.dotfiles/ai-bootstrap/skills/personal/th-projects/scripts/spec-trace-check.py . --authoring`; verify the implementation does
  not execute a live drill, alter a live role, deploy/restart services, or
  manually repair data as part of the change.
