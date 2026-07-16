# Beads Runtime Data Bridge

> **Status:** Proposed design — no migration, deployment, or architecture
> decision is authorized by this document.
>
> **Decision owner:** the Butlers operator / platform owner.
>
> **Purpose:** Define a hardened, multi-host path for runtime consumers to
> read a bounded projection of Beads issue data without giving application
> containers network or credential access to Beads/Dolt.

## Executive summary

Today, Beads is authoritative in a Dolt server bound to the tracker host's
loopback interface. The shipped single-host bridge exports
`.beads/issues.export.jsonl` on that host and bind-mounts only that one file,
read-only, into the `butlers-up` and dashboard API services. The current
`decision_review` consumer is deliberately honest about failure: a missing,
unreadable, or stale export is **unavailable**, not an empty decision queue.

That is a useful single-host compatibility bridge, but it is not a durable
multi-host contract. It depends on a compose-project-local file, cannot be
queried from a different host, and can freeze at an old inode when an export is
atomically replaced. It must not be "fixed" by exposing Dolt to runtime
containers or mounting `.beads/` wholesale; the latter contains tracker
credentials.

The recommended target is a small, deterministic, management-plane
**Beads projection sync service**. It reads Beads locally through `bd export`,
validates a bounded issue/dependency snapshot, and transactionally publishes a
read-only PostgreSQL projection. Runtime consumers read only the last complete
projection through a shared provider. Beads/Dolt remains the source of truth;
the projection is a cache with explicit freshness and failure semantics.

## Scope and invariants

### In scope

- Read-only runtime visibility of Beads data, beginning with the existing
  owner-decision digest and its P1/deploy blocking escalation.
- A path that works when the tracker host and Butlers runtime hosts differ.
- Explicit freshness, provenance, and degraded-mode behavior.
- A least-privilege database and network boundary suitable for the existing
  Docker/egress model.

### Out of scope

- Runtime mutation of Beads issues, dependencies, labels, or metadata.
- Replacing Beads/Dolt as the tracker source of truth.
- A generic Beads REST/MCP API for daemons, LLM sessions, or dashboard users.
- Broad tracker replication for unrelated reporting use cases.
- Deploying a service, creating credentials, changing firewall rules, or
  selecting an operational owner.

### Non-negotiable invariants

1. **Beads/Dolt stays authoritative.** PostgreSQL stores an explicitly
   labelled projection, never a second writable tracker.
2. **Runtime is read-only.** A runtime container, dashboard request, or
   prompted LLM cannot write Beads through this bridge.
3. **No tracker credentials in application containers.** In particular, never
   mount `.beads/` or `.beads-credential-key` into them.
4. **No fabricated all-clear.** An absent, malformed, partially published, or
   over-age projection reports unavailable/stale rather than `0` open
   decisions.
5. **No broad egress exception.** Normal runtime containers do not receive a
   route to Dolt or the tracker host merely to read issue data.
6. **One completed snapshot at a time.** Readers either see the previously
   completed snapshot or the next completed snapshot, never an in-progress
   mixture.

## Current evidence and problem boundary

The current design is intentionally narrow:

- `bd` talks to the shared Dolt server on the tracker host's `127.0.0.1:3307`.
  A container's loopback is not the host loopback, and the egress firewall
  blocks RFC1918, Tailscale CGNAT, link-local, and other private ranges except
  explicitly allowed hosts.
- `src/butlers/jobs/decision_review.py` reads the exported JSONL file and
  returns `available=False` for a missing, unreadable, or over-age source. It
  uses the same deterministic digest for Switchboard delivery and
  `GET /api/decisions`.
- `docker-compose.yml`, `scripts/compose.sh`, and
  `butlers.core.deploy.materialize_beads_export()` deliberately mount or
  create only `issues.export.jsonl`, never the whole tracker directory.
- The existing bridge was shipped for the single-host decision desk in
  [PR #3140](https://github.com/Tzeusy/butlers/pull/3140). Later deployment
  hardening added the dashboard mount and deploy-time export materialization;
  it still leaves a local-file contract rather than a multi-host data plane.

This preserves the security intent of RFC 0008: the application egress plane
must not gain arbitrary private-network reachability simply because it needs a
small amount of governance data. It also preserves RFC 0006's schema and role
discipline: a cross-plane data surface needs an explicit migration and grants,
not an incidental application connection to another database.

## Options considered

| Option | Benefits | Costs and failure exposure | Disposition |
|---|---|---|---|
| Keep the single-file JSONL bind mount | Already shipped; no new service; preserves host-only tracker access | Compose/worktree path coupling, stale-inode risk, every runtime host needs the same host file, no transaction/provenance boundary beyond file mtime | Keep only as the current compatibility path and a controlled rollback mode |
| API-side live tracker reader | One apparent source and no copied issue rows | Introduces a privileged tracker endpoint or a Dolt network exception into the runtime plane; ties dashboard and jobs to tracker availability/latency; creates an auth, DoS, and data-exfiltration surface | Reject |
| Direct Dolt SQL client from runtime | Queries canonical tracker data directly | Requires exposing/binding Dolt beyond host loopback, new MySQL/Dolt client/runtime surface beside the PostgreSQL stack, and a private-network allowlist exception; grants application workloads tracker read capability | Reject |
| Self-hosted Dolt read replica | Could keep a tracker-native read model and support multiple readers | The repository has no proven self-hosted replication, failover, freshness, or credential-rotation contract for this topology. It would still need a network/service boundary and an application-side Dolt client. Replica consistency and recovery must be demonstrated before selection | Prototype-only alternative; not the default recommendation |
| Immutable export in object storage | Multi-host fan-out without a tracker TCP route; immutable artifacts aid audit | Adds storage credentials, object lifecycle, reader cache invalidation, and duplicate parsing/query logic. It does not naturally provide transactional relational joins for the decision digest | Viable only if object storage becomes the approved cross-host artifact plane; otherwise not preferred |
| **Management-plane export sync to a PostgreSQL projection** | Uses the already-required Butlers PostgreSQL plane; keeps tracker access outside runtime; permits transactionally complete snapshots, typed queries, metrics, role grants, and multi-host readers | Adds a small service, a new schema/migration, sync lag, and operational ownership | **Recommended, pending owner approval** |

The Dolt-replica option is deliberately not rejected as impossible. It is
rejected as the default until a time-boxed prototype proves the exact
self-hosted replication, freshness, authentication, recovery, and access
semantics required here. A hosted-product capability or a generic SQL-server
feature is not enough evidence for this deployment.

## Recommended architecture

### Boundary and data flow

```text
Tracker / management plane                  Butlers data plane
--------------------------                  ------------------
bd + local Dolt
       |
       | local bd export; no runtime route
       v
beads-projection-sync  -- TLS, narrow DB credential -->  PostgreSQL
       |                                                  beads_projection.*
       |                                                        |
       | structured logs, metrics, sync state                  | read-only
       v                                                        v
operator / alerting                                  Switchboard + dashboard API
                                                             |
                                                             v
                                                    degraded-honest decision digest
```

`beads-projection-sync` is a deterministic management-plane process, not a
butler and not an LLM task. It may run as a host service or in a separately
isolated management workload on the tracker host; choosing that placement is
an owner decision below. Its only tracker operation is local read/export.

The initial projection should contain only data required by the decision
digest and its escalation query:

- issue identifier, title, status, type, priority, labels, timestamps, and
  native deadline fields;
- dependency edges and their timestamps/type;
- an export/projection provenance record, content digest, completion time,
  producer version, and validation result.

Descriptions, comments, arbitrary metadata, and raw export blobs are
intentionally excluded until an approved consumer needs them. This avoids
silently creating a broad governance-data replica merely because the exporter
can read it.

### Snapshot publication protocol

The proposed schema name is `beads_projection` rather than `public`. It keeps
this control-plane cache out of every butler's default search path and enables
targeted grants. Exact table and role names remain implementation details for
the approved change, but the minimum shape is:

- `sync_runs`: every attempt, its source/export timestamp, content digest,
  validation outcome, error class, and stable run id;
- `snapshots`: completed candidate snapshots and their lifecycle;
- `issues` and `dependencies`, keyed by snapshot id;
- a singleton `publication_state` that identifies the one active completed
  snapshot and records last success/last failure.

For each run, the service must:

1. Generate/read an export in management-plane-local staging storage. The
   staging file is never bind-mounted into application containers.
2. Parse and validate all records before publishing: JSON structure, unique
   issue ids, known dependency endpoints, timestamp parseability, bounded
   record sizes, and the fields required by the selected consumers.
3. Insert the run and its candidate rows in PostgreSQL, then atomically mark
   the snapshot current in the same transaction. A crash or database error
   leaves the previously completed snapshot current.
4. Retain a bounded number of prior completed snapshots and failed-run
   metadata for diagnosis and rollback; the retention period is an owner
   decision.

The source does not currently provide a documented, portable export sequence
number. The service should store a content digest and observed export time, but
it must **not** claim strict source monotonicity until a prototype identifies a
reliable Dolt/`bd` watermark. Until then, an apparent rollback or unexpectedly
empty result is an alerted validation condition, not a silently accepted new
truth.

### Reader contract

A single typed provider (for example, a future
`butlers.core.beads_projection` module) owns projection reads and freshness
classification. `decision_review.py` keeps ownership of decision-label
detection and escalation rules; the provider supplies a complete issue/edge
snapshot rather than letting each caller parse JSONL or query tables directly.

Every result must carry at least:

- `available`: whether a complete snapshot exists and is within the configured
  hard freshness limit;
- `source`: `beads_projection` or the explicitly selected legacy mode during
  rollout;
- `as_of`: completed snapshot time and source export time when known;
- `age`: reader-observed projection age;
- `unavailable_reason`: a stable reason such as `projection_missing`,
  `projection_stale`, `projection_read_error`, or `projection_schema_mismatch`.

`GET /api/decisions` and the Switchboard scheduled jobs must use this same
provider. A healthy empty snapshot can produce a genuine all-clear; an
unhealthy source cannot. After cutover, there should be no silent automatic
fallback from projection to JSONL: an automatic fallback can hide a broken
control plane behind different freshness semantics. Migration mode may select
one source explicitly and report it in status/telemetry.

### Access and network model

- The sync process receives a dedicated PostgreSQL writer identity with access
  only to the projection schema and its required sequences/functions. It does
  not receive Butlers runtime secrets or broad application-schema privileges.
- Projection tables grant `USAGE`/`SELECT` only to the exact roles used by
  Switchboard and dashboard API reads. Do not assume existing blanket
  `public` privileges are a safe authorization mechanism; the approved
  migration must verify the live role/grant model and explicitly revoke
  unnecessary access.
- Runtime containers receive no Dolt port, `bd` credential, `bd` write tool,
  or `.beads` mount. Their only new dependency is the existing PostgreSQL
  endpoint they already need.
- If the sync process uses a networked PostgreSQL endpoint, it uses TLS and a
  narrowly provisioned credential. If it is containerized, its egress policy
  admits only that endpoint; it never adds the tracker/Dolt host to the normal
  application egress allowlist.
- No dashboard endpoint exposes arbitrary raw projection queries. The first
  surface remains the existing bounded decision digest.

## Threat model

| Threat | Required protection | Residual / operator signal |
|---|---|---|
| Compromised runtime container or prompted LLM | No tracker route, no `bd` credential, no raw `.beads` mount, and projection grants are read-only | It may read only the bounded data its assigned runtime role can query; unexpected query/permission failures are logged and alerted |
| Compromised sync process | Separate service identity, least-privilege PostgreSQL writer, dedicated host/workload boundary, no application secrets, and local-only tracker access | The process can read tracker export data and write its projection; audit each run, rotate its credential, and treat host compromise as a management-plane incident |
| Network interception or unintended lateral access | TLS/authenticated PostgreSQL connection, minimal egress allowlist, no new Dolt listener exposed to app networks | Firewall/configuration drift must be checked in deployment validation |
| Malformed, oversized, or adversarial export record | Strict parser/schema validation, bounded fields, no shell interpolation from record content, and no publishing on validation failure | Failed run is visible; last complete snapshot remains active |
| Partial write, crash, or two writers | One-writer lease/advisory lock plus transactional candidate-and-pointer publication | Readers retain the previous complete snapshot; duplicate-writer detection is an alert |
| Stale, rolled-back, or unexpectedly empty data | Source/projection timestamps, digest recording, warning and hard TTLs, comparison against prior counts, and explicit rollback validation | Consumers become unavailable at hard TTL; stale data is never an all-clear or escalation trigger |
| Unnecessary sensitive tracker data in the runtime plane | Minimal initial field set, no raw export blob, retention policy, and an approved change for each added field | Data-scope review is required before description/comment/metadata replication |
| Projection database unavailable | Reader returns degraded availability; jobs do not send conclusions from unknown data | Dashboard and attention paths name the source failure rather than showing zero decisions |

## Ownership and failure semantics

| Boundary | Owner | Normal responsibility | Failure behavior |
|---|---|---|---|
| Beads/Dolt and `bd` | Tracker/Beads operator | Authoritative issue state and local export capability | No new snapshot; bridge reports source failure without changing tracker state |
| Projection sync | Platform/operator | Export, validate, publish, retain history, emit health | Keep last complete snapshot; record a failed run and retry with bounded backoff |
| `beads_projection` schema | Core migration owner | Tables, constraints, targeted roles/grants, retention job | Schema/version mismatch fails closed before a snapshot is published |
| Shared reader provider | Core/Switchboard owner | Freshness classification and provenance envelope | Returns unavailable, never a synthetic empty snapshot |
| Decision classification/escalation | Switchboard owner | Existing deterministic label and dependency logic | Does not deliver a digest/escalation based on an unavailable or over-age source |
| Dashboard `/api/decisions` | Dashboard API owner | Render the same provider result and degraded envelope | Names the unavailable reason; does not show a calm all-clear |
| Alerting and runbook | Platform/operator | Detect repeated sync failure, TTL breach, writer contention, and permission drift | Creates a named operational incident; no automatic tracker mutation |

The following failure rules are mandatory for the implementation change:

1. An export, parse, or validation failure publishes nothing and leaves the
   active pointer unchanged.
2. A PostgreSQL transaction failure publishes nothing; retrying must be safe.
3. A failed reader lookup or a snapshot older than the hard TTL becomes
   unavailable even if a prior snapshot is still retained for diagnosis.
4. A suspicious empty or older-than-current candidate is not treated as a
   normal all-clear until the validated source-watermark policy says it is
   safe. It generates an operator-visible signal.
5. A consumer must not use an unavailable snapshot to send a weekly "no
   decisions" message or an escalation conclusion.

## Migration and operational plan

This is an ordered proposal, not an approved work plan.

1. **Record the architecture decision.** Confirm the owner decisions below.
   Add or amend an RFC for the control-plane boundary; amend RFC 0006 for the
   projection schema/role contract and RFC 0008 for any new management-plane
   network rule. Reconcile the executable compose/firewall configuration with
   RFC wording as part of that same change rather than relying on either one
   silently.
2. **Specify the consumer contract.** Create an OpenSpec change covering the
   provider envelope, freshness semantics, decision-digest parity, dashboard
   metadata, and migration acceptance criteria. Do not make the table layout
   the public API.
3. **Add the database boundary.** A core migration creates the dedicated
   schema, completed-snapshot protocol, indexes, constraints, targeted grants,
   and telemetry/status surface. It must work against a fresh/core-only
   database as well as the deployed one.
4. **Build the sync process in shadow mode.** Run it on the selected
   management plane, publish candidates, and compare its decision digest with
   the exact current `bd export` output. Keep runtime readers on the explicitly
   selected legacy source while parity, failure injection, freshness, and role
   tests prove out.
5. **Cut consumers over deliberately.** Switch both Switchboard and dashboard
   through the shared provider under an explicit deployment setting. Expose
   source, as-of, and unavailable reason in existing status surfaces. Do not
   silently fall back across sources.
6. **Prove the hardened multi-host topology.** Run a reader on a host that has
   no tracker file or Dolt route; verify it can read only PostgreSQL. Verify
   the normal application egress firewall still cannot reach the tracker/Dolt
   address and that the sync identity cannot access unrelated application
   schemas.
7. **Retire the local mount only after a soak period.** Keep the JSONL route as
   a documented rollback mode for a bounded, owner-approved period. Remove
   compose mounts, deploy-time materialization, and legacy parser branches
   together once the new source has met the agreed SLO.

### Proposed validation gates

- Parser fixtures: valid data, malformed JSON, duplicate ids, unknown
  dependency endpoints, timestamp errors, oversized fields, and an empty
  source.
- PostgreSQL integration tests: one complete snapshot is visible; a crash or
  rejected candidate never replaces it; retention and idempotent retry work.
- Role tests using the actual `SET ROLE` model: reader roles can select only
  their allowed projection surface; the sync role cannot read/write unrelated
  schemas; runtime roles cannot write the projection.
- Digest parity tests: current JSONL and projection input yield the same
  decision order and escalation result for shared fixtures.
- Freshness/failure tests: missing, stale, schema-mismatched, and read-error
  projection results propagate as degraded envelopes rather than empty queues.
- Deployment test: no application container mount or egress path reaches
  Beads/Dolt; only the chosen management-plane process has tracker access.
- Operational drill: stop the sync process, corrupt a candidate, revoke its
  database grant, and restore it; each branch must produce a named status and
  leave the last valid snapshot intact.

## Open owner decisions

These decisions are intentionally unresolved. Approving this document does
not choose them implicitly.

1. **Management-plane placement:** host `systemd` service, an isolated
   management container, or another operator-owned runner. The recommendation
   is a tracker-host service/workload separate from the application runtime.
2. **Freshness contract:** proposed starting point is a five-minute target,
   warning before the hard limit, and a 15-minute hard unavailable TTL. The
   owner must set the actual SLO and decide whether an unavailable weekly
   digest creates a notification, a dashboard-only alert, or both.
3. **Source method:** use `bd export` polling initially, or fund a Dolt
   replica prototype. The recommendation is export polling until a replica
   prototype proves the required self-hosted contract.
4. **Projection scope and retention:** exact fields, whether any description
   or arbitrary metadata may cross the boundary, number/age of retained
   snapshots, and access-audit retention.
5. **Credential and role operator:** who provisions/rotates the projection
   writer credential, and which exact dashboard/Switchboard database roles
   receive read access.
6. **Cutover and rollback policy:** soak duration, source-selection mechanism,
   and the criterion for removing JSONL mounts and legacy code.
7. **Operational ownership:** who responds to a stale projection, how quickly,
   and which alert channel is authoritative when the decision desk's source is
   unavailable.

## References

- `src/butlers/jobs/decision_review.py` — current deterministic JSONL reader,
  decision classification, escalation rules, and degraded-mode contract.
- `src/butlers/core/deploy.py` and `scripts/compose.sh` — current best-effort
  export materialization before compose mounts.
- `docker-compose.yml` and `scripts/egress-firewall.sh` — current runtime
  mount and private-network egress boundary.
- [RFC 0006: Database Schema and Isolation](../../about/legends-and-lore/rfcs/0006-database-schema-and-isolation.md)
  — schema, role, migration, and cross-boundary requirements.
- [RFC 0008: Deployment Network Security](../../about/legends-and-lore/rfcs/0008-deployment-network-security.md)
  — least-privilege deployment and egress requirements.
- `openspec/changes/owner-decision-desk-decisions-lane/` — decision-desk
  degraded-envelope and digest-consumer contract.
