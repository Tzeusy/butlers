## Context

`ensure_module_default_schedule()` currently runs from module startup before
`sync_schedules()` has established which `[[butler.schedule]]` entries remain
in the active TOML configuration. It flips any same-named `source='toml'` row
to `source='db'`, preserving `enabled`; then `sync_schedules()` only disables
rows that are still TOML-sourced. The resulting sequence cannot distinguish an
active TOML override from a removed one at the recovery boundary, and it leaves
the removed row disabled after a previous TOML-removal pass.

The active memory cleanup handler deletes an episode with the predicate
`expires_at < now()`. `/api/memory/stats` already fans out per butler memory
pool and names ordinary pool failures in `meta.pools_failed`; catalog drift has
the analogous separate `meta.catalog_pools_failed` tracker. Neither surface
currently reports retained rows that the cleanup handler would delete.

This is a cross-cutting, safety-sensitive contract change. It affects a
git-backed identity/config boundary, per-schema scheduler state, the canonical
append-only audit spine, aggregate read semantics, and an owner-facing
dashboard. It must not turn a visibility repair into a historical deletion
operation.

## Goals / Non-Goals

**Goals:**

- Recover exactly one class of stale schedule state: a registered module
  default whose matching TOML-owned row was disabled after the TOML declaration
  was removed.
- Keep disabled DB-owned rows operator-owned, including the live rows that
  motivated this work; recovery must never re-enable them.
- Make the state transition and its durable audit inseparable, idempotent, and
  safe under concurrent starts.
- Make expired-but-retained episodes visible by the exact cleanup predicate,
  with complete-versus-unknown fan-out semantics and an honest Overture.
- Preserve a clean handoff boundary to the separate provenance and
  owner-authorized historical-drain slices.

**Non-Goals:**

- Deleting, expiring, quarantining, backfilling, or otherwise mutating
  historical episodes, facts, rules, generic links, or retained raw content.
- Re-enabling any `source='db'` schedule, including
  `memory_episode_cleanup` and `memory_consolidation` rows disabled by an
  operator or prior live incident.
- Introducing a background job, startup side effect, migration, or automatic
  remediation based on the new statistics.
- Defining episode evidence/provenance behavior after deletion. That belongs to
  `bu-kqnum.13.4`; no retained source may be drained before its contract and
  implementation are complete.
- Performing the switchboard historical drain. That remains the separately
  owner/ops-gated `bu-kqnum.13.5` operation, blocked by its explicit owner
  authorization (`bu-vgl57`), provenance work, safe code slices, and the
  consolidation-retention decision (`bu-tmy40` / `bu-v50gm`).

## Decisions

### D1 — Synchronize TOML before module-default recovery

The lifecycle SHALL synchronize declared TOML schedules before evaluating
module-default recovery. After that synchronization, a known module default is
eligible for recovery only when its same-named row is both `source='toml'` and
disabled. A still-declared TOML entry is handled wholly by normal TOML sync;
it remains TOML-owned and is not a recovery event.

The module default registry remains the allowlist. The scheduler does not infer
module ownership from a name prefix, arbitrary database row, or dashboard
input. Registration is then safe to insert a missing default or reclaim only a
TOML-orphaned default.

**Why this over the current pre-sync source flip:** it gives the transition a
real provenance condition and prevents audit churn for TOML entries that are
still active. It also preserves the doctrine that roster configuration is the
source of truth for live butler identity.

**Alternatives considered:**

- Keep recovery before sync and always flip TOML rows: rejected because the
  implementation cannot prove the TOML block was removed and would record a
  recovery on every boot for an active override.
- Re-enable every disabled same-named row: rejected because it overrides a
  deliberate operator disable and would revive the live `source='db'` rows.
- Add a generic `module_default` flag to every schedule row: rejected for this
  slice because the existing module registry plus source provenance supplies the
  narrow allowlist without a schema expansion or migration.

### D2 — Recover and audit in one transaction, using the transition as the idempotency key

The scheduler SHALL acquire one connection and execute the eligible transition
with a conditional `UPDATE ... RETURNING` (or equivalent single-row
serialization) inside one SQL transaction. A returned row is the sole authority
to append one canonical `public.audit_log` record. The same transaction commits
only after the audit insert succeeds.

The audit entry identifies the recovery action and schedule target, and contains
only schedule control-plane context: source transition, prior enabled state,
and the registered module/default name. It MUST NOT contain episode content,
prompt text, job arguments, or other retained payload. The implementation may
reuse `audit.append(connection, ...)`, whose existing contract supports a
caller-owned transaction.

The transition changes only `source` to `db`, `enabled` to `true`, and normal
update bookkeeping. It preserves cron, dispatch mode, job name, job args,
complexity, and `next_run_at`; it does not reset cadence or bring a historical
run forward.

**Why this over a best-effort audit:** a successful re-enable without durable
evidence is indistinguishable from an unaudited operator change, while an audit
without the re-enable fabricates recovery. The existing audit primitive already
defines this atomicity boundary.

**Alternatives considered:**

- Update then fire-and-forget a daemon audit: rejected because its swallow-on-
  failure behavior violates the required failure atomicity.
- Audit before update in separate commits: rejected because a crash can create
  evidence of a recovery that never occurred.
- Rewrite the module default payload while recovering: rejected because cadence
  and runtime arguments can be intentional DB-level customization.

### D3 — Treat expiry observation as a tri-state, not a zero-filled aggregate

`GET /api/memory/stats` SHALL compute expired-retained episode counts from the
same cleanup predicate, currently `expires_at < now()`, and shall use
`expires_at IS NOT NULL` as the per-source eligible denominator. Its observation
contains aggregate count and ratio plus per-source count, denominator, and
ratio. A complete source with at least one matching row exceeds the approved
v1 threshold of zero and is degraded; a complete source with no matching rows
is healthy. A source with no memory schema is absent, not failed.

A retention-only pool query failure is distinct from ordinary stats and catalog
drift failures. It SHALL preserve the existing successful stats fields but name
the failed sources in `meta.retention_pools_failed`. If any relevant source
fails, the fleet aggregate count and ratio are unknown (`null`), not a partial
total presented as complete; successful per-source observations may remain
visible as lower-bound evidence. The fleet retention status is `unknown` in
that case even if completed sources show zero. If all relevant sources complete,
the status is `degraded` when any source exceeds zero and `healthy` otherwise.

**Why this over reusing `pools_failed` only:** a retention query can fail while
the established episode/fact/rule statistics remain valid. A dedicated tracker
keeps those existing fields useful while preventing the new gauge from silently
converting a failed source into a healthy zero, matching the catalog-drift
precedent.

**Alternatives considered:**

- Count `expires_at <= now()` or use a new deadline expression: rejected
  because it would diverge from the cleanup handler and make the deadman report
  a different population from the data action it observes.
- Return partial aggregate totals without a state marker: rejected because an
  undercount can read as a healthy all-clear.
- Automatically invoke cleanup when the threshold is exceeded: rejected
  because visibility does not authorize deletion, and existing DB-owned
  schedules remain operator-controlled.

### D4 — Render the state and coverage as separate, named facts

`MemoryOverture` SHALL consume the new wire fields rather than infer health from
an omitted value. It renders a named retention-degraded condition for a complete
source over threshold and an incomplete/unknown condition naming every failed
retention source. It SHALL not render a healthy retention statement when the
aggregate is unknown. Existing ordinary `pools_failed` and catalog-drift
degraded notes remain independent and continue to render.

**Why this over a numeric-only KPI:** the system's reliability doctrine rejects
calm absence. A number without coverage can look like a verified zero.

### D5 — Fence provenance and the historical drain at the contract boundary

This change declares no opinion about whether a deleted episode should retain
durable evidence, show `source-expired`, or retire links. Those are provenance
semantics owned by `bu-kqnum.13.4`. It likewise does not authorize a one-shot
or ongoing historical cleanup; `bu-kqnum.13.5` must obtain explicit owner/ops
authorization, restore proof, a fixed cutoff and dry run, bounded atomic
batches, and a terminal provenance-aware notification before it changes live
data. The ordinary cleanup handler MUST NOT be reused as an unbounded backfill.

## Direct Reader and Contract Map

| Boundary | Current authority / reader | Contract added here |
|---|---|---|
| Git-backed schedules | `ButlerConfig.schedules` and `sync_schedules()` | TOML presence is determined before recovery; active TOML remains TOML-owned. |
| Module default allowlist | Memory and Chronicler default registries calling `ensure_module_default_schedule()` | Only a registry-declared default can reclaim a disabled TOML orphan. |
| Scheduler execution | `scheduled_tasks`, scheduler tick, and schedule CRUD/read surfaces | Recovery preserves executable payload and never changes a DB-owned disable. |
| Durable evidence | `public.audit_log`, `audit.append()`, `/api/audit-log` | Exactly one committed control-plane audit accompanies one recovered row. |
| Cleanup authority | `run_episode_cleanup()` | The observation uses its exact expiry predicate; the observation never calls it. |
| Aggregate API | `get_memory_stats`, `MemoryStats`, `ApiMeta`, frontend API types | New counts/ratios/status and retention-specific failed-source list are additive. |
| Owner-facing UI | `useMemoryStats()` and `MemoryOverture` | Complete degradation and unknown coverage are rendered explicitly. |
| Separate provenance/ops lanes | `bu-kqnum.13.4`, `bu-kqnum.13.5`, `bu-vgl57`, `bu-tmy40`, `bu-v50gm` | No evidence mutation, deletion, drain, or authorization is implied here. |

The per-butler `memory_stats` MCP tool and butler-detail scoped stats endpoint
remain outside this fleet aggregate/UI contract; they must not be silently used
as a substitute for the complete-or-unknown `/api/memory/stats` observation.

## Failure, Concurrency, and Idempotence Matrix

| Condition | Required result |
|---|---|
| No row for a registered default | Insert the ordinary enabled DB-owned default; this is not a reclaim audit event. |
| Active TOML declaration / TOML row | TOML synchronization owns cadence and enablement; no module recovery audit is written. |
| Removed TOML declaration, matching disabled TOML row | Atomically recover it to enabled DB ownership and append one audit entry. |
| Matching disabled DB-owned row | No mutation, no audit, no schedule re-enable. |
| Concurrent recovery attempts | At most one transition returns a row and produces an audit entry; all other attempts are no-ops. |
| Audit insert fails | Roll back the transition; the pre-transition schedule state remains visible and no recovery audit exists. |
| Process crash before commit | Neither transition nor audit is committed. |
| Process crash after commit / later restart | The row is DB-owned and enabled; future registration is a no-op and emits no duplicate audit. |
| A complete stats source has retained expired rows | Return its exact count/ratio and a degraded status; do not invoke cleanup. |
| A retention stats source fails | Name it, mark fleet retention unknown, null fleet aggregate/ratio, and retain successful per-source evidence. |
| A pool lacks a memory schema | Exclude it from retention observation; do not call it a failed source. |

## Verification Matrix

| Layer | Required evidence |
|---|---|
| Scheduler unit/integration | TOML present, TOML removed→disabled→recover, disabled DB-owned preservation, payload preservation, and second-run no-op. |
| Transaction/audit | Real PostgreSQL test that a successful reclaim has one audit row; forced audit failure leaves the original schedule unchanged; concurrent contenders yield one transition/audit. |
| API model and fan-out | Per-source and all-source complete aggregates, zero denominator, one source over threshold, retention-only query failure, and absent memory schema coverage. |
| Cross-contract | Existing degraded-envelope contract confirms `retention_pools_failed` names failures without mutating ordinary `pools_failed` or catalog fields. |
| Frontend | Types compile; Overture renders healthy, degraded, and unknown/incomplete retention states while retaining existing degraded notes. |
| Scope guard | Static/review inspection confirms no migration, drain call, schedule toggle endpoint, notification, provenance mutation, or historical data operation is introduced. |
| Spec | `openspec validate harden-memory-retention-schedule-recovery --strict` succeeds. |

## Risks / Trade-offs

- **[Risk] Lifecycle reordering changes startup assumptions.** → Keep the
  reorder limited to TOML synchronization and module-default registration;
  demonstrate that handlers are still registered before the first scheduler
  tick and that active TOML cadence continues to win.
- **[Risk] Audit access is unavailable in a partial deployment.** → Fail
  closed for recovery: no state transition commits until the canonical audit
  write succeeds; report the ordinary startup failure through existing module
  diagnostics rather than silently recovering.
- **[Risk] A large retained population produces expensive counting.** → Use
  aggregate SQL over the cleanup predicate, scoped per pool, with the existing
  fan-out pattern; do not fetch episode content or IDs.
- **[Risk] A temporary pool outage looks like clean retention.** → Keep
  aggregate values unknown and name failed sources; never zero-fill them.
- **[Risk] Owners infer that a visible deadman authorizes deletion.** → Copy,
  specs, tasks, and review gates explicitly state that it is observation-only;
  the owner-gated drain remains a separately blocked operational procedure.
- **[Trade-off] Zero is a strict v1 threshold.** → It treats every row matching
  the cleanup predicate as a violation. Any future grace window or threshold
  tuning must be an explicit policy/spec change rather than an invisible UI
  relaxation.
