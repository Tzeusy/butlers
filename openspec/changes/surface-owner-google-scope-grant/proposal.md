## Why

The `dashboard-google-accounts` capability already mandates a per-account
scope-set picker (to grant `Google Health`) and a Google Health status card.
But the spec describes them as living on an abstract "Google Accounts settings
page" that does not exist, and the implemented surface — `PageGoogleAccounts`
inside the `/secrets` credential passport (route `/secrets?focus=u:google`) —
only renders when the inventory is projected onto a `{google_account}` entity
via a manual `?identity=<uuid>` URL parameter.

The owner-default `/secrets` view (no `?identity=`) projects the `{owner}`
entity, which holds **no** Google credential: Google OAuth refresh tokens are
stored on separate companion entities with role `{google_account}` (one per
Google account), linked via `public.google_accounts.entity_id`. The result is a
**discoverability dead-end** — there is no path for the owner to reach the
scope-set picker, and therefore no way to grant the `Google Health` scopes that
the connector requires. This is the live blocker behind a connector that is
otherwise built and (after PR #2127) runtime-healthy.

A naive fix — surfacing every Google account under the owner view — would leak
the refresh-token credential of **non-primary** accounts (e.g. a second,
possibly different person's account) into the owner's passport. The contract
must therefore be explicit that the owner-default projection surfaces only the
**primary** account.

See:

- `openspec/specs/dashboard-google-accounts/spec.md` — §Per-Account Scope Set
  Picker and §Google Health Connector Status Card mandate the surfaces but bind
  them to no concrete route.
- `src/butlers/api/routers/secrets_v2.py` `_fetch_user_secrets` — owner-default
  branch joins `entity_info` to `entities WHERE 'owner' = ANY(roles)`, so
  `{google_account}` entities are never returned.
- `src/butlers/google_account_registry.py` — companion entity created with role
  `{google_account}`, linked via `public.google_accounts.entity_id`.
- `frontend/src/components/secrets/passport/pages.tsx` — `PageGoogleAccounts`
  renders inside `PageUser` at `/secrets?focus=u:google`.

## What Changes

This change is **spec-only**. It amends the `dashboard-google-accounts`
capability to:

1. Bind the scope-set picker (and the `Google Health` grant CTA) to the real
   route: the `/secrets` passport's Google credential page
   (`/secrets?focus=u:google`), not an abstract settings page.
2. Add a new requirement that the **owner-default** `/secrets` inventory SHALL
   surface the owner's **primary** Google account, so the picker / connect CTA
   is reachable without a manual `?identity=` parameter.
3. Add a normative **multi-account leak-prevention** scenario: non-primary
   Google accounts SHALL appear only under an explicit `?identity=<entity>`
   lens, never in the owner-default view.

It does not implement the change. Implementation is tracked in beads under epic
`bu-lmrzg` (backend projection `bu-2kejb`, frontend `bu-3gekd`, status/banner
`bu-hh875`, e2e `bu-fodms`), each of which links to a requirement section here.

## Scope Boundary

The systemic auth-status / reauth taxonomy (`ok | degraded | expired |
rotation-needed | unsupported | unconfigured`) and the durable reauth CTA are
owned by the in-flight `add-connector-oauth-scope-surface` change. This change
neither defines nor duplicates that enum; the test-mode warning surfaced here
relies only on the already-specified `metadata.google_health_test_mode` flag and
`last_token_refresh_at`, and is the harmonization point when that capability
ships.
