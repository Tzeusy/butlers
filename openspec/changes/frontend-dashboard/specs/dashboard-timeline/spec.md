# Dashboard Timeline

Unified cross-butler event stream for the Butlers dashboard. The timeline aggregates events from their natural tables across multiple butler databases: `sessions` (all butlers), `routing_log` (Switchboard), `scheduled_tasks` (all butlers), and `notifications` (Switchboard). Events are merged and sorted by timestamp descending, with cursor-based pagination. Fan-out aggregation at query time across 5 butler databases (per D8).

Each event is normalized into a common envelope: `{type, butler, timestamp, data}`. The cursor is a timestamp, enabling efficient "load older" pagination without offset drift.

---

## ADDED Requirements

### Requirement: Cross-butler timeline API

The dashboard API SHALL expose `GET /api/timeline` which aggregates events from all butler databases via concurrent fan-out queries, returning a unified event stream sorted by timestamp descending.

The endpoint SHALL accept the following query parameters:
- `limit` (integer, default 50) -- maximum number of events to return
- `before` (ISO 8601 timestamp, optional) -- cursor; return only events with timestamp strictly older than this value
- `butlers` (comma-separated string, optional) -- filter to events originating from the specified butlers (e.g., `butlers=health,relationship`)
- `types` (comma-separated string, optional) -- filter by event type; allowed values: `session`, `routing`, `notification`, `error`, `schedule`

The response SHALL be JSON with the following structure:
- `events` -- array of event objects, each conforming to the common envelope: `{type, butler, timestamp, data}`
- `next_cursor` -- ISO 8601 timestamp of the oldest event in the returned batch, or `null` if no more events exist

The `type` field SHALL be one of: `session`, `routing`, `notification`, `error`, `schedule`. The `butler` field SHALL identify the butler that owns the source record. The `timestamp` field SHALL be an ISO 8601 string. The `data` field SHALL contain event-type-specific details (see Event type aggregation requirement).

#### Scenario: Fetch timeline with default parameters

- **WHEN** `GET /api/timeline` is called with no query parameters
- **THEN** the API MUST query all butler databases concurrently for recent events across all source tables
- **AND** the response MUST contain an `events` array with at most 50 events sorted by `timestamp` descending
- **AND** each event object MUST include `type`, `butler`, `timestamp`, and `data` fields
- **AND** the response MUST include a `next_cursor` field set to the `timestamp` of the oldest event in the batch

#### Scenario: Fetch timeline with cursor-based pagination

- **WHEN** `GET /api/timeline?before=2026-02-08T14:30:00Z` is called
- **THEN** the API MUST return only events with `timestamp` strictly before `2026-02-08T14:30:00Z`
- **AND** at most 50 events MUST be returned, sorted by `timestamp` descending

#### Scenario: Filter timeline by butler names

- **WHEN** `GET /api/timeline?butlers=health,relationship` is called
- **THEN** the API MUST return only events where the `butler` field is `"health"` or `"relationship"`
- **AND** the fan-out query SHOULD only target the `health` and `relationship` databases (plus Switchboard for routing/notification events referencing those butlers)

#### Scenario: Filter timeline by event types

- **WHEN** `GET /api/timeline?types=session,error` is called
- **THEN** the API MUST return only events where `type` is `"session"` or `"error"`
- **AND** events of type `routing`, `notification`, and `schedule` MUST NOT appear in the response

#### Scenario: Combine butler and type filters

- **WHEN** `GET /api/timeline?butlers=health&types=session&limit=10` is called
- **THEN** the API MUST return at most 10 events that are both from the `health` butler and of type `session`

#### Scenario: No events match the filters

- **WHEN** `GET /api/timeline?butlers=nonexistent` is called and no butler named `"nonexistent"` exists
- **THEN** the API MUST return `{"events": [], "next_cursor": null}`
- **AND** the response status MUST be 200

#### Scenario: Fewer events than limit remain

- **WHEN** `GET /api/timeline?before=2026-01-01T00:00:00Z` is called and only 3 events exist before that timestamp
- **THEN** the response MUST contain exactly 3 events
- **AND** `next_cursor` MUST be `null` to indicate no more events are available

---

### Requirement: Event type aggregation

The timeline API SHALL query the following source tables and map their rows to timeline events:

1. **`sessions` table (all butler DBs):**
   - Session start events: `type="session"`, derived from rows where `completed_at IS NULL` (in-progress sessions). The `data` field MUST include `session_id`, `trigger_source`, `prompt` (truncated to 200 characters), and `status` set to `"started"`.
   - Session complete events: `type="session"`, derived from rows where `success=true` AND `completed_at IS NOT NULL`. The `data` field MUST include `session_id`, `trigger_source`, `prompt` (truncated to 200 characters), `duration_ms`, `status` set to `"completed"`, and `model`.
   - Session fail events: `type="error"`, derived from rows where `success=false` AND `completed_at IS NOT NULL`. The `data` field MUST include `session_id`, `trigger_source`, `prompt` (truncated to 200 characters), `error` (truncated to 300 characters), `duration_ms`, and `status` set to `"failed"`.

2. **`routing_log` table (Switchboard DB only):**
   - Routing events: `type="routing"`. The `data` field MUST include `routing_id`, `source_channel`, `source_id`, `routed_to`, `prompt_summary` (truncated to 200 characters), and `group_id` (if present).
   - The `butler` field for routing events SHALL be set to `"switchboard"`.
   - The `timestamp` field SHALL be derived from `created_at`.

3. **`notifications` table (Switchboard DB only):**
   - Notification events: `type="notification"`. The `data` field MUST include `notification_id`, `channel`, `recipient`, `source_butler`, `status` (sent/failed), and `message` (truncated to 200 characters).
   - If `status='failed'`, the `data` field MUST also include the `error` message.
   - The `butler` field SHALL be set to the `source_butler` value from the notifications row.
   - The `timestamp` field SHALL be derived from `created_at`.

4. **`scheduled_tasks` table (all butler DBs):**
   - Schedule dispatch events: `type="schedule"`, derived from rows where `last_run_at IS NOT NULL`. The `data` field MUST include `task_id`, `task_name`, `cron`, `last_result` (truncated to 200 characters), and `next_run_at`.
   - The `timestamp` field SHALL be derived from `last_run_at`.
   - Only the most recent dispatch per task SHALL be considered (based on `last_run_at`).

All events from all sources MUST be merged into a single list and sorted by `timestamp` descending before applying the `limit`.

#### Scenario: Timeline contains mixed event types from multiple butlers

- **WHEN** the `health` butler has 2 completed sessions, the `relationship` butler has 1 failed session, the Switchboard has 3 routing log entries and 1 sent notification, and the `general` butler has 1 recently dispatched scheduled task
- **THEN** the timeline MUST return all 8 events merged and sorted by `timestamp` descending
- **AND** each event MUST have the correct `type` and `butler` fields

#### Scenario: Session complete event data shape

- **WHEN** a session in the `health` butler's database has `id='abc-123'`, `trigger_source='tick'`, `prompt='Check vitals and log weight'`, `success=true`, `duration_ms=4500`, `completed_at='2026-02-08T10:00:00Z'`, `model='claude-sonnet-4-20250514'`
- **THEN** the corresponding timeline event MUST be `{type: "session", butler: "health", timestamp: "2026-02-08T10:00:00Z", data: {session_id: "abc-123", trigger_source: "tick", prompt: "Check vitals and log weight", duration_ms: 4500, status: "completed", model: "claude-sonnet-4-20250514"}}`

#### Scenario: Failed session maps to error event type

- **WHEN** a session in the `relationship` butler's database has `success=false` and `error='MCP connection refused'`
- **THEN** the corresponding timeline event MUST have `type` set to `"error"` (not `"session"`)
- **AND** `data.status` MUST be `"failed"`
- **AND** `data.error` MUST contain `"MCP connection refused"`

#### Scenario: Routing event data shape

- **WHEN** a `routing_log` entry in the Switchboard database has `id='rte-456'`, `source_channel='telegram'`, `source_id='12345'`, `routed_to='health'`, `prompt_summary='Log my weight: 82kg'`, `created_at='2026-02-08T09:55:00Z'`
- **THEN** the corresponding timeline event MUST be `{type: "routing", butler: "switchboard", timestamp: "2026-02-08T09:55:00Z", data: {routing_id: "rte-456", source_channel: "telegram", source_id: "12345", routed_to: "health", prompt_summary: "Log my weight: 82kg", group_id: null}}`

#### Scenario: Notification event for a failed delivery

- **WHEN** a `notifications` entry has `source_butler='health'`, `channel='telegram'`, `status='failed'`, `error='Chat not found'`, `message='Your daily summary is ready'`, `created_at='2026-02-08T11:00:00Z'`
- **THEN** the corresponding timeline event MUST have `type` set to `"notification"`, `butler` set to `"health"`, and `data` including `status: "failed"`, `error: "Chat not found"`, and `message: "Your daily summary is ready"`

#### Scenario: Schedule dispatch event data shape

- **WHEN** a `scheduled_tasks` entry in the `general` butler's database has `id='task-789'`, `name='daily-review'`, `cron='0 9 * * *'`, `last_run_at='2026-02-08T09:00:00Z'`, `last_result='Completed successfully'`, `next_run_at='2026-02-09T09:00:00Z'`
- **THEN** the corresponding timeline event MUST be `{type: "schedule", butler: "general", timestamp: "2026-02-08T09:00:00Z", data: {task_id: "task-789", task_name: "daily-review", cron: "0 9 * * *", last_result: "Completed successfully", next_run_at: "2026-02-09T09:00:00Z"}}`

#### Scenario: Long text fields are truncated in timeline events

- **WHEN** a session has a `prompt` longer than 200 characters
- **THEN** the `data.prompt` field in the timeline event MUST be truncated to 200 characters with an ellipsis appended
- **AND** the full prompt MUST remain accessible via the session detail API

---

### Requirement: Cursor-based pagination

The timeline API SHALL implement cursor-based pagination using timestamps. The `before` query parameter acts as a cursor -- it specifies a timestamp, and the API returns only events with `timestamp` strictly less than the cursor value.

The response SHALL include a `next_cursor` field set to the `timestamp` of the oldest (last) event in the returned batch. When no more events exist beyond the returned batch, `next_cursor` SHALL be `null`.

Cursor values MUST be ISO 8601 timestamps with timezone (e.g., `2026-02-08T14:30:00.123456Z`). Microsecond precision MUST be preserved to avoid skipping events with identical second-level timestamps.

#### Scenario: First page has no cursor

- **WHEN** `GET /api/timeline?limit=20` is called without a `before` parameter
- **THEN** the API MUST return the 20 most recent events across all butlers
- **AND** `next_cursor` MUST be set to the `timestamp` of the 20th (oldest) event in the batch

#### Scenario: Subsequent page uses previous next_cursor

- **WHEN** a first request to `GET /api/timeline?limit=20` returns `next_cursor="2026-02-07T18:45:12.123456Z"`
- **AND** a second request is made to `GET /api/timeline?limit=20&before=2026-02-07T18:45:12.123456Z`
- **THEN** the second response MUST contain only events with `timestamp` strictly before `2026-02-07T18:45:12.123456Z`
- **AND** no events from the first page MUST appear in the second response

#### Scenario: Last page returns null cursor

- **WHEN** `GET /api/timeline?before=2026-01-15T00:00:00Z&limit=50` is called and only 12 events exist before that timestamp
- **THEN** the response MUST contain exactly 12 events
- **AND** `next_cursor` MUST be `null`

#### Scenario: Microsecond precision prevents event skipping

- **WHEN** two events have timestamps `2026-02-08T10:00:00.000001Z` and `2026-02-08T10:00:00.000002Z`
- **AND** a request is made with `before=2026-02-08T10:00:00.000002Z`
- **THEN** the event at `2026-02-08T10:00:00.000001Z` MUST be included in the response
- **AND** the event at `2026-02-08T10:00:00.000002Z` MUST NOT be included

---

### Requirement: Timeline page

The frontend SHALL render a timeline page at `/timeline` displaying a vertical event stream mixing all event types from all butlers. The timeline is the primary cross-butler activity view.

Each event in the stream SHALL display:
- **Timestamp** -- formatted as a human-readable relative time (e.g., "2 minutes ago", "yesterday at 3:15 PM") with the full ISO timestamp available on hover
- **Butler badge** -- a colored badge showing the butler name that owns the event
- **Event type icon** -- a distinct icon per event type: session (play/terminal icon), routing (arrow/route icon), notification (bell icon), error (warning/exclamation icon), schedule (clock icon)
- **One-line summary** -- a concise description derived from the event data (e.g., "Session completed in 4.5s via tick trigger", "Routed telegram message to health", "Notification sent via telegram", "daily-review dispatched", "Session failed: MCP connection refused")

Each event SHALL be expandable to reveal a detail panel showing the full `data` payload in a structured, readable format. For session events, the detail panel MUST include a link to the session detail drawer (navigating to `/sessions` with the session pre-selected or opening the drawer inline).

#### Scenario: Timeline page loads with recent events

- **WHEN** a user navigates to `/timeline`
- **THEN** the page MUST display the most recent events (default limit of 50) in a vertical stream, ordered by timestamp descending (newest at top)
- **AND** each event MUST display a timestamp, butler badge, event type icon, and one-line summary

#### Scenario: Event type icons are visually distinct

- **WHEN** the timeline contains events of types `session`, `routing`, `notification`, `error`, and `schedule`
- **THEN** each event type MUST be rendered with a distinct icon that is visually distinguishable from the others
- **AND** error events MUST use a warning/danger visual treatment (e.g., red icon or red accent)

#### Scenario: Expanding an event reveals detail panel

- **WHEN** a user clicks on a session-complete event in the timeline
- **THEN** the event MUST expand to show a detail panel containing the full event data: `session_id`, `trigger_source`, full `prompt`, `duration_ms`, `status`, and `model`
- **AND** the detail panel MUST include a clickable link to view the full session details

#### Scenario: Expanding a routing event shows routing details

- **WHEN** a user clicks on a routing event in the timeline
- **THEN** the detail panel MUST show `source_channel`, `source_id`, `routed_to`, and the full `prompt_summary`
- **AND** if `group_id` is present, it MUST be displayed to indicate the event was part of a multi-route decomposition

#### Scenario: Error event summary includes error message

- **WHEN** a session-failed event has `data.error` set to `"MCP connection refused"`
- **THEN** the one-line summary MUST include the error text (e.g., "Session failed: MCP connection refused")
- **AND** the event MUST be styled with error/danger visual treatment

#### Scenario: One-line summary varies by event type

- **WHEN** a session-complete event has `trigger_source="tick"` and `duration_ms=4500`
- **THEN** the summary MUST read something like "Session completed in 4.5s via tick trigger"
- **WHEN** a routing event has `source_channel="telegram"` and `routed_to="health"`
- **THEN** the summary MUST read something like "Routed telegram message to health"
- **WHEN** a notification event has `channel="telegram"` and `status="sent"`
- **THEN** the summary MUST read something like "Notification sent via telegram"
- **WHEN** a schedule event has `task_name="daily-review"`
- **THEN** the summary MUST read something like "daily-review dispatched"

---

### Requirement: Timeline filters

The timeline page SHALL provide filter controls that allow the user to narrow the displayed events by butler, event type, and date range.

The following filter controls SHALL be provided:
- **Butler multi-select** -- a multi-select control listing all known butlers. When one or more butlers are selected, only events from those butlers SHALL be displayed. When no butlers are selected (default), events from all butlers SHALL be displayed.
- **Event type multi-select** -- a multi-select control listing all event types: session, routing, notification, error, schedule. When one or more types are selected, only events of those types SHALL be displayed. When no types are selected (default), all event types SHALL be displayed.
- **Date range picker** -- a date range selector with "from" and "to" fields. When set, only events with `timestamp` within the specified range SHALL be displayed.

Filter selections SHALL be reflected in the URL query parameters so that filtered views can be shared or bookmarked. Changing a filter MUST trigger a new API request with the corresponding query parameters.

#### Scenario: Filter by single butler

- **WHEN** the user selects `"health"` in the butler multi-select filter
- **THEN** the timeline MUST display only events where `butler` is `"health"`
- **AND** the URL MUST update to include `?butlers=health`
- **AND** a new API request MUST be made with the `butlers=health` parameter

#### Scenario: Filter by multiple event types

- **WHEN** the user selects `"error"` and `"notification"` in the event type multi-select filter
- **THEN** the timeline MUST display only events where `type` is `"error"` or `"notification"`
- **AND** the URL MUST update to include `?types=error,notification`

#### Scenario: Combine butler and event type filters

- **WHEN** the user selects butler `"health"` and event type `"session"`
- **THEN** the timeline MUST display only session events from the health butler
- **AND** the URL MUST update to include both filter parameters

#### Scenario: Date range filter narrows displayed events

- **WHEN** the user sets the date range to February 1-7, 2026
- **THEN** the timeline MUST display only events with `timestamp` between `2026-02-01T00:00:00Z` and `2026-02-07T23:59:59Z` (inclusive)

#### Scenario: Clearing all filters restores the default view

- **WHEN** the user has active filters and clears them all (or clicks a "Clear filters" control)
- **THEN** the timeline MUST display all event types from all butlers with no date restriction
- **AND** the URL query parameters MUST be removed

---

### Requirement: Auto-refresh

The timeline page SHALL provide an auto-refresh toggle that, when enabled, polls the timeline API every 10 seconds for new events. New events SHALL appear at the top of the stream without disrupting the user's scroll position.

Auto-refresh SHALL be disabled by default. The toggle MUST be clearly visible in the timeline page header or toolbar area.

When auto-refresh is enabled, the poll request SHALL use the `timestamp` of the most recent event currently displayed as a reference to fetch only events newer than it. This avoids re-fetching the entire timeline on each poll.

#### Scenario: Enable auto-refresh

- **WHEN** the user toggles auto-refresh ON
- **THEN** the timeline MUST begin polling the API every 10 seconds
- **AND** the toggle MUST visually indicate the active/enabled state

#### Scenario: New events appear at top during auto-refresh

- **WHEN** auto-refresh is enabled and a new session-complete event occurs in the `health` butler between polls
- **THEN** the next poll MUST fetch the new event
- **AND** the new event MUST appear at the top of the timeline stream
- **AND** the user's current scroll position MUST NOT change (no jarring scroll jumps)

#### Scenario: Auto-refresh respects active filters

- **WHEN** auto-refresh is enabled and the user has filtered to butler `"health"` and type `"session"`
- **THEN** the poll request MUST include the `butlers=health&types=session` parameters
- **AND** only matching new events MUST be appended to the top

#### Scenario: Disable auto-refresh stops polling

- **WHEN** the user toggles auto-refresh OFF
- **THEN** polling MUST stop immediately
- **AND** no further API requests MUST be made until the user manually triggers a refresh or re-enables auto-refresh

#### Scenario: Auto-refresh indicator shows last refresh time

- **WHEN** auto-refresh is enabled and a poll completes
- **THEN** the UI MUST display the time of the last successful refresh (e.g., "Last updated: 10:32:15 AM")

---

### Requirement: Infinite scroll

The timeline page SHALL implement infinite scroll to load older events as the user scrolls down. When the user scrolls near the bottom of the currently loaded events, the page SHALL automatically fetch the next page of events using cursor-based pagination and append them to the bottom of the stream.

The infinite scroll MUST use the `next_cursor` value from the previous API response as the `before` parameter for the next request.

#### Scenario: Scrolling near the bottom triggers a fetch

- **WHEN** the user scrolls within 200 pixels of the bottom of the loaded event list
- **AND** `next_cursor` from the last response is not `null`
- **THEN** the page MUST automatically issue a `GET /api/timeline?before={next_cursor}` request
- **AND** a loading indicator MUST be displayed at the bottom of the list while the request is in progress

#### Scenario: Fetched events are appended to the bottom

- **WHEN** the infinite scroll fetch returns 50 additional events
- **THEN** the events MUST be appended to the bottom of the existing event list
- **AND** the user's current scroll position MUST NOT change
- **AND** `next_cursor` MUST be updated to the value from the new response for subsequent loads

#### Scenario: No more events to load

- **WHEN** the last API response returned `next_cursor: null`
- **THEN** scrolling to the bottom MUST NOT trigger any additional API requests
- **AND** a message such as "No more events" or "You've reached the beginning" MUST be displayed at the bottom of the list

#### Scenario: Infinite scroll works with active filters

- **WHEN** the user has filters applied (e.g., `butlers=health&types=session`) and scrolls to load more events
- **THEN** the infinite scroll request MUST include both the `before` cursor and the active filter parameters
- **AND** only events matching the filters MUST be appended

#### Scenario: Changing filters resets the scroll position

- **WHEN** the user changes a filter while events are loaded via infinite scroll
- **THEN** the timeline MUST reset to the first page (no `before` cursor)
- **AND** the scroll position MUST return to the top
- **AND** the previously loaded events MUST be replaced with the new filtered results

---

### Requirement: Heartbeat tick collapsing

The timeline page SHALL collapse consecutive heartbeat tick events into a single grouped entry for readability.

**Definition:** Heartbeat tick events are timeline events with `type="schedule"` where `data.task_name` matches a heartbeat pattern (e.g., starts with `"heartbeat"` or `"tick"`). Consecutive heartbeat ticks are those that fall within the same 10-minute cycle (i.e., their timestamps are within 10 minutes of each other).

**Collapsing behavior:** The UI SHALL group consecutive heartbeat ticks into a single entry displaying: "Heartbeat: N butlers ticked, M failures" where N is the total number of heartbeat tick events in the group and M is the count of events where `data.last_result` indicates a failure.

**Implementation:** Collapsing is a frontend rendering concern. The `GET /api/timeline` endpoint returns individual events unchanged. The timeline UI component groups heartbeat events before rendering.

The collapsed entry MUST be expandable to reveal the individual tick events with their full details (butler name, result, timestamp).

#### Scenario: Heartbeat ticks within a cycle are collapsed

- **WHEN** the timeline contains 5 heartbeat tick schedule events for butlers `general`, `health`, `relationship`, `switchboard`, `heartbeat` all with timestamps within a 10-minute window, and all succeeded
- **THEN** the timeline MUST display a single collapsed entry: "Heartbeat: 5 butlers ticked, 0 failures"

#### Scenario: Heartbeat ticks with failures

- **WHEN** the timeline contains 4 heartbeat tick events within a 10-minute window, with 1 event having a failed `last_result`
- **THEN** the collapsed entry MUST display: "Heartbeat: 4 butlers ticked, 1 failure"
- **AND** the failure count MUST be styled with a warning/danger visual treatment

#### Scenario: Expanding collapsed heartbeat entry

- **WHEN** the user clicks on a collapsed heartbeat entry
- **THEN** the entry MUST expand to show each individual heartbeat tick event with its butler name, timestamp, and result

#### Scenario: Non-consecutive heartbeat ticks are not collapsed

- **WHEN** heartbeat tick events are separated by more than 10 minutes (i.e., from different cycles)
- **THEN** they MUST be displayed as separate collapsed groups (one per cycle)

#### Scenario: Heartbeat ticks mixed with other events

- **WHEN** the timeline contains a session event between two groups of heartbeat ticks
- **THEN** the session event MUST break the grouping — the heartbeat ticks before and after the session event MUST be separate collapsed entries
