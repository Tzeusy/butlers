## ADDED Requirements

### Requirement: Paginated routing log endpoint
The dashboard API SHALL expose `GET /api/butlers/switchboard/routing-log` which MUST return paginated entries from the `routing_log` table. The endpoint MUST accept query parameters: `from` (ISO 8601 timestamp, inclusive lower bound on `created_at`), `to` (ISO 8601 timestamp, exclusive upper bound on `created_at`), `limit` (integer, default 50), and `offset` (integer, default 0). Results MUST be ordered by `created_at` descending. The endpoint is read-only.

#### Scenario: Retrieve routing log with default pagination
- **WHEN** a client sends `GET /api/butlers/switchboard/routing-log` with no query parameters
- **THEN** the response MUST return up to 50 routing log entries ordered by `created_at` descending, each containing `id`, `source_channel`, `source_id`, `routed_to`, `prompt_summary`, `trace_id`, `group_id`, and `created_at`

#### Scenario: Filter routing log by date range
- **WHEN** a client sends `GET /api/butlers/switchboard/routing-log?from=2025-01-01T00:00:00Z&to=2025-01-02T00:00:00Z`
- **THEN** the response MUST contain only entries whose `created_at` falls within the specified range (inclusive of `from`, exclusive of `to`)

#### Scenario: Paginate through routing log
- **WHEN** a client sends `GET /api/butlers/switchboard/routing-log?limit=10&offset=10`
- **THEN** the response MUST return the second page of 10 entries, skipping the first 10

---

### Requirement: Butler registry endpoint
The dashboard API SHALL expose `GET /api/butlers/switchboard/registry` which MUST return all entries from the `butler_registry` table as a snapshot. Each entry MUST include `name`, `endpoint_url`, `description`, `modules` (JSONB), `last_seen_at`, and `registered_at`. The endpoint is read-only.

#### Scenario: Retrieve butler registry
- **WHEN** a client sends `GET /api/butlers/switchboard/registry`
- **THEN** the response MUST be a JSON array of all registered butlers with `name`, `endpoint_url`, `description`, `modules`, `last_seen_at`, and `registered_at`

#### Scenario: Empty registry
- **WHEN** no butlers are registered in the `butler_registry` table
- **THEN** the response MUST be an empty JSON array

---

### Requirement: Routing log tab
The dashboard frontend SHALL render a routing log tab displaying a table with columns: timestamp (`created_at`), source channel, source ID, routed to (rendered as a butler badge), and prompt summary (truncated to a reasonable length). The tab MUST support pagination controls.

#### Scenario: Display routing log table
- **WHEN** a user navigates to the routing log tab
- **THEN** the page MUST display a table of routing log entries with timestamp, source channel, source ID, butler badge for routed_to, and truncated prompt summary

#### Scenario: Paginate routing log
- **WHEN** the routing log contains more entries than the page size
- **THEN** pagination controls MUST allow the user to navigate between pages

#### Scenario: Prompt summary truncation
- **WHEN** a routing log entry has a `prompt_summary` exceeding the display limit
- **THEN** the summary MUST be truncated with an ellipsis, and hovering or clicking MUST reveal the full text

---

### Requirement: Registry tab
The dashboard frontend SHALL render a registry tab displaying a table with columns: name, endpoint URL, modules list, last seen (`last_seen_at`), and registered at (`registered_at`).

#### Scenario: Display butler registry table
- **WHEN** a user navigates to the registry tab
- **THEN** the page MUST display a table listing all registered butlers with name, endpoint URL, modules rendered as a list or badges, last seen timestamp, and registered at timestamp

#### Scenario: Modules display
- **WHEN** a butler has multiple modules configured in its `modules` JSONB field
- **THEN** all module names MUST be displayed as distinct badges or list items in the modules column

#### Scenario: Empty registry display
- **WHEN** no butlers are registered
- **THEN** the registry tab MUST display an informative empty-state message
