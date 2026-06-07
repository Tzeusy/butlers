# Dashboard Google Accounts — Owner-Default Scope-Grant Discoverability Delta

This delta resolves a discoverability drift in `dashboard-google-accounts`. It
binds the existing scope-set picker to its real route (the `/secrets` passport)
and adds the requirement that the owner-default passport surfaces the primary
Google account so the picker is reachable. It is additive and route-clarifying;
it does not change the picker's grant/revoke behavior or the status-card
contract.

## MODIFIED Requirements

### Requirement: Per-Account Scope Set Picker

The scope-set picker SHALL be rendered on each connected Google account card
inside the `/secrets` credential passport's Google credential page — the
`PageGoogleAccounts` surface reached at route `/secrets?focus=u:google` — and
SHALL NOT depend on any separate "Google Accounts settings page". The picker
SHALL be reachable from the owner-default passport per the §Owner-Default Google
Account Discoverability requirement.

#### Scenario: Picker visibility

- **WHEN** the owner views a connected Google account card on
  `/secrets?focus=u:google`
- **THEN** the card SHALL display one row per available scope set (at minimum:
  `Calendar`, `Drive`, `Google Health`)
- **AND** each row SHALL show the current grant state, derived by checking
  whether `public.google_accounts.granted_scopes` contains all of that scope
  set's scope URLs
- **AND** each row SHALL render a toggle or button that initiates consent or
  revocation

#### Scenario: Granting a scope set

- **WHEN** the owner activates the toggle for `Google Health` on an account
  without those scopes
- **THEN** the UI SHALL call `GET /api/oauth/google/start?scope_set=health&force_consent=true&account_hint=<account_email>`
- **AND** on successful callback, the card SHALL re-render showing `Google
  Health` as granted
- **AND** a Google Health connector status card SHALL appear

#### Scenario: Revoking a scope set

- **WHEN** the owner deactivates the toggle for `Google Health`
- **THEN** the UI SHALL call `DELETE /api/connectors/google-health/disconnect`
- **AND** SHALL confirm via modal: `"This revokes Google Health access only.
  Calendar and Drive remain connected."`

#### Scenario: Picker reachable without a manual identity parameter

- **WHEN** the owner opens `/secrets` with no `?identity=` query parameter
- **THEN** the owner's primary Google account card (and therefore its scope-set
  picker) SHALL be reachable per §Owner-Default Google Account Discoverability
- **AND** the owner SHALL NOT need to know or supply any entity UUID to reach
  the `Google Health` grant CTA

## ADDED Requirements

### Requirement: Owner-Default Google Account Discoverability

The owner-default credential inventory SHALL surface the owner's **primary** Google account so its account card, scope-set picker, and `Google Health` connect CTA are discoverable. That is, `GET /api/secrets/inventory` with no `identity` parameter SHALL project the Google OAuth credential stored on the primary account's `{google_account}` companion entity (linked via `public.google_accounts.entity_id`) into the owner-default view — for the primary account only, never requiring an `?identity=` parameter.

#### Scenario: Primary Google account appears in the owner-default inventory

- **WHEN** `GET /api/secrets/inventory` is called with no `identity` parameter
- **AND** an active Google account exists with `public.google_accounts.is_primary = true`
- **THEN** the response SHALL include that account's Google credential (provider
  `google`) and its identity entry, even though the credential is stored on a
  `{google_account}` entity rather than the `{owner}` entity
- **AND** the `/secrets` passport SHALL render a Google account card with the
  scope-set picker for that account

#### Scenario: Multi-account leak prevention

- **WHEN** `GET /api/secrets/inventory` is called with no `identity` parameter
- **AND** one or more **non-primary** active Google accounts exist (for example
  a second, possibly different person's account)
- **THEN** the owner-default response SHALL NOT include any non-primary Google
  account's credential or identity
- **AND** a non-primary Google account's credential SHALL be retrievable only
  via an explicit `GET /api/secrets/inventory?identity=<that account's entity>`
  lens

#### Scenario: No Google account connected

- **WHEN** `GET /api/secrets/inventory` is called with no `identity` parameter
- **AND** no active Google account exists
- **THEN** the owner-default response SHALL omit any Google credential without
  error
- **AND** the `/secrets` passport SHALL still offer an "add account" / connect
  affordance so the owner can begin the Google OAuth flow
