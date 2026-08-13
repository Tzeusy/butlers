# Diagnosis-First Tailscale Serve Repair Packet

> **Purpose:** A sanitized, evidence-first packet for an authorized operator
> to assess one suspected Tailscale Serve route fault without turning uncertain
> diagnosis into a broad infrastructure change.
> **Audience:** The owner-approved operator and an independent off-host verifier.
> **Boundary:** This is not a command sheet. It contains no executable host,
> network, certificate, deployment, credential, or service-lifecycle action.

## 1. Packet Boundary and Authorities

Complete the host, window, operator, verifier, and read-only authorization
fields before any live observation. Complete the mutation authorization field
before any change. A blank required value is an abort condition for its phase,
not permission to infer a value.

| Field | Required value |
|---|---|
| Target host | `[HOST]` |
| Approved maintenance window | `[APPROVED_WINDOW]` |
| Authorized operator | `[AUTHORIZED_OPERATOR]` |
| Off-host verifier | `[OFF_HOST_VERIFIER]` |
| Read-only observation authorization | `[READ_ONLY_OBSERVATION_AUTHORIZATION]` |
| Mutation authorization | `[MUTATION_AUTHORIZATION]` |
| Repository revision reviewed | `[REPOSITORY_COMMIT]` |
| Sanitized evidence location | `[SANITIZED_EVIDENCE_LOCATION]` |

This packet authorizes neither a host connection nor a repair by itself. The
authorized operator owns any live action under the approved change record; the
off-host verifier independently owns the acceptance evidence. Do not record
credentials, tokens, personal data, raw configuration, or unredacted logs in
this repository artifact or its handoff.

## 2. Repository Facts Versus Live Evidence

The following are checked-in implementation facts. They are not evidence that
any particular host is healthy, reachable, configured, or serving the current
revision.

| Checked-in fact | Repository source | It does not establish |
|---|---|---|
| The dev route names are `/butlers-dev/` and `/butlers-dev-api/api`. | `scripts/compose.sh` mode configuration | Which mode, route mapping, or port is active on `[HOST]`. |
| The production route names are `/butlers/` and `/butlers-api/api`. | `scripts/compose.sh` mode configuration | That a production stack exists on `[HOST]`. |
| The dashboard API exposes `GET /api/health` and returns `status: "ok"` when ready. | `src/butlers/api/app.py` | A live health response, readiness, or TLS outcome. |
| External HTTPS path exposure is intended to terminate through Tailscale Serve while Compose host bindings stay local. | `scripts/compose.sh`; RFC 0008 | Current Serve state, certificate identity, or any live proxy target. |

Live evidence must be time-stamped, attributable to `[AUTHORIZED_OPERATOR]` or
`[OFF_HOST_VERIFIER]`, and redacted to the minimum needed to distinguish a
route fault from an application fault. Do not promote a repository fact to a
live conclusion without that evidence.

## 3. Unauthorized Read-Only Capture

"Unauthorized" means no mutation authority. It is not permission to bypass
ordinary access control. This category begins only when
`[READ_ONLY_OBSERVATION_AUTHORIZATION]` is valid and
`[MUTATION_AUTHORIZATION]` is not issued. It must remain read-only and must
not be expanded into a configuration, service, or certificate action.

Record only these sanitized fields:

1. The authority fields from section 1, the observation timestamp, and the
   affected route label.
2. The observed outcome class for the route: reachable, unavailable,
   redirected, wrong service, or indeterminate.
3. The TLS outcome class: hostname match, trusted chain, current validity, or
   the specific failed category. Do not save certificate contents.
4. A redacted mapping summary sufficient to tell whether exactly one expected
   path is absent or misdirected. Do not save host internals or full state.
5. The off-host verifier's independently observed result when that verifier is
   already authorized to observe the route.

Stop this category when the evidence is ambiguous, when it spans more than one
route, or when it suggests an application, identity, or certificate problem.
Those outcomes do not justify a guessed repair.

## 4. Narrow Authorized Mutation

This category begins only when all section 1 fields are complete, the evidence
identifies one affected route, and the approved authorization names that route.
The authorized operator may make one reversible mapping-level correction for
that route only. The operator must preserve a sanitized before-state summary
and the exact expected after-state for the same route.

The following remain outside this category: other route prefixes, host
identity, firewall policy, certificates, application images, container or
process lifecycle, deployment state, and credential material. This packet
intentionally supplies no action syntax. A change that needs any excluded
surface must abort and receive a separately reviewed procedure.

## 5. Strict-TLS Verification

`[OFF_HOST_VERIFIER]` performs acceptance after any authorized correction. The
verifier uses the named `[HOST]` over HTTPS with strict TLS validation: the
hostname must match, the certificate chain must be trusted, and the certificate
must be currently valid. A certificate validation bypass, browser exception,
or insecure client mode is a failed verification, not a workaround.

| Route | Strict-TLS acceptance criterion |
|---|---|
| `https://[HOST]/butlers-dev/` | HTTPS completes with the expected hostname and trusted certificate, then the dashboard route returns its intended application shell without a path-routing failure. |
| `https://[HOST]/butlers-dev-api/api/health` | HTTPS completes with the same strict TLS checks, then the health endpoint returns a successful ready response with `status: "ok"`. |
| `https://[HOST]/butlers-api/api/health` | If the production API is present, HTTPS completes with the same strict TLS checks, then the health endpoint returns a successful ready response with `status: "ok"`. If it is absent by design, record `not-applicable` with the confirmed mode evidence. |

Verification records only the route, timestamp, verifier, status class, and
pass or fail result. A successful response with invalid TLS is a failure. A
valid TLS handshake with a wrong route or a non-ready health response is also a
failure.

## 6. Abort Criteria

Abort immediately and preserve the sanitized evidence when any of these is
true:

- `[HOST]`, `[APPROVED_WINDOW]`, `[AUTHORIZED_OPERATOR]`, or
  `[OFF_HOST_VERIFIER]` is missing, conflicting, expired, or cannot be
  independently identified.
- The evidence does not isolate one route and one mapping-level discrepancy.
- The baseline required for a reversible correction is absent or ambiguous.
- Strict TLS cannot be verified without a certificate validation bypass.
- The proposed change affects any route or surface outside section 4.
- The off-host verifier cannot perform the acceptance check within the approved
  window.
- The observed result points to application readiness, host identity, or
  certificate issuance rather than a single route mapping.

Do not stack speculative corrections. A failed narrow correction is evidence
for escalation, not permission for a second guess.

## 7. Rollback

Rollback is an authorized, single-route restoration of the captured
last-known-good mapping summary. It is available only while the operator can
identify the exact change made in section 4 and the same approved window and
off-host verification are still available.

After rollback, `[OFF_HOST_VERIFIER]` repeats the strict-TLS matrix in section
5 and records the result as rollback evidence. Do not broaden rollback into a
global reset, alter unrelated prefixes, or erase the failed-change evidence.
If the prior mapping cannot be established safely, abort and escalate instead.

## 8. Full Serve Reconstruction: Escalation Only

Full Serve reconstruction is never a routine repair under this packet. It is
appropriate only when the evidence cannot isolate a single mapping-level fault,
when more than one route is implicated, when the known-good baseline is absent,
or when the result indicates a host, TLS, or application problem.

It requires new, explicit authorization, a separate reviewed implementation
procedure, a new sanitized baseline, and a distinct off-host acceptance plan.
The procedure must state its rollback boundary before it begins. Until those
conditions exist, stop at diagnosis and retain the evidence for the authorized
owner's decision.

## Handoff Record

Close the packet with the following sanitized summary: read-only and mutation
authorization records, repository revision, observation window, affected route,
evidence class, narrow-change decision, strict-TLS result, rollback status if
used, and whether escalation was requested. Do not treat this repository
document as proof that a live repair occurred; the signed authorization and
off-host verification record are the live evidence.
