## ADDED Requirements

### Requirement: Stale-contact claims require one authoritative producer

Before classifying a contact as overdue, the Relationship butler MUST resolve exactly one
server-attested expected-signal producer for that contact. A missing, unsupported, mixed,
conflicting, caller-asserted, or otherwise unprovable source MUST be `unmeasurable` and MUST NOT
produce a stale-contact candidate, overdue-contact result, reconnect suggestion, or scheduled
relationship-maintenance nudge.

ID: REQ-butler-relationship-001
Source: relationship-stale-contact-producer-mapping design §§1-6; RFC 0011
Scope: v1-mandatory

#### Scenario: Gmail interaction source maps to Gmail liveness

- **WHEN** an email interaction is server-attested by the passive interaction writer and the
  contact has corroborating active email identity evidence
- **THEN** its sole expected-signal producer MUST be `connector:gmail`
- **AND** no Telegram, WhatsApp, Discord, calendar, or generic connector health may authorize it

#### Scenario: Telegram user-client remains distinct from Telegram bot

- **WHEN** a Telegram user-client interaction is server-attested and the contact has a
  corroborating active `telegram:<id>` identity
- **THEN** its sole expected-signal producer MUST be `connector:telegram_user_client`
- **AND** `connector:telegram_bot` MUST NOT authorize the signal, even when that bot is healthy

#### Scenario: WhatsApp user-client uses canonical identity corroboration

- **WHEN** a WhatsApp user-client interaction is server-attested and the contact resolved through
  an exact WhatsApp JID identity or the canonical E.164 phone fallback
- **THEN** its sole expected-signal producer MUST be `connector:whatsapp_user_client`

#### Scenario: Owner-entered manual source requires server attestation

- **WHEN** an interaction is entered through a server-authenticated owner path and its origin is
  attested by the server rather than request metadata
- **THEN** its expected-signal producer MUST be `owner`

#### Scenario: Unattested manual source is unmeasurable

- **WHEN** a manual interaction's owner origin is absent or only caller-asserted
- **THEN** the interaction source MUST be `unmeasurable`

#### Scenario: Unsupported and legacy writers fail closed

- **WHEN** a stale-contact input comes from Telegram bot, Discord, a calendar-derived interaction,
  a legacy/backfilled row, an unknown writer, or an interaction with no authoritative attestation
- **THEN** the input MUST be `unmeasurable`
- **AND** the system MUST NOT infer a producer from its predicate, contact handle, row order, or any
  currently healthy connector

#### Scenario: Mixed ownership is unmeasurable

- **WHEN** the participating contact identities or latest authoritative observations resolve to
  more than one expected-signal producer
- **THEN** the contact's stale-contact signal MUST be `unmeasurable`
- **AND** the evaluator MUST NOT choose one source by recency, primary flag, row order, or health

#### Scenario: Live elapsed source follows the existing policy

- **WHEN** exactly one mapped producer is healthy and current and the contact's effective cadence
  has elapsed
- **THEN** the signal MAY be `absent` and the existing stale-contact policy MAY emit its existing
  candidate or overdue result
- **AND** the existing cadence, tier-1500 exclusion, priority, ranking, deduplication, and delivery
  rules MUST remain unchanged

#### Scenario: Dead or unreadable producer suppresses every stale-contact output

- **WHEN** a mapped connector is stale, dead/offline, unhealthy, missing, or unreadable after the
  contact's cadence has elapsed
- **THEN** the signal MUST be `unmeasurable`, never `absent`
- **AND** `insight-scan`, `contacts_overdue`, scheduled relationship maintenance, and on-demand
  reconnect planning MUST emit no owner-facing stale-contact candidate or nudge for that contact

#### Scenario: Legacy observation waits for a trustworthy baseline

- **WHEN** the latest interaction used by the cadence calculation predates server-attested producer
  provenance
- **THEN** the stale-contact signal MUST remain `unmeasurable`
- **AND** current contact identity alone MUST NOT backfill the legacy observation's producer
- **AND** a later server-attested observation MAY establish a new trustworthy baseline
