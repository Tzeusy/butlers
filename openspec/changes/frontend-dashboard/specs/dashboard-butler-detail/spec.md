# Dashboard Butler Detail

Butler detail overview tab — the default view when navigating to `/butlers/:name`. Provides a quick snapshot of the butler's identity, health, and current activity. This spec covers the core content of the overview tab; other tabs (Config, Skills, Trigger, Sessions, Schedules, State, and domain-specific tabs) are defined in their respective specs.

---

## ADDED Requirements

### Requirement: Butler identity card

The butler detail overview tab SHALL display an identity card at the top containing:
- **Butler name** — the butler's configured name from `butler.toml`
- **Description** — the first line of the butler's `MANIFESTO.md` file (the one-line value proposition)
- **Port** — the MCP server port from `butler.toml`
- **Uptime** — the time elapsed since the butler daemon started, formatted as a human-readable duration (e.g., "3d 4h 12m"). Derived from the `status()` MCP response `started_at` field. If the butler is unreachable, display "Unreachable" with a red badge.

#### Scenario: Identity card displays for a healthy butler

- **WHEN** a user navigates to `/butlers/health` and the health butler is reachable
- **THEN** the identity card MUST display the butler name "health", the first line of its MANIFESTO.md, its port number, and the uptime duration

#### Scenario: Identity card for an unreachable butler

- **WHEN** a user navigates to `/butlers/health` and the health butler's `status()` call fails
- **THEN** the identity card MUST display the butler name and config-derived fields (description, port)
- **AND** the uptime field MUST display "Unreachable" with a red visual indicator

---

### Requirement: Module health badges

The butler detail overview tab SHALL display module health badges — one colored dot per module — showing the health status of each module registered with the butler.

Health is determined from the `status()` MCP response per D13:
- **Green** — module reports `connected` or `healthy` status
- **Yellow** — module reports `degraded` status
- **Red** — module reports `error` status
- **Gray** — module status is `unknown` (e.g., status() response did not include the module)

Each badge MUST display the module name as a label next to the dot.

#### Scenario: All modules healthy

- **WHEN** the `switchboard` butler's `status()` reports modules `telegram` (healthy) and `email` (healthy)
- **THEN** the overview tab MUST display two green dots labeled "telegram" and "email"

#### Scenario: Module in error state

- **WHEN** the `switchboard` butler's `status()` reports module `telegram` with health status `error`
- **THEN** the overview tab MUST display a red dot labeled "telegram"

#### Scenario: Butler is unreachable

- **WHEN** the butler's `status()` call fails
- **THEN** the module health badges MUST display gray dots for all configured modules (from `butler.toml`) with status "unknown"

---

### Requirement: Active session indicator

The butler detail overview tab SHALL display an active session indicator showing whether the butler is currently running a CC session.

- **When active:** Display "Currently running CC session" with the elapsed time since `started_at`, updating every second. Derived from querying the butler's `sessions` table for a row where `completed_at IS NULL`.
- **When idle:** Display "Idle" with the time since the last completed session (e.g., "Last session 15 minutes ago").

#### Scenario: Butler has an active session

- **WHEN** the `health` butler's `sessions` table contains a row with `completed_at IS NULL` and `started_at = 2 minutes ago`
- **THEN** the indicator MUST display "Currently running CC session" with "2m elapsed" (updating live)

#### Scenario: Butler is idle

- **WHEN** the `health` butler has no sessions with `completed_at IS NULL` and the most recent session completed 15 minutes ago
- **THEN** the indicator MUST display "Idle — last session 15 minutes ago"

#### Scenario: Butler has no sessions at all

- **WHEN** the butler's `sessions` table is empty
- **THEN** the indicator MUST display "Idle — no sessions recorded"

---

### Requirement: Error summary

The butler detail overview tab SHALL display an error summary showing the count of failed sessions in the last 24 hours.

The error summary MUST include:
- **Failed session count** — number of sessions with `success=false` and `completed_at` within the last 24 hours
- **Link to filtered sessions** — clicking the error count MUST navigate to the sessions tab with a pre-applied filter for `success=false` and the last 24-hour date range

#### Scenario: Butler has recent failures

- **WHEN** the `health` butler has 3 failed sessions in the last 24 hours
- **THEN** the error summary MUST display "3 failed sessions in the last 24h"
- **AND** clicking it MUST navigate to the sessions tab filtered to show only those failed sessions

#### Scenario: No recent failures

- **WHEN** the butler has zero failed sessions in the last 24 hours
- **THEN** the error summary MUST display "No failures in the last 24h" with a positive visual indicator (e.g., green text or checkmark)
