# Design

## Context

The Google Health connector is built and, after PR #2127 (account-discovery
crash fix), runtime-healthy. It cannot ingest because no Google account has the
`googlehealth.*` scopes, and the owner has no discoverable way to grant them:
the only surface that renders the scope-set picker (`PageGoogleAccounts`) lives
inside the `/secrets` passport at `/secrets?focus=u:google` and is reachable
only by manually projecting the inventory onto a `{google_account}` companion
entity via `?identity=<uuid>`.

## Decisions

### Decision 1: Home this delta in `dashboard-google-accounts`, not `butler-secrets`

The scope-set picker and Google Health status card are already specified by the
ratified `dashboard-google-accounts` capability. The `/secrets` passport
capability (`butler-secrets`) exists only inside the in-flight
`redesign-secrets-passport` change and is not ratified, so it cannot host a
`MODIFIED` delta. Binding the route and the discoverability requirement in
`dashboard-google-accounts` keeps one coherent owner for the picker contract.
When `butler-secrets` ratifies, it SHALL reference this requirement rather than
re-specify it.

### Decision 2: Owner-default projection surfaces the primary account only

The owner-default inventory must include the primary Google account so the
picker is reachable. It must exclude non-primary accounts because their
credentials may belong to a different person; surfacing them under the owner
lens would be a credential-disclosure regression. Non-primary accounts remain
reachable only via an explicit `?identity=` lens (already supported). The
selection key is `public.google_accounts.is_primary = true AND status =
'active'`.

### Decision 3: No new auth-status surface here

The test-mode warning is already specified by `dashboard-google-accounts`
(§Test-Mode Pre-Verification Warning) using `metadata.google_health_test_mode`
and `last_token_refresh_at`. This change does not introduce a durable
`expired` / `requires_reauth` state — that systemic taxonomy is owned by
`add-connector-oauth-scope-surface`. The implementation bead for the status
card/banner (`bu-hh875`) consumes only the already-specified signals and is the
harmonization point when the systemic change lands.

## Implementation notes (for the downstream beads, non-normative)

- Backend (`bu-2kejb`): extend `secrets_v2.py` `_fetch_user_secrets`
  owner-default branch to also return secured `entity_info` for the primary
  `{google_account}` entity, and `_fetch_identity_info` to include that entity.
  Add a unit test asserting the non-primary account is excluded from the
  owner-default projection.
- Frontend (`bu-3gekd`): the existing provider mapping
  (`google_oauth_refresh` → `google`) and `PageGoogleAccounts` picker render
  automatically once the credential is present in the owner-default inventory;
  verify the `Google Health` grant CTA is wired (non-dead) to the
  `scope_set=health` start URL.

## Risks

- **Disclosure risk** if the primary-only filter is implemented incorrectly —
  mitigated by the §Multi-account leak prevention scenario and a required
  exclusion unit test in `bu-2kejb`.
- **Drift with `butler-secrets`** if that change ratifies a conflicting passport
  contract — mitigated by Decision 1's explicit reference directive.
