# Dashboard Schedules

Schedule management UI and API for the Butlers dashboard. Provides read access to each butler's `scheduled_tasks` table via direct DB queries and write operations (create, update, delete, toggle) routed through MCP tool calls to the butler daemon (per the dual data-access pattern in D1 and the write-through-MCP constraint in D11).

Each butler's database contains a `scheduled_tasks` table with columns: `id` (UUID PK), `name` (TEXT NOT NULL UNIQUE), `cron` (TEXT NOT NULL), `prompt` (TEXT NOT NULL), `source` (TEXT NOT NULL DEFAULT 'toml', values: 'toml' or 'runtime'), `enabled` (BOOLEAN NOT NULL DEFAULT true), `last_run_at` (TIMESTAMPTZ), `last_result` (TEXT), `next_run_at` (TIMESTAMPTZ), `created_at` (TIMESTAMPTZ). All write operations go through MCP tools (`schedule_create`, `schedule_update`, `schedule_delete`) on the butler daemon -- the dashboard API never writes directly to butler databases.

## ADDED Requirements

### Requirement: List schedules API

The dashboard API SHALL expose `GET /api/butlers/:name/schedules` which reads all rows from the named butler's `scheduled_tasks` table via a direct database query.

The response SHALL be a JSON array of schedule objects ordered by `name` ascending. Each schedule object MUST include: `id`, `name`, `cron`, `cron_description` (a human-readable description of the cron expression, e.g., "Every day at 9:00 AM"), `next_run_at` (ISO 8601 timestamp or null), `next_run_human` (a human-readable relative time string, e.g., "in 3 hours", or null if `next_run_at` is null), `source`, `enabled`, `last_run_at` (ISO 8601 timestamp or null), and `last_result` (string or null).

The `cron_description` field SHALL be computed server-side from the `cron` expression using a library such as `cron-descriptor` or equivalent. The `next_run_human` field SHALL be computed server-side as the relative time from now to `next_run_at`.

#### Scenario: Fetch all schedules for a butler

- **WHEN** `GET /api/butlers/health/schedules` is called and the `health` butler's `scheduled_tasks` table contains three tasks
- **THEN** the API MUST return HTTP 200 with a JSON array of three schedule objects
- **AND** each object MUST include `id`, `name`, `cron`, `cron_description`, `next_run_at`, `next_run_human`, `source`, `enabled`, `last_run_at`, and `last_result`
- **AND** the array MUST be ordered by `name` ascending

#### Scenario: Cron description is human-readable

- **WHEN** a schedule has `cron = '0 9 * * *'`
- **THEN** the `cron_description` field MUST contain a human-readable string such as "Every day at 9:00 AM"

#### Scenario: Next run human-readable relative time

- **WHEN** a schedule has `next_run_at = '2026-02-10T15:00:00Z'` and the current time is `2026-02-10T12:00:00Z`
- **THEN** the `next_run_human` field MUST contain a relative time string such as "in 3 hours"

#### Scenario: Disabled schedule has null next run fields

- **WHEN** a schedule has `enabled = false` and `next_run_at = null`
- **THEN** the `next_run_at` field MUST be null
- **AND** the `next_run_human` field MUST be null

#### Scenario: Butler has no schedules

- **WHEN** `GET /api/butlers/general/schedules` is called and the `general` butler's `scheduled_tasks` table is empty
- **THEN** the API MUST return HTTP 200 with an empty JSON array

#### Scenario: Butler does not exist

- **WHEN** `GET /api/butlers/nonexistent/schedules` is called and no butler named `"nonexistent"` is registered
- **THEN** the API MUST return HTTP 404 with the standard error response `{"error": {"code": "BUTLER_NOT_FOUND", "message": "Butler 'nonexistent' not found", "butler": "nonexistent"}}`

---

### Requirement: Create schedule API

The dashboard API SHALL expose `POST /api/butlers/:name/schedules` which creates a new schedule by calling the `schedule_create` MCP tool on the named butler's daemon.

The request body MUST be a JSON object containing:
- `name` (string, required) -- the unique name for the schedule
- `cron` (string, required) -- a valid five-field cron expression
- `prompt` (string, required) -- the prompt text to dispatch when the schedule fires

The API SHALL validate that all three fields are present and non-empty before calling the MCP tool. If validation fails, the API MUST return HTTP 422 with a `VALIDATION_ERROR` response.

On success, the API SHALL return HTTP 201 with the created schedule object (matching the same shape as the list endpoint response).

#### Scenario: Successfully create a new schedule

- **WHEN** `POST /api/butlers/health/schedules` is called with body `{"name": "nightly-check", "cron": "0 2 * * *", "prompt": "Run nightly health check"}`
- **AND** the `health` butler daemon is reachable
- **THEN** the API MUST call the `schedule_create` MCP tool on the `health` butler with the provided `name`, `cron`, and `prompt`
- **AND** the API MUST return HTTP 201 with the created schedule object including the assigned `id`, `source` set to `"runtime"`, `enabled` set to `true`, and a computed `cron_description`

#### Scenario: Missing required field returns validation error

- **WHEN** `POST /api/butlers/health/schedules` is called with body `{"name": "test", "cron": "0 2 * * *"}` (missing `prompt`)
- **THEN** the API MUST return HTTP 422 with `{"error": {"code": "VALIDATION_ERROR", "message": "Field 'prompt' is required", "butler": null}}`

#### Scenario: Empty name returns validation error

- **WHEN** `POST /api/butlers/health/schedules` is called with body `{"name": "", "cron": "0 2 * * *", "prompt": "test"}`
- **THEN** the API MUST return HTTP 422 with a `VALIDATION_ERROR` response indicating the name must be non-empty

#### Scenario: Invalid cron expression returns error from MCP tool

- **WHEN** `POST /api/butlers/health/schedules` is called with body `{"name": "test", "cron": "not-a-cron", "prompt": "test"}`
- **AND** the `schedule_create` MCP tool rejects the cron expression as invalid
- **THEN** the API MUST return HTTP 400 with an error message indicating the cron expression is invalid

#### Scenario: Duplicate schedule name returns error from MCP tool

- **WHEN** `POST /api/butlers/health/schedules` is called with `name = "daily-review"`
- **AND** a schedule with that name already exists in the butler's database
- **THEN** the API MUST return HTTP 409 with an error message indicating the schedule name is already in use

#### Scenario: Butler daemon unreachable returns 502

- **WHEN** `POST /api/butlers/health/schedules` is called with a valid body
- **AND** the `health` butler daemon is not running
- **THEN** the API MUST return HTTP 502 with `{"error": {"code": "BUTLER_UNREACHABLE", "message": "Butler 'health' is not reachable", "butler": "health"}}`

---

### Requirement: Update schedule API

The dashboard API SHALL expose `PUT /api/butlers/:name/schedules/:id` which updates an existing schedule by calling the `schedule_update` MCP tool on the named butler's daemon.

The request body MUST be a JSON object containing one or more of the following optional fields:
- `name` (string, optional) -- updated schedule name
- `cron` (string, optional) -- updated cron expression
- `prompt` (string, optional) -- updated prompt text

At least one field MUST be provided. If the body is empty or contains no recognized fields, the API MUST return HTTP 422 with a `VALIDATION_ERROR` response.

On success, the API SHALL return HTTP 200 with the updated schedule object.

#### Scenario: Update cron expression for a schedule

- **WHEN** `PUT /api/butlers/health/schedules/abc-123` is called with body `{"cron": "30 6 * * *"}`
- **AND** the `health` butler daemon is reachable
- **THEN** the API MUST call the `schedule_update` MCP tool on the `health` butler with `id = "abc-123"` and `cron = "30 6 * * *"`
- **AND** the API MUST return HTTP 200 with the updated schedule object reflecting the new cron expression and recomputed `cron_description` and `next_run_at`

#### Scenario: Update multiple fields at once

- **WHEN** `PUT /api/butlers/health/schedules/abc-123` is called with body `{"name": "new-name", "prompt": "Updated prompt text"}`
- **THEN** the API MUST call the `schedule_update` MCP tool with both the new `name` and `prompt`
- **AND** the API MUST return HTTP 200 with the updated schedule object

#### Scenario: Empty body returns validation error

- **WHEN** `PUT /api/butlers/health/schedules/abc-123` is called with body `{}`
- **THEN** the API MUST return HTTP 422 with a `VALIDATION_ERROR` response indicating at least one field must be provided

#### Scenario: Schedule not found returns 404

- **WHEN** `PUT /api/butlers/health/schedules/nonexistent-uuid` is called with a valid body
- **AND** the `schedule_update` MCP tool returns a not-found error
- **THEN** the API MUST return HTTP 404 with an error message indicating the schedule was not found

#### Scenario: Butler daemon unreachable returns 502

- **WHEN** `PUT /api/butlers/health/schedules/abc-123` is called
- **AND** the `health` butler daemon is not running
- **THEN** the API MUST return HTTP 502 with a `BUTLER_UNREACHABLE` error response

---

### Requirement: Delete schedule API

The dashboard API SHALL expose `DELETE /api/butlers/:name/schedules/:id` which deletes an existing schedule by calling the `schedule_delete` MCP tool on the named butler's daemon.

The API SHALL NOT perform confirmation -- confirmation is the responsibility of the frontend. The API simply forwards the delete request to the MCP tool.

On success, the API SHALL return HTTP 204 with no body.

#### Scenario: Successfully delete a runtime schedule

- **WHEN** `DELETE /api/butlers/health/schedules/abc-123` is called
- **AND** the schedule with `id = "abc-123"` has `source = 'runtime'`
- **AND** the `health` butler daemon is reachable
- **THEN** the API MUST call the `schedule_delete` MCP tool on the `health` butler with `id = "abc-123"`
- **AND** the API MUST return HTTP 204 with no body

#### Scenario: Attempt to delete a TOML-source schedule returns error

- **WHEN** `DELETE /api/butlers/health/schedules/abc-123` is called
- **AND** the schedule with `id = "abc-123"` has `source = 'toml'`
- **AND** the `schedule_delete` MCP tool rejects the request because TOML-source tasks cannot be deleted
- **THEN** the API MUST return HTTP 400 with an error message indicating that TOML-source schedules cannot be deleted and can only be disabled

#### Scenario: Schedule not found returns 404

- **WHEN** `DELETE /api/butlers/health/schedules/nonexistent-uuid` is called
- **AND** the `schedule_delete` MCP tool returns a not-found error
- **THEN** the API MUST return HTTP 404 with an error message indicating the schedule was not found

#### Scenario: Butler daemon unreachable returns 502

- **WHEN** `DELETE /api/butlers/health/schedules/abc-123` is called
- **AND** the `health` butler daemon is not running
- **THEN** the API MUST return HTTP 502 with a `BUTLER_UNREACHABLE` error response

---

### Requirement: Toggle schedule enabled/disabled API

The dashboard API SHALL expose `PATCH /api/butlers/:name/schedules/:id/toggle` which toggles a schedule's `enabled` state by calling the `schedule_update` MCP tool on the named butler's daemon.

The endpoint SHALL read the current `enabled` state from the butler's database, invert it, and pass the new value to the `schedule_update` MCP tool. No request body is required.

On success, the API SHALL return HTTP 200 with the updated schedule object reflecting the new `enabled` state.

#### Scenario: Toggle an enabled schedule to disabled

- **WHEN** `PATCH /api/butlers/health/schedules/abc-123/toggle` is called
- **AND** the schedule with `id = "abc-123"` currently has `enabled = true`
- **THEN** the API MUST read the current state, determine the new value is `false`, and call `schedule_update` with `id = "abc-123"` and `enabled = false`
- **AND** the API MUST return HTTP 200 with the updated schedule object having `enabled = false` and `next_run_at = null`

#### Scenario: Toggle a disabled schedule to enabled

- **WHEN** `PATCH /api/butlers/health/schedules/abc-123/toggle` is called
- **AND** the schedule with `id = "abc-123"` currently has `enabled = false`
- **THEN** the API MUST call `schedule_update` with `id = "abc-123"` and `enabled = true`
- **AND** the API MUST return HTTP 200 with the updated schedule object having `enabled = true` and a recomputed `next_run_at`

#### Scenario: Schedule not found returns 404

- **WHEN** `PATCH /api/butlers/health/schedules/nonexistent-uuid/toggle` is called
- **AND** no schedule with that ID exists in the butler's database
- **THEN** the API MUST return HTTP 404 with an error message indicating the schedule was not found

#### Scenario: Butler daemon unreachable returns 502

- **WHEN** `PATCH /api/butlers/health/schedules/abc-123/toggle` is called
- **AND** the `health` butler daemon is not running
- **THEN** the API MUST return HTTP 502 with a `BUTLER_UNREACHABLE` error response

---

### Requirement: Schedules tab with data table

The frontend SHALL render a schedules tab within each butler's detail page (accessible via `/butlers/:name?tab=schedules`) displaying a data table of all scheduled tasks for that butler.

The table SHALL display the following columns:
- **Name** -- the schedule's `name`, displayed as a clickable link or text that opens the edit modal
- **Cron** -- the `cron` expression displayed in monospace font, with the `cron_description` (human-readable) shown as secondary text or tooltip beneath/beside it
- **Next run** -- the `next_run_human` relative time string (e.g., "in 3 hours"), or a dash if the schedule is disabled. The full `next_run_at` timestamp SHALL be shown in a tooltip on hover.
- **Source** -- a badge indicating `"toml"` (styled with a neutral/muted color) or `"runtime"` (styled with an accent color)
- **Enabled** -- a toggle switch reflecting the current `enabled` state. Clicking the toggle SHALL call the toggle API endpoint.
- **Last run** -- the `last_run_at` timestamp formatted as a human-readable relative time (e.g., "2 hours ago"), or a dash if the schedule has never run
- **Last result** -- a badge indicating the outcome: "success" (green), "error" (red), or a dash if the schedule has never run. The full `last_result` text SHALL be available via tooltip or popover on hover/click.
- **Actions** -- a "Run now" button per row that triggers an immediate execution of the schedule's prompt

The table SHALL fetch data from `GET /api/butlers/:name/schedules` using TanStack Query. The query key SHALL include the butler name so that switching butlers refetches automatically.

#### Scenario: Schedules tab displays all schedules in a table

- **WHEN** a user navigates to `/butlers/health?tab=schedules`
- **AND** the `health` butler has three scheduled tasks
- **THEN** the schedules tab MUST display a data table with three rows
- **AND** each row MUST display the name, cron expression with human-readable description, next run, source badge, enabled toggle, last run, last result badge, and a "Run now" button

#### Scenario: Cron column shows expression and description

- **WHEN** a schedule has `cron = '0 9 * * *'` and `cron_description = 'Every day at 9:00 AM'`
- **THEN** the Cron column MUST display `0 9 * * *` in monospace font
- **AND** "Every day at 9:00 AM" MUST be visible as secondary text or tooltip

#### Scenario: Source badge distinguishes toml and runtime

- **WHEN** the table contains one schedule with `source = 'toml'` and one with `source = 'runtime'`
- **THEN** the toml schedule MUST display a neutral-styled badge reading "toml"
- **AND** the runtime schedule MUST display an accent-styled badge reading "runtime"

#### Scenario: Enabled toggle reflects current state

- **WHEN** a schedule has `enabled = true`
- **THEN** the toggle switch in the Enabled column MUST be in the "on" position
- **AND** when a schedule has `enabled = false`, the toggle MUST be in the "off" position

#### Scenario: Clicking enabled toggle calls toggle API

- **WHEN** a user clicks the enabled toggle for a schedule with `id = "abc-123"` on the `health` butler
- **THEN** the frontend MUST call `PATCH /api/butlers/health/schedules/abc-123/toggle`
- **AND** on success, the table row MUST update to reflect the new `enabled` state without a full page reload
- **AND** a success toast MUST be displayed

#### Scenario: Last result shows success badge for successful run

- **WHEN** a schedule has `last_result` containing a success outcome
- **THEN** the Last result column MUST display a green "success" badge

#### Scenario: Last result shows error badge for failed run

- **WHEN** a schedule has `last_result` containing an error outcome
- **THEN** the Last result column MUST display a red "error" badge
- **AND** hovering or clicking the badge MUST reveal the full error text

#### Scenario: Schedule has never run

- **WHEN** a schedule has `last_run_at = null` and `last_result = null`
- **THEN** the Last run column MUST display a dash
- **AND** the Last result column MUST display a dash

#### Scenario: Run now button triggers immediate execution

- **WHEN** a user clicks the "Run now" button for a schedule named "daily-review" with prompt "Run daily review"
- **THEN** the frontend MUST trigger the butler to execute the schedule's prompt (via an appropriate API call or MCP tool invocation)
- **AND** a success toast MUST be displayed confirming the trigger
- **AND** the table data MUST be refetched to reflect the updated `last_run_at` and `last_result`

#### Scenario: Empty state when butler has no schedules

- **WHEN** a user navigates to the schedules tab and the butler has no scheduled tasks
- **THEN** the table MUST display an empty state message such as "No scheduled tasks" with a call-to-action button to create a new schedule

---

### Requirement: Schedule CRUD UI

The frontend SHALL provide UI controls for creating, editing, and deleting schedules within the schedules tab.

**Create form:** A "New schedule" button above the table SHALL open a creation form (inline panel or modal) with the following fields:
- **Name** (text input, required) -- the unique schedule name
- **Cron expression** (text input, required) -- a five-field cron expression. The form SHOULD display a live human-readable preview of the cron expression as the user types.
- **Prompt** (textarea, required) -- the prompt text to dispatch

The form SHALL have "Create" and "Cancel" buttons. Submitting the form SHALL call `POST /api/butlers/:name/schedules`. On success, the form SHALL close, a success toast SHALL be displayed, and the schedules table SHALL refetch.

**Edit modal:** Clicking a schedule name in the table (or an edit action) SHALL open an edit modal pre-populated with the schedule's current `name`, `cron`, and `prompt` values. The modal SHALL have "Save" and "Cancel" buttons. Submitting SHALL call `PUT /api/butlers/:name/schedules/:id` with only the changed fields. On success, the modal SHALL close, a success toast SHALL be displayed, and the table SHALL refetch.

**Delete with confirmation:** A delete action (button or menu item) per schedule SHALL open a confirmation dialog stating the schedule name and asking the user to confirm deletion. The dialog SHALL have "Delete" and "Cancel" buttons. Confirming SHALL call `DELETE /api/butlers/:name/schedules/:id`. On success, a success toast SHALL be displayed and the table SHALL refetch.

TOML-source schedules MUST NOT show the delete action. The edit modal for TOML-source schedules SHALL display a notice that the schedule is managed by `butler.toml` and only the `enabled` state can be changed from the dashboard.

#### Scenario: Create form opens and validates inputs

- **WHEN** a user clicks the "New schedule" button
- **THEN** a creation form MUST appear with empty Name, Cron expression, and Prompt fields
- **AND** the "Create" button MUST be disabled until all three fields are non-empty

#### Scenario: Live cron preview updates as user types

- **WHEN** the user types `0 9 * * 1-5` into the Cron expression field
- **THEN** a human-readable preview MUST update to display text such as "Every weekday at 9:00 AM"

#### Scenario: Invalid cron expression shows inline error

- **WHEN** the user types `not-valid` into the Cron expression field
- **THEN** an inline validation message MUST appear indicating the cron expression is invalid
- **AND** the "Create" button MUST remain disabled

#### Scenario: Successful schedule creation

- **WHEN** the user fills in Name = "weekly-report", Cron = "0 10 * * 1", Prompt = "Generate weekly report" and clicks "Create"
- **THEN** the frontend MUST call `POST /api/butlers/health/schedules` with the provided values
- **AND** on HTTP 201 response, the form MUST close
- **AND** a success toast MUST be displayed with a message such as "Schedule 'weekly-report' created"
- **AND** the schedules table MUST refetch to show the new schedule

#### Scenario: Create form shows API error

- **WHEN** the user submits the create form and the API returns HTTP 409 (duplicate name)
- **THEN** the form MUST display the error message from the API response
- **AND** the form MUST remain open so the user can correct the input

#### Scenario: Edit modal opens with pre-populated values

- **WHEN** a user clicks the name of a schedule with `name = "daily-review"`, `cron = "0 9 * * *"`, `prompt = "Run daily review"`
- **THEN** an edit modal MUST open with the Name field set to "daily-review", the Cron field set to "0 9 * * *", and the Prompt field set to "Run daily review"

#### Scenario: Edit modal submits only changed fields

- **WHEN** the user changes only the Prompt field in the edit modal and clicks "Save"
- **THEN** the frontend MUST call `PUT /api/butlers/health/schedules/:id` with only the `prompt` field in the body
- **AND** the `name` and `cron` fields MUST NOT be included in the request body

#### Scenario: Edit modal for TOML-source schedule shows restriction notice

- **WHEN** a user opens the edit modal for a schedule with `source = 'toml'`
- **THEN** the modal MUST display a notice such as "This schedule is managed by butler.toml. Only the enabled state can be changed from the dashboard."
- **AND** the Name, Cron, and Prompt fields MUST be read-only or disabled

#### Scenario: Delete confirmation dialog

- **WHEN** a user clicks the delete action for a schedule named "nightly-check"
- **THEN** a confirmation dialog MUST appear with text such as "Are you sure you want to delete the schedule 'nightly-check'? This action cannot be undone."
- **AND** the dialog MUST have "Delete" and "Cancel" buttons

#### Scenario: Confirming delete removes the schedule

- **WHEN** the user clicks "Delete" in the confirmation dialog for schedule `id = "abc-123"` on the `health` butler
- **THEN** the frontend MUST call `DELETE /api/butlers/health/schedules/abc-123`
- **AND** on HTTP 204 response, the dialog MUST close
- **AND** a success toast MUST be displayed with a message such as "Schedule 'nightly-check' deleted"
- **AND** the schedules table MUST refetch

#### Scenario: Cancel delete dismisses the dialog

- **WHEN** the user clicks "Cancel" in the delete confirmation dialog
- **THEN** the dialog MUST close without making any API call

#### Scenario: TOML-source schedule does not show delete action

- **WHEN** the schedules table displays a schedule with `source = 'toml'`
- **THEN** the delete action (button or menu item) MUST NOT be rendered for that row
