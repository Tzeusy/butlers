# RFC 0023: Tracker-Host Beads Projection Exporter

**Status:** Draft — Option A planning contract approved; implementation and
activation remain owner-gated

**Date:** 2026-08-13

## Summary

Butlers will obtain the small amount of Beads data required by the Decisions
digest through a deterministic tracker-host exporter and a bounded PostgreSQL
projection. The exporter is the only new tracker reader. Normal runtime
workloads read one complete active snapshot through `BeadReadProvider`; they do
not receive Dolt reachability, Beads credentials, a `bd` command, raw exports,
or a general tracker API.

This RFC fixes the data boundary, atomicity, freshness, retention, parity, and
rollback contract. It does not authorize service installation, credential
provisioning, migration execution, network changes, deployment, consumer
cutover, or JSONL retirement.

## Context

The currently shipped decision path consumes a read-only
`.beads/issues.export.jsonl` bind mount. It deliberately treats a missing,
unreadable, or stale export as unavailable rather than showing a fabricated
empty queue. It nevertheless remains a single-host file contract: a different
runtime host cannot read it, an atomically replaced file can leave a container
on an old inode, and issues/dependencies/lint have no relational publication
boundary.

Exposing the tracker host or Dolt to application containers would violate the
least-privilege deployment model in RFC 0008. Letting each consumer parse a
raw export would duplicate policy and broaden the data surface. The selected
design places deterministic tracker access in an operator-controlled management
workload and provides a read-only, active-only PostgreSQL projection to the
existing runtime plane.

## Decision

### 1. Boundary and authority

- Beads/Dolt remains the sole authoritative tracker.
- The future exporter runs only on the tracker host in an
  operator-authorized management workload. It is not a butler, connector, LLM
  task, dashboard endpoint, or general bridge.
- The exporter reads Beads only locally, publishes only to PostgreSQL over TLS
  using a dedicated least-privilege writer identity, and has no public
  listener.
- Runtime consumers use the selected source only through `BeadReadProvider`.
  They MUST NOT receive a tracker host route, Dolt port, `bd`, tracker
  credential, or a whole `.beads` directory mount. Until separately authorized
  JSONL retirement, explicit JSONL mode may retain only the existing read-only
  `issues.export.jsonl` file mount; it is not tracker capability.
- No caller receives an arbitrary tracker query or mutation surface. The first
  and only consumer scope is the existing read-only Decisions digest.

### 2. Minimal active snapshot

The exporter includes only Beads records with status `open`, `in_progress`, or
`blocked`. It stores the following typed allowlist:

| Relation | Permitted fields |
|---|---|
| Issue | id, title, status, issue type, priority, created/updated/deadline timestamps, labels |
| Eligible decision detail | source description, validated ordered options/default, structured-detail availability and categorical reason |
| Dependency | issue id, depends-on id, type, created timestamp |
| Lint | clean/violations/unavailable state; bounded violation id, title, and category code |
| Provenance | snapshot/run ids, source digest, completion/source times, schema/producer version, bounded counts, categorical outcome/reason |

An eligible decision is an active, non-epic issue carrying the `decision`
label. Its description may be stored only for that decision row. The exporter
derives normalized decision options/default and detail-state values, then
discards source metadata.

The projection MUST NOT retain raw metadata, notes, comments, history,
attachments, raw export blobs, credentials, host paths, raw linter output, or
raw exception text. A new field requires a new approved specification and
security review; the fact that an exporter can see a field is never authority
to persist it.

### 3. Publication protocol

The core migration will create a `beads_projection` schema outside all
butler-default search paths. Its private storage has completed snapshots,
snapshot-keyed issue/dependency/lint rows, a singleton active-pointer row, and
categorical sync-run outcomes.

Before export staging or database work, the publisher holds a dedicated
PostgreSQL advisory lock. It performs the following sequence:

1. Generate/read a local staged export in tracker-host-only storage.
2. Validate record shape, unique identifiers, allowed bounds, timestamps, and
   active dependency endpoints. Normalize allowlisted fields and evaluate the
   strict decision lint.
3. In one PostgreSQL transaction, insert the candidate rows, mark the
   candidate complete, update the singleton active pointer, and record the
   success outcome.
4. On any lock, source, parse, validation, or database failure, record only a
   categorical failed run. Do not publish candidate rows or change the active
   pointer.

A reader therefore sees the preceding complete snapshot until a new complete
snapshot and its pointer are committed together. A candidate with a lint
violation remains publishable as a valid tracker snapshot, but its normalized
`violations` state is preserved. A candidate whose lint execution is
unavailable also preserves that fact; it is never represented as a clean audit.

### 4. Retention

The retention invariant is exact: retain the active completed snapshot and two
immediately prior completed snapshots. Pruning MUST never delete the snapshot
currently named by the active pointer.

Failed-run metadata is categorical and retained for 30 days. It contains no
raw tracker payload or error text. Successful snapshot provenance remains with
the retained snapshots; it is not a substitute for tracker history.

### 5. Read contract and atomicity

`BeadReadProvider` owns runtime reads and returns an immutable typed envelope:

```text
available, source, snapshot_id, completed_at, source_exported_at,
freshness, target_met, unavailable_reason, issues, dependencies, lint
```

Reader roles receive only `USAGE` on `beads_projection` and `SELECT` on
bounded active-snapshot views. They receive no direct privilege on private
tables, the active pointer, snapshot history, failed runs, sequences, or writer
functions. The writer has no privilege on application schemas.

The provider starts one `REPEATABLE READ, READ ONLY` transaction, selects the
active snapshot metadata and each active view, and verifies every returned row
has the selected snapshot id. A missing/non-singleton pointer, unavailable
view, schema mismatch, query error, or mismatched row fails closed as an
unavailable provider result. The provider MUST NOT combine data from different
snapshots and MUST NOT synthesize an empty successful snapshot.

### 6. Freshness

Snapshot age is measured from completed publication time:

| Age | Classification | Consumer behavior |
|---|---|---|
| `<= 5 minutes` | target-fresh | normal readable result |
| `> 5` and `<= 10 minutes` | fresh, target missed | readable result plus observable target miss |
| `> 10` and `<= 15 minutes` | warning | readable result plus visible warning provenance |
| `> 15 minutes` | unavailable | degraded response; never all-clear |

Missing, unreadable, or schema-mismatched data is also unavailable with a
stable categorical reason. `GET /api/decisions` retains
`decisions_available`, `unavailable_reason`, and the legacy `export_as_of`
when applicable, and adds source, snapshot-as-of, freshness, and target-met
metadata.

### 7. Preserved decision semantics

`decision_review` remains the owner of label-only decision selection,
structured-detail validation, and dependency escalation. The provider supplies
the typed active snapshot; it does not create a second classifier. A pure
calculation over the projection must match an equivalent legacy JSONL fixture
for decision order, structured-detail availability/reason, P1/deploy
escalations, and strict lint outcome.

The strict lint includes active `decision` labels and active non-epic legacy
title-marker records. Lint violations and lint unavailability retain the
existing attention behavior. No export, projection, dashboard, or scheduled
job mutates the Beads source to correct a result.

### 8. Rollout and rollback

1. Land the implementation with reader mode explicitly set to JSONL.
2. After a separate operational authorization, run the exporter in shadow mode
   for 14 full consecutive days. Each successful cycle compares JSONL and
   projection semantic output; a mismatch or unavailable source resets the
   clean-day counter and emits a bounded operator signal.
3. Only after the fourteen-day gate and separate cutover authorization, switch
   both the Switchboard jobs and dashboard to explicit projection mode.
4. Retain an explicit JSONL source selection for exactly seven calendar days
   after cutover. It is a deployment/configuration rollback, not an automatic
   in-process fallback; provenance must name the selected source.
5. JSONL mount/parser/export-materialization retirement requires a separate
   owner authorization after the rollback window. It is not implied by this
   RFC, parity success, or a green CI run.

### 9. Security and operational proof

Before activation, implementation must demonstrate all of the following against
real role/network topology:

- TLS and credential scope for the writer; no credential in source control or
  normal runtime container.
- `SET ROLE` proof that writer and reader privileges are mutually constrained.
- Atomic publication and atomic reader tests, including failure/pointer-flip
  injection.
- No normal application container tracker/Dolt egress or tracker material.
- Source freshness, warning, hard-unavailable, lint, and shadow-parity status
  surfaced with stable identifiers and no sensitive/raw payload logging.

## Rejected Alternatives

**Direct runtime `bd`/Dolt access.** Rejected because it exposes tracker
network/credentials and couples application availability to tracker latency.

**A general tracker API or MCP tool.** Rejected because it turns a bounded
governance projection into an unbounded data-exfiltration and mutation surface.

**A Dolt read replica.** Not selected absent a proven self-hosted replication,
authentication, recovery, and freshness design.

**Silent JSONL fallback.** Rejected because it hides a broken projection behind
different freshness semantics and makes operator state unprovable.

## Consequences

The system gains a multi-host read path and a coherent snapshot boundary at the
cost of a small management-plane workload, a dedicated schema/role contract,
and explicit operator responsibility. The JSONL bridge remains the current
compatibility and rollback mechanism, not a discarded implementation detail.

## References

- RFC 0006 — Database Schema and Isolation
- RFC 0007 — Dashboard and API Surface
- RFC 0008 — Deployment Network Security
- `docs/architecture/beads-runtime-data-bridge.md`
- `openspec/changes/beads-projection-exporter/`
