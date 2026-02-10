# Dashboard Audit Log

Audit log for dashboard-initiated write operations. Every mutation performed through the dashboard API (trigger, schedule CRUD, state set/delete) is logged with full context for traceability and accountability.

---

## ADDED Requirements

### Requirement: Audit log storage

The dashboard API SHALL log every write operation to a `dashboard_audit_log` table. The table SHALL be created via an Alembic migration in the Switchboard database (as the dashboard's shared persistence layer).

The `dashboard_audit_log` table SHALL have the following columns:
- `id` (UUID, primary key, default gen_random_uuid())
- `timestamp` (TIMESTAMPTZ, NOT NULL, default now())
- `butler` (TEXT, NOT NULL) — the butler targeted by the operation
- `operation` (TEXT, NOT NULL) — the operation type (e.g., `trigger`, `schedule.create`, `schedule.update`, `schedule.delete`, `schedule.toggle`, `state.set`, `state.delete`)
- `user_context` (JSONB, NOT NULL) — for v1, contains `{"ip": "...", "user_agent": "..."}` extracted from the HTTP request. Future versions may include authenticated user identity.
- `request_summary` (JSONB, NOT NULL) — a summary of the request payload (e.g., `{"prompt": "Check vitals"}` for trigger, `{"key": "last_sync", "value_preview": "2026-02-..."}` for state.set). Sensitive values SHOULD be truncated or omitted.
- `result` (TEXT, NOT NULL) — `"success"` or `"error"`
- `error_message` (TEXT, nullable) — error description when `result = "error"`

Indexes:
- `idx_audit_butler_timestamp` on `(butler, timestamp DESC)`
- `idx_audit_operation_timestamp` on `(operation, timestamp DESC)`
- `idx_audit_timestamp` on `(timestamp DESC)`

#### Scenario: Trigger operation is logged

- **WHEN** a user triggers the `health` butler via `POST /api/butlers/health/trigger` with prompt "Check vitals"
- **THEN** a row MUST be inserted into `dashboard_audit_log` with `butler="health"`, `operation="trigger"`, `request_summary={"prompt": "Check vitals"}`, and `result="success"` (or `"error"` if the trigger failed)

#### Scenario: Schedule delete operation is logged

- **WHEN** a user deletes a scheduled task via `DELETE /api/butlers/general/schedules/task-123`
- **THEN** a row MUST be inserted with `butler="general"`, `operation="schedule.delete"`, `request_summary={"task_id": "task-123"}`, and `result="success"`

#### Scenario: State set operation with value truncation

- **WHEN** a user sets a state key via `PUT /api/butlers/health/state/large_data` with a 10KB JSON value
- **THEN** the `request_summary` MUST contain `{"key": "large_data", "value_preview": "..."}` where `value_preview` is truncated to 200 characters

---

### Requirement: Audit log API

The dashboard API SHALL expose `GET /api/audit-log` which returns a paginated list of audit log entries.

The endpoint SHALL accept the following query parameters:
- `butler` (string, optional) — filter by butler name
- `operation` (string, optional) — filter by operation type
- `from` (ISO 8601 timestamp, optional) — include only entries with `timestamp >= from`
- `to` (ISO 8601 timestamp, optional) — include only entries with `timestamp <= to`
- `limit` (integer, default 50) — maximum number of entries to return
- `offset` (integer, default 0) — number of entries to skip for pagination

The response SHALL be a JSON object containing:
- `items` (array) — audit log entries, each including all columns from the `dashboard_audit_log` table
- `total` (integer) — total count of matching entries (for pagination UI)

Results SHALL be ordered by `timestamp` descending.

#### Scenario: Fetch audit log with default parameters

- **WHEN** `GET /api/audit-log` is called with no query parameters
- **THEN** the API MUST return at most 50 entries ordered by `timestamp` descending
- **AND** each entry MUST include `id`, `timestamp`, `butler`, `operation`, `user_context`, `request_summary`, `result`, and `error_message`

#### Scenario: Filter audit log by butler

- **WHEN** `GET /api/audit-log?butler=health` is called
- **THEN** the API MUST return only entries where `butler` equals `"health"`

#### Scenario: Filter audit log by operation type

- **WHEN** `GET /api/audit-log?operation=trigger` is called
- **THEN** the API MUST return only entries where `operation` equals `"trigger"`

#### Scenario: Filter audit log by date range

- **WHEN** `GET /api/audit-log?from=2026-02-01T00:00:00Z&to=2026-02-07T23:59:59Z` is called
- **THEN** the API MUST return only entries with `timestamp` within the specified range

#### Scenario: No entries match filters

- **WHEN** `GET /api/audit-log?butler=nonexistent` is called
- **THEN** the API MUST return `{"items": [], "total": 0}`
- **AND** the response status MUST be 200

---

### Requirement: Audit logging middleware

All dashboard API write endpoints SHALL be wrapped with audit logging. The audit logging SHALL be implemented as a decorator or middleware applied to write endpoint handlers.

The following endpoints MUST be audit-logged:
- `POST /api/butlers/:name/trigger` — operation: `trigger`
- `POST /api/butlers/:name/tick` — operation: `tick`
- `POST /api/butlers/:name/schedules` — operation: `schedule.create`
- `PUT /api/butlers/:name/schedules/:id` — operation: `schedule.update`
- `DELETE /api/butlers/:name/schedules/:id` — operation: `schedule.delete`
- `PATCH /api/butlers/:name/schedules/:id` — operation: `schedule.toggle`
- `PUT /api/butlers/:name/state/:key` — operation: `state.set`
- `DELETE /api/butlers/:name/state/:key` — operation: `state.delete`

The middleware MUST:
1. Extract `user_context` (IP address and User-Agent) from the request before executing the handler
2. Execute the handler
3. Log the result (success or error) to the `dashboard_audit_log` table
4. NOT block the response — audit logging failures MUST be logged as warnings but MUST NOT cause the API response to fail

#### Scenario: Audit log captures user context

- **WHEN** a request to `POST /api/butlers/health/trigger` is made from IP `192.168.1.50` with User-Agent `Mozilla/5.0`
- **THEN** the audit log entry MUST have `user_context = {"ip": "192.168.1.50", "user_agent": "Mozilla/5.0"}`

#### Scenario: Audit log records error result

- **WHEN** a trigger request fails because the butler is unreachable
- **THEN** the audit log entry MUST have `result="error"` and `error_message` containing the error description

#### Scenario: Audit logging failure does not break the API

- **WHEN** the `dashboard_audit_log` table is temporarily unavailable (e.g., DB connection issue)
- **THEN** the write endpoint MUST still succeed (or fail based on its own logic)
- **AND** the audit logging failure MUST be logged as a warning in the application logs

---

### Requirement: Audit log frontend page

The frontend SHALL render an audit log page accessible from the sidebar navigation and from butler detail pages.

The audit log page MUST include:
- **Audit log table** — a paginated table displaying audit entries with columns: timestamp (formatted), butler (badge), operation (badge), user context (IP), request summary (truncated JSON), result (success/error badge), and error message (if present).
- **Filter controls** — butler selector, operation type selector, and date range picker.
- **Pagination** — standard pagination controls at the bottom.

#### Scenario: Audit log page loads with recent entries

- **WHEN** a user navigates to the audit log page
- **THEN** the page MUST display the most recent 50 audit entries in a table
- **AND** each row MUST show the timestamp, butler badge, operation type, and result badge

#### Scenario: User filters by butler and operation

- **WHEN** the user selects butler "health" and operation "trigger"
- **THEN** the table MUST update to show only trigger operations targeting the health butler

#### Scenario: Error entries are visually distinct

- **WHEN** an audit entry has `result="error"`
- **THEN** the row MUST display a red error badge and show the error message in an expandable section
