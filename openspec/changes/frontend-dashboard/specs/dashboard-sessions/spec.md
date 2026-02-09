# Dashboard Sessions

Cross-butler session browsing and detail views. The dashboard provides paginated session lists aggregated from all butler databases via fan-out queries, per-butler session lists, and detailed session views with full prompt text, tool call timelines, token/cost breakdowns, and trace correlation.

Sessions are read directly from each butler's `sessions` table (per the dual data-access pattern in D1). Each butler's database contains a `sessions` table with columns: `id`, `trigger_source`, `prompt`, `result`, `tool_calls` (JSONB), `success`, `error`, `duration_ms`, `started_at`, `completed_at`, `model`, `trace_id`, `cost` (JSONB), `input_tokens`, `output_tokens`, `parent_session_id`. Cost estimation is derived at query time from token counts and configurable per-model pricing (per D4).

## ADDED Requirements

### Requirement: Cross-butler paginated session list API

The dashboard API SHALL expose `GET /api/sessions` which aggregates sessions from all butler databases via concurrent fan-out queries, returning a paginated list with the originating butler name attached to each session record.

The endpoint SHALL accept the following query parameters:
- `limit` (integer, default 20) -- maximum number of sessions to return
- `offset` (integer, default 0) -- number of sessions to skip for pagination
- `butler` (string, optional) -- filter to sessions from a specific butler
- `trigger_source` (string, optional) -- filter by trigger source value
- `success` (boolean, optional) -- filter by success/failure status
- `from` (ISO 8601 timestamp, optional) -- include only sessions with `started_at >= from`
- `to` (ISO 8601 timestamp, optional) -- include only sessions with `started_at <= to`

The response SHALL be ordered by `started_at` descending across all butlers. Each session object in the response MUST include a `butler` field identifying which butler the session belongs to.

#### Scenario: Fetch sessions across all butlers with default pagination

- **WHEN** `GET /api/sessions` is called with no query parameters
- **THEN** the API MUST query all butler databases concurrently, merge the results, sort by `started_at` descending, and return at most 20 sessions
- **AND** each session object MUST include a `butler` field set to the name of the butler that owns the session
- **AND** each session object MUST include `id`, `trigger_source`, `prompt`, `success`, `duration_ms`, `started_at`, `completed_at`, `model`, `input_tokens`, `output_tokens`

#### Scenario: Filter sessions by butler name

- **WHEN** `GET /api/sessions?butler=health` is called
- **THEN** the API MUST return only sessions from the `health` butler's database
- **AND** all returned sessions MUST have `butler` set to `"health"`

#### Scenario: Filter sessions by date range

- **WHEN** `GET /api/sessions?from=2026-02-01T00:00:00Z&to=2026-02-07T23:59:59Z` is called
- **THEN** the API MUST return only sessions with `started_at` between the specified timestamps (inclusive)

#### Scenario: Filter sessions by trigger source and success status

- **WHEN** `GET /api/sessions?trigger_source=tick&success=false` is called
- **THEN** the API MUST return only sessions where `trigger_source` equals `"tick"` AND `success` is `false`

#### Scenario: Paginate through sessions

- **WHEN** `GET /api/sessions?limit=10&offset=20` is called
- **THEN** the API MUST skip the first 20 sessions (by `started_at` descending across all butlers) and return at most 10 sessions

#### Scenario: No sessions match the filters

- **WHEN** `GET /api/sessions?butler=nonexistent` is called and no butler named `"nonexistent"` exists
- **THEN** the API MUST return an empty list
- **AND** the response status MUST be 200

---

### Requirement: Single-butler paginated session list API

The dashboard API SHALL expose `GET /api/butlers/:name/sessions` which returns a paginated list of sessions from a single butler's database.

The endpoint SHALL accept the same query parameters as `GET /api/sessions` except `butler` (which is implicit from the URL path): `limit`, `offset`, `trigger_source`, `success`, `from`, `to`.

#### Scenario: Fetch sessions for a specific butler

- **WHEN** `GET /api/butlers/health/sessions` is called with no query parameters
- **THEN** the API MUST query only the `health` butler's database and return at most 20 sessions ordered by `started_at` descending
- **AND** each session object MUST include `id`, `trigger_source`, `prompt`, `success`, `duration_ms`, `started_at`, `completed_at`, `model`, `input_tokens`, `output_tokens`

#### Scenario: Filter single-butler sessions by date range and success

- **WHEN** `GET /api/butlers/relationship/sessions?from=2026-02-01T00:00:00Z&success=true` is called
- **THEN** the API MUST return only sessions from the `relationship` butler where `started_at >= 2026-02-01T00:00:00Z` AND `success` is `true`

#### Scenario: Butler does not exist

- **WHEN** `GET /api/butlers/nonexistent/sessions` is called and no butler named `"nonexistent"` is registered
- **THEN** the API MUST return a 404 response with an error message indicating the butler was not found

---

### Requirement: Session detail API

The dashboard API SHALL expose `GET /api/butlers/:name/sessions/:id` which returns the full session record including prompt, result, tool calls, error details, token breakdown, and trace ID.

#### Scenario: Fetch an existing session's full details

- **WHEN** `GET /api/butlers/health/sessions/abc-123-uuid` is called and the session exists in the `health` butler's database
- **THEN** the API MUST return the complete session record including `id`, `trigger_source`, `prompt` (full text, not truncated), `result` (full text), `tool_calls` (full JSONB array), `success`, `error`, `duration_ms`, `started_at`, `completed_at`, `model`, `input_tokens`, `output_tokens`, `trace_id`, `parent_session_id`, and `cost` (JSONB)

#### Scenario: Session does not exist

- **WHEN** `GET /api/butlers/health/sessions/nonexistent-uuid` is called and no session with that ID exists
- **THEN** the API MUST return a 404 response with an error message indicating the session was not found

#### Scenario: Session belongs to a different butler

- **WHEN** `GET /api/butlers/health/sessions/abc-123-uuid` is called but the session ID belongs to the `relationship` butler
- **THEN** the API MUST return a 404 response (since it only queries the specified butler's database)

---

### Requirement: Sessions page with paginated table and filters

The frontend SHALL render a sessions page at `/sessions` displaying a paginated table of sessions aggregated across all butlers, with filtering controls.

The table SHALL display the following columns for each session:
- **Timestamp** -- `started_at` formatted as a human-readable date and time
- **Butler** -- butler name displayed as a colored badge
- **Trigger source** -- the `trigger_source` value
- **Prompt** -- the `prompt` text, truncated to a maximum visible length with ellipsis
- **Duration** -- `duration_ms` formatted as a human-readable duration (e.g., "3.5s", "1m 12s")
- **Tokens** -- total token count (`input_tokens + output_tokens`), or a dash if not available
- **Est. cost** -- estimated cost derived from token counts and configurable pricing, or a dash if not available
- **Status** -- a badge indicating success (green) or failure (red)

The page SHALL provide the following filter controls:
- Butler selector (dropdown or multi-select, listing all known butlers)
- Date range picker (from/to)
- Trigger source selector
- Success/failure toggle or selector

#### Scenario: Sessions page loads with default view

- **WHEN** a user navigates to `/sessions`
- **THEN** the page MUST display the sessions table with the first page of results (default limit) sorted by timestamp descending
- **AND** all filter controls MUST be visible and set to their default (unfiltered) state

#### Scenario: User filters by butler and date range

- **WHEN** a user selects butler `"health"` from the butler filter and sets a date range of February 1-7 2026
- **THEN** the table MUST update to show only sessions from the `health` butler within the specified date range
- **AND** the URL query parameters SHOULD update to reflect the applied filters

#### Scenario: User navigates to next page

- **WHEN** the sessions table shows 20 results and the user clicks the next page control
- **THEN** the table MUST fetch and display the next page of sessions (offset by the page size)

#### Scenario: Prompt text is truncated in the table

- **WHEN** a session has a prompt longer than the maximum visible length
- **THEN** the prompt column MUST display the truncated text with an ellipsis indicator

#### Scenario: Session row with no token data

- **WHEN** a session has `null` values for `input_tokens` and `output_tokens` (e.g., pre-migration session)
- **THEN** the Tokens column MUST display a dash or "N/A"
- **AND** the Est. cost column MUST display a dash or "N/A"

---

### Requirement: Butler sessions tab

The frontend SHALL render a sessions tab within each butler's detail page that displays the same paginated session table as the `/sessions` page, but scoped to a single butler.

#### Scenario: Butler detail page shows sessions tab

- **WHEN** a user navigates to the `health` butler's detail page and selects the sessions tab
- **THEN** the sessions table MUST display only sessions belonging to the `health` butler
- **AND** the butler filter control MUST NOT be shown (since it is implicit)
- **AND** all other filter controls (date range, trigger source, success/failure) MUST be available

#### Scenario: Butler sessions tab pagination

- **WHEN** the `health` butler has more sessions than the default page size
- **THEN** the sessions tab MUST provide pagination controls to browse through all sessions

---

### Requirement: Session detail drawer

The frontend SHALL render a session detail drawer (slide-over panel) when a user clicks on a session row in any sessions table. The drawer SHALL display the complete session information.

The drawer MUST contain the following sections:

1. **Header** -- session ID, butler name badge, trigger source, timestamp, duration, and success/failure status badge
2. **Prompt** -- full prompt text, rendered in a scrollable monospace or formatted text area
3. **Tool calls timeline** -- an ordered list of tool calls from the `tool_calls` JSONB array, each displaying the tool name, arguments, and result. The calls MUST be displayed in the order they were made (array order).
4. **Result** -- full result text, rendered in a scrollable text area. If the session failed, this section SHALL display the error message instead or in addition to any partial result.
5. **Error details** -- if `error` is non-null, display the error message prominently with error styling
6. **Token breakdown** -- a summary showing input tokens, output tokens, total tokens, and estimated cost. Estimated cost SHALL be computed from token counts using the configurable pricing for the session's `model`.
7. **Trace link** -- if `trace_id` is non-null, display the trace ID as a clickable link that navigates to `/traces/:traceId`

#### Scenario: Open session detail for a successful session

- **WHEN** a user clicks on a successful session row in the sessions table
- **THEN** a detail drawer MUST slide open from the right side of the screen
- **AND** the drawer MUST display the full prompt text, the ordered tool calls with their arguments and results, the full result text, and the token breakdown
- **AND** the error details section MUST NOT be displayed

#### Scenario: Open session detail for a failed session

- **WHEN** a user clicks on a failed session row in the sessions table
- **THEN** the detail drawer MUST display the error message in the error details section with error styling (e.g., red background or border)
- **AND** if a partial result exists, it MUST also be displayed in the result section

#### Scenario: Tool calls displayed in order with arguments and results

- **WHEN** a session has three tool calls in its `tool_calls` array: `state_get("foo")`, `state_set("bar", 42)`, `notify("telegram", "done")`
- **THEN** the tool calls timeline MUST display all three calls in that exact order
- **AND** each call MUST show the tool name, the arguments passed, and the result returned

#### Scenario: Session with no tool calls

- **WHEN** a session has an empty `tool_calls` array
- **THEN** the tool calls timeline section MUST display an empty state message (e.g., "No tool calls recorded")

#### Scenario: Trace link navigation

- **WHEN** a session has `trace_id` set to `"abc123def456"`
- **THEN** the drawer MUST display the trace ID as a clickable link
- **AND** clicking the link MUST navigate to `/traces/abc123def456`

#### Scenario: Session with no trace ID

- **WHEN** a session has `trace_id` set to `null`
- **THEN** the trace link section MUST display a dash or "No trace" instead of a link

#### Scenario: Token breakdown with cost estimation

- **WHEN** a session has `input_tokens = 1500`, `output_tokens = 500`, and `model = "claude-sonnet-4-20250514"`
- **THEN** the token breakdown section MUST display input tokens as 1,500, output tokens as 500, total tokens as 2,000
- **AND** the estimated cost MUST be computed using the configured pricing for the `claude-sonnet-4-20250514` model (input_tokens * input_price + output_tokens * output_price)

#### Scenario: Token breakdown with missing token data

- **WHEN** a session has `null` values for both `input_tokens` and `output_tokens`
- **THEN** the token breakdown section MUST display "No token data available"
- **AND** no cost estimate MUST be shown

---

### Requirement: Cost column derivation

The estimated cost displayed in session tables and detail views SHALL be derived at query time from token counts and configurable per-model pricing. Cost MUST NOT be stored in the database. The pricing configuration SHALL map model identifiers to per-token input and output prices.

#### Scenario: Cost computed from token counts and pricing config

- **WHEN** a session has `input_tokens = 2000`, `output_tokens = 800`, and `model = "claude-sonnet-4-20250514"`
- **AND** the pricing config specifies `claude-sonnet-4-20250514` input price as $0.000003 per token and output price as $0.000015 per token
- **THEN** the estimated cost MUST be computed as `(2000 * 0.000003) + (800 * 0.000015) = $0.006 + $0.012 = $0.018`

#### Scenario: Cost unavailable when tokens are missing

- **WHEN** a session has `null` values for `input_tokens` or `output_tokens`
- **THEN** the estimated cost MUST be displayed as unavailable (dash or "N/A")
- **AND** no partial cost calculation MUST be attempted

#### Scenario: Cost unavailable when model pricing is not configured

- **WHEN** a session has valid token counts but the `model` value does not exist in the pricing configuration
- **THEN** the estimated cost MUST be displayed as unavailable
- **AND** the token counts MUST still be displayed normally

#### Scenario: Pricing config is updatable without migration

- **WHEN** the operator updates the `pricing.toml` configuration file with new model prices
- **THEN** the dashboard API MUST reflect the updated prices on subsequent requests
- **AND** no database migration or restart SHALL be required (config reload is acceptable)
