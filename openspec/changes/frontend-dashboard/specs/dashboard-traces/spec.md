# Dashboard Traces

Simplified distributed trace viewer for the Butlers dashboard. Traces are reconstructed from session records (`trace_id`, `parent_session_id` columns) across all butler databases and `routing_log` entries from the Switchboard database. No separate span storage -- this is a simplified view compared to Grafana Tempo, covering the session-level call graph (which butler triggered which, how long each step took).

Each butler has its own `sessions` table with `trace_id` (TEXT, nullable) and `parent_session_id` (UUID, nullable). The Switchboard has a `routing_log` table with `trace_id` (TEXT), `source_channel` (TEXT), `routed_to` (TEXT), `prompt_summary` (TEXT), `group_id` (UUID, nullable), and `created_at` (TIMESTAMPTZ). Traces are assembled by grouping sessions across all butler databases by `trace_id`, then reconstructing parent-child relationships using `parent_session_id`.

## ADDED Requirements

### Requirement: Trace list API

The dashboard API SHALL expose `GET /api/traces` which aggregates sessions from all butler databases, groups them by `trace_id`, and returns a paginated list of trace summaries.

The endpoint SHALL accept the following query parameters:
- `limit` (integer, default 20) -- maximum number of traces to return
- `offset` (integer, default 0) -- number of traces to skip for pagination
- `butler` (string, optional) -- filter to traces that include at least one session from the specified butler
- `from` (ISO 8601 timestamp, optional) -- include only traces where the earliest session `started_at >= from`
- `to` (ISO 8601 timestamp, optional) -- include only traces where the earliest session `started_at <= to`

The response SHALL be ordered by trace start time descending (the earliest `started_at` among all sessions in the trace). Each trace object in the response MUST include:
- `trace_id` -- the shared trace identifier
- `start_time` -- the earliest `started_at` timestamp among all sessions in the trace
- `total_duration` -- the time span from the earliest `started_at` to the latest `completed_at` across all sessions in the trace, in milliseconds
- `entry_point` -- an object containing `channel` (the `source_channel` from the corresponding `routing_log` entry, or `"direct"` if no routing log entry exists) and `butler` (the butler that owns the root session)
- `span_count` -- the total number of sessions sharing this `trace_id` across all butler databases

Sessions with a NULL `trace_id` SHALL be excluded from trace aggregation.

#### Scenario: Fetch traces with default pagination

- **WHEN** `GET /api/traces` is called with no query parameters
- **THEN** the API MUST query all butler databases concurrently for sessions with non-NULL `trace_id`, group them by `trace_id`, compute the summary fields for each trace, sort by `start_time` descending, and return at most 20 traces

#### Scenario: Filter traces by butler

- **WHEN** `GET /api/traces?butler=health` is called
- **THEN** the API MUST return only traces that include at least one session from the `health` butler's database
- **AND** the `span_count` and `total_duration` MUST still reflect all sessions in the trace across all butlers (not just those from `health`)

#### Scenario: Filter traces by date range

- **WHEN** `GET /api/traces?from=2026-02-01T00:00:00Z&to=2026-02-07T23:59:59Z` is called
- **THEN** the API MUST return only traces whose `start_time` (earliest session `started_at`) falls within the specified range (inclusive)

#### Scenario: Paginate through traces

- **WHEN** `GET /api/traces?limit=10&offset=20` is called
- **THEN** the API MUST skip the first 20 traces (by `start_time` descending) and return at most 10 traces

#### Scenario: No traces exist

- **WHEN** `GET /api/traces` is called and no sessions with non-NULL `trace_id` exist in any butler database
- **THEN** the API MUST return an empty list
- **AND** the response status MUST be 200

#### Scenario: Trace with active session reports partial duration

- **WHEN** a trace includes a session that has not yet completed (`completed_at` IS NULL)
- **THEN** the `total_duration` MUST be computed using the current time in place of the missing `completed_at`
- **AND** the trace MUST still appear in the list (it SHALL NOT be excluded due to the active session)

---

### Requirement: Trace detail API

The dashboard API SHALL expose `GET /api/traces/:trace_id` which returns the full trace detail including a hierarchical span structure reconstructed from session records and routing log entries.

The endpoint SHALL query all butler databases concurrently for sessions WHERE `trace_id` matches the requested trace ID. It SHALL also query the Switchboard's `routing_log` table for entries WHERE `trace_id` matches. The results SHALL be assembled into a tree structure using `parent_session_id` relationships.

The response MUST include:
- `trace_id` -- the trace identifier
- `start_time` -- the earliest `started_at` across all sessions in the trace
- `total_duration` -- time span from earliest `started_at` to latest `completed_at`, in milliseconds
- `entry_point` -- an object with `channel` and `butler` as defined in the trace list API
- `spans` -- a hierarchical array of span objects representing the session tree

Each span object MUST include:
- `session_id` -- the session UUID
- `butler` -- the name of the butler that owns this session
- `trigger_source` -- the session's trigger source
- `started_at` -- session start timestamp
- `duration_ms` -- session duration in milliseconds
- `success` -- boolean indicating session outcome
- `input_tokens` -- input token count (nullable)
- `output_tokens` -- output token count (nullable)
- `model` -- model identifier (nullable)
- `tool_calls` -- the JSONB array of tool calls from the session
- `prompt` -- the session prompt text (truncated to 200 characters in the span, full text available via session detail API)
- `result` -- the session result text (truncated to 200 characters)
- `error` -- error message if the session failed (nullable)
- `children` -- nested array of child span objects (sessions whose `parent_session_id` matches this session's `id`)

The `routing_log` entries matching the trace SHALL be included in the response as a separate `routing_hops` array, each containing:
- `id` -- routing log entry UUID
- `source_channel` -- originating channel
- `source_id` -- sender identifier
- `routed_to` -- target butler name
- `prompt_summary` -- summary of the routed prompt
- `group_id` -- decomposition group UUID (nullable)
- `created_at` -- timestamp of the routing event

#### Scenario: Fetch a trace with a single root session and two child sessions

- **WHEN** `GET /api/traces/abc-trace-123` is called
- **AND** the trace contains three sessions: a root session in the `switchboard` butler (with `parent_session_id` NULL), and two child sessions in the `health` and `relationship` butlers (each with `parent_session_id` set to the root session's ID)
- **THEN** the response MUST return a `spans` array containing one root span for the switchboard session
- **AND** that root span's `children` array MUST contain two child spans, one for the health session and one for the relationship session
- **AND** each child span's `children` array MUST be empty

#### Scenario: Fetch a trace with routing hops

- **WHEN** `GET /api/traces/abc-trace-123` is called
- **AND** the Switchboard's `routing_log` contains two entries with `trace_id = 'abc-trace-123'` (one routing to `health`, one to `relationship`)
- **THEN** the response MUST include a `routing_hops` array containing both routing log entries
- **AND** each hop MUST include `source_channel`, `routed_to`, `prompt_summary`, and `created_at`

#### Scenario: Fetch a trace that does not exist

- **WHEN** `GET /api/traces/nonexistent-trace-id` is called and no sessions with that `trace_id` exist in any butler database
- **THEN** the API MUST return a 404 response with an error message indicating the trace was not found

#### Scenario: Trace with deeply nested session hierarchy

- **WHEN** a trace has three levels of nesting (root -> child -> grandchild)
- **THEN** the `spans` tree MUST correctly represent all three levels
- **AND** the grandchild session MUST appear in the `children` array of the child span, not directly under the root span

#### Scenario: Trace with orphaned sessions

- **WHEN** a trace contains a session whose `parent_session_id` references a session that does not exist in any butler database (e.g., the parent session was deleted or belongs to a failed query)
- **THEN** the orphaned session MUST be included as a root-level span in the `spans` array
- **AND** the response MUST NOT fail or omit the orphaned session

---

### Requirement: Trace tree assembly

The dashboard API SHALL reconstruct parent-child relationships from `parent_session_id` columns on session records. The root session of a trace is the session with `parent_session_id` set to NULL. Routing log entries from the Switchboard fill in routing hop metadata but do not form part of the span tree.

The tree assembly algorithm SHALL:
1. Collect all sessions with the matching `trace_id` from all butler databases via fan-out query
2. Index sessions by `id` for O(1) lookup
3. For each session, find its parent by `parent_session_id` and attach it as a child
4. Sessions with `parent_session_id` NULL or with a `parent_session_id` not found in the collected sessions are treated as root-level spans
5. Sort children within each parent by `started_at` ascending (chronological order)

#### Scenario: Tree with one root and multiple children

- **WHEN** a trace contains sessions A (parent=NULL), B (parent=A), and C (parent=A)
- **AND** B started at 10:00:01 and C started at 10:00:03
- **THEN** the assembled tree MUST have A as the single root span
- **AND** A's children MUST be [B, C] in that order (B before C, sorted by `started_at`)

#### Scenario: Tree with multiple roots

- **WHEN** a trace contains sessions A (parent=NULL) and B (parent=NULL)
- **THEN** the assembled tree MUST have two root-level spans: A and B
- **AND** both MUST appear in the top-level `spans` array, sorted by `started_at` ascending

#### Scenario: Empty children arrays for leaf sessions

- **WHEN** a session has no other sessions referencing it as `parent_session_id`
- **THEN** its `children` array MUST be an empty array (not null or absent)

#### Scenario: Cross-butler parent-child relationship

- **WHEN** session A belongs to the `switchboard` butler and session B belongs to the `health` butler
- **AND** session B has `parent_session_id` set to session A's ID
- **THEN** the tree assembly MUST correctly link B as a child of A despite them being in different butler databases

---

### Requirement: Trace list page

The frontend SHALL render a trace list page at `/traces` displaying a paginated table of traces with filtering controls.

The table SHALL display the following columns for each trace:
- **Trace ID** -- the `trace_id` value, truncated to the first 8 characters with a copy-to-clipboard button for the full ID
- **Start time** -- `start_time` formatted as a human-readable date and time
- **Duration** -- `total_duration` formatted as a human-readable duration (e.g., "3.5s", "1m 12s")
- **Entry point** -- the `channel` and `butler` from `entry_point`, formatted as "{channel} -> {butler}" (e.g., "telegram -> health")
- **Spans** -- the `span_count` value displayed as a numeric badge

The page SHALL provide the following filter controls:
- Date range picker (from/to)
- Butler selector (dropdown listing all known butlers)

Clicking a table row SHALL navigate to `/traces/:traceId` for the clicked trace.

#### Scenario: Trace list page loads with default view

- **WHEN** a user navigates to `/traces`
- **THEN** the page MUST display the traces table with the first page of results (default limit 20) sorted by start time descending
- **AND** all filter controls MUST be visible and set to their default (unfiltered) state

#### Scenario: User filters by date range

- **WHEN** a user sets a date range of February 1-7 2026 in the date range picker
- **THEN** the table MUST update to show only traces whose start time falls within the specified date range
- **AND** the URL query parameters SHOULD update to reflect the applied filter

#### Scenario: User filters by butler

- **WHEN** a user selects `"health"` from the butler filter dropdown
- **THEN** the table MUST update to show only traces that include at least one session from the `health` butler

#### Scenario: User clicks a trace row

- **WHEN** a user clicks on a row for trace ID `"abc123def456789"`
- **THEN** the browser MUST navigate to `/traces/abc123def456789`

#### Scenario: User copies full trace ID

- **WHEN** a user clicks the copy button next to a truncated trace ID `"abc123de..."`
- **THEN** the full trace ID MUST be copied to the clipboard
- **AND** a success toast MUST confirm the copy action

#### Scenario: Trace list with no results

- **WHEN** the API returns an empty trace list (e.g., no sessions have trace IDs, or filters match nothing)
- **THEN** the page MUST display an empty state message (e.g., "No traces found")

#### Scenario: Pagination controls

- **WHEN** the trace list has more traces than the page size
- **THEN** pagination controls MUST be displayed
- **AND** clicking next/previous MUST fetch and display the corresponding page of traces

---

### Requirement: Trace detail page

The frontend SHALL render a trace detail page at `/traces/:traceId` displaying a waterfall/timeline visualization of the trace's span hierarchy. Each span is rendered as a horizontal bar positioned and sized relative to the trace's time range.

The waterfall view SHALL:
- Display spans as horizontal bars in a vertically stacked layout, with nesting indicated by indentation
- Position each bar horizontally based on its `started_at` relative to the trace's `start_time`
- Size each bar's width proportionally to its `duration_ms` relative to the trace's `total_duration`
- Color each bar by the butler it belongs to (each butler gets a distinct, consistent color)
- Display the butler name and trigger source as a label on or next to each bar
- Show a time axis at the top of the waterfall indicating the trace's time range

The page header SHALL display:
- The full trace ID (with copy-to-clipboard)
- The trace start time
- The total duration
- The entry point (channel and butler)
- The total span count

Clicking a span bar SHALL open an attributes panel (slide-over or inline expansion) showing the span's full details:
- Butler name
- Session ID (clickable link to the session detail, via the session detail drawer)
- Trigger source
- Prompt (full text, scrollable)
- Result (full text, scrollable)
- Error message (if applicable, with error styling)
- Tool calls list (tool name and arguments for each call)
- Token breakdown (input tokens, output tokens, total)
- Duration
- Model identifier

#### Scenario: Trace detail page renders a waterfall for a three-span trace

- **WHEN** a user navigates to `/traces/abc-trace-123`
- **AND** the trace contains three spans: a root switchboard session (0-5000ms), a child health session (500-3000ms), and a child relationship session (3200-4800ms)
- **THEN** the waterfall MUST render three horizontal bars
- **AND** the root bar MUST span the full width of the timeline
- **AND** the health bar MUST be indented under the root and positioned starting at 10% of the timeline width with a width proportional to 2500ms
- **AND** the relationship bar MUST be indented under the root and positioned starting at 64% of the timeline width with a width proportional to 1600ms

#### Scenario: Spans are colored by butler

- **WHEN** the trace contains sessions from butlers `switchboard`, `health`, and `relationship`
- **THEN** all spans belonging to the `switchboard` butler MUST share the same color
- **AND** all spans belonging to the `health` butler MUST share a different color
- **AND** all spans belonging to the `relationship` butler MUST share a different color
- **AND** a color legend or key MUST be visible on the page identifying which color maps to which butler

#### Scenario: User clicks a span to view attributes

- **WHEN** a user clicks on the health butler's span bar in the waterfall
- **THEN** an attributes panel MUST appear showing the health session's full details: butler name, session ID, trigger source, prompt, result, tool calls, token breakdown, duration, and model
- **AND** the session ID MUST be a clickable link

#### Scenario: Attributes panel shows error details for failed span

- **WHEN** a user clicks on a span whose session has `success = false` and a non-null `error` field
- **THEN** the attributes panel MUST prominently display the error message with error styling (e.g., red text or red border)
- **AND** the result section MUST display any partial result if present

#### Scenario: Trace detail page for a nonexistent trace

- **WHEN** a user navigates to `/traces/nonexistent-id` and the API returns a 404
- **THEN** the page MUST display an error state indicating the trace was not found
- **AND** a link to return to `/traces` MUST be provided

#### Scenario: Deeply nested spans are indented progressively

- **WHEN** a trace has three levels of nesting (root -> child -> grandchild)
- **THEN** the root span bar MUST have no indentation
- **AND** the child span bar MUST be indented one level
- **AND** the grandchild span bar MUST be indented two levels
- **AND** the visual nesting MUST clearly communicate the parent-child hierarchy

#### Scenario: Routing hops are displayed

- **WHEN** the trace detail response includes `routing_hops`
- **THEN** the page MUST display the routing hops in a supplementary section (e.g., below the waterfall or in a collapsible panel)
- **AND** each hop MUST show the source channel, routed-to butler, prompt summary, and timestamp

---

### Requirement: Session-to-trace navigation

The session detail drawer (as defined in the dashboard-sessions spec) SHALL provide navigation from a session to its containing trace. When a session has a non-null `trace_id`, the trace ID SHALL be displayed as a clickable link that navigates to the trace detail page.

#### Scenario: Session with trace_id links to trace detail

- **WHEN** a user opens the session detail drawer for a session with `trace_id` set to `"abc123def456"`
- **THEN** the drawer MUST display the trace ID in the trace link section
- **AND** the trace ID MUST be rendered as a clickable link
- **AND** clicking the link MUST navigate to `/traces/abc123def456`

#### Scenario: Session without trace_id shows no trace link

- **WHEN** a user opens the session detail drawer for a session with `trace_id` set to `null`
- **THEN** the trace link section MUST display "No trace" or a dash
- **AND** no clickable link MUST be rendered

#### Scenario: Trace detail page highlights the originating session

- **WHEN** a user navigates to `/traces/abc123def456` from a session detail drawer for session `sess-789`
- **THEN** the trace detail page SHOULD visually highlight or scroll to the span corresponding to session `sess-789` in the waterfall view
