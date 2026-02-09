# Dashboard Notifications

Notification history and monitoring for the Butlers dashboard. All notification data lives in the Switchboard's database in a single `notifications` table with columns: `id` (UUID PK), `source_butler` (TEXT NOT NULL), `channel` (TEXT NOT NULL, one of 'telegram', 'email'), `recipient` (TEXT), `message` (TEXT NOT NULL), `metadata` (JSONB DEFAULT '{}'), `status` (TEXT DEFAULT 'sent', one of 'sent', 'failed', 'pending'), `error` (TEXT), `session_id` (UUID), `trace_id` (TEXT), `created_at` (TIMESTAMPTZ DEFAULT now()). Indexes exist on `(source_butler, created_at DESC)`, `(channel, created_at DESC)`, and `(status)`.

## ADDED Requirements

### Requirement: Paginated notification history API

The dashboard API SHALL expose `GET /api/notifications` which returns a paginated list of notifications from the Switchboard database, ordered by `created_at` descending.

The endpoint SHALL accept the following query parameters:
- `limit` (integer, default 20) -- maximum number of notifications to return
- `offset` (integer, default 0) -- number of notifications to skip for pagination
- `butler` (string, optional) -- filter by `source_butler`
- `channel` (string, optional) -- filter by `channel` (e.g., 'telegram', 'email')
- `status` (string, optional) -- filter by `status` (e.g., 'sent', 'failed', 'pending')
- `from` (ISO 8601 timestamp, optional) -- include only notifications with `created_at >= from`
- `to` (ISO 8601 timestamp, optional) -- include only notifications with `created_at <= to`

Each notification object in the response MUST include: `id`, `source_butler`, `channel`, `recipient`, `message`, `status`, `error`, `created_at`, and `metadata`.

#### Scenario: Fetch notifications with default pagination

- **WHEN** `GET /api/notifications` is called with no query parameters
- **THEN** the API MUST return at most 20 notifications ordered by `created_at` descending
- **AND** each notification object MUST include `id`, `source_butler`, `channel`, `recipient`, `message`, `status`, `error`, `created_at`, and `metadata`

#### Scenario: Filter notifications by butler and channel

- **WHEN** `GET /api/notifications?butler=health&channel=telegram` is called
- **THEN** the API MUST return only notifications where `source_butler` equals `"health"` AND `channel` equals `"telegram"`

#### Scenario: Filter notifications by status and date range

- **WHEN** `GET /api/notifications?status=failed&from=2026-02-01T00:00:00Z&to=2026-02-07T23:59:59Z` is called
- **THEN** the API MUST return only notifications where `status` equals `"failed"` AND `created_at` is between the specified timestamps (inclusive)

#### Scenario: Paginate through notifications

- **WHEN** `GET /api/notifications?limit=10&offset=30` is called
- **THEN** the API MUST skip the first 30 notifications (by `created_at` descending) and return at most 10 notifications

#### Scenario: No notifications match the filters

- **WHEN** `GET /api/notifications?butler=nonexistent` is called and no notifications exist for that butler
- **THEN** the API MUST return an empty list
- **AND** the response status MUST be 200

---

### Requirement: Notification statistics API

The dashboard API SHALL expose `GET /api/notifications/stats` which returns an aggregate summary of notification activity from the Switchboard database.

The response MUST include:
- `total_sent_today` (integer) -- count of notifications with `status = 'sent'` and `created_at` on the current UTC day
- `failure_rate` (float, percentage) -- `(count of status='failed') / (total count)` over the current UTC day, expressed as a percentage rounded to one decimal place; 0.0 if no notifications exist today
- `by_butler` (object) -- keys are `source_butler` values, values are the count of notifications from that butler for the current UTC day
- `by_channel` (object) -- keys are `channel` values, values are the count of notifications on that channel for the current UTC day

#### Scenario: Stats with normal activity

- **WHEN** `GET /api/notifications/stats` is called and today's notifications include 45 sent via telegram from the health butler, 10 sent via email from the relationship butler, and 5 failed via telegram from the health butler
- **THEN** the response MUST include `total_sent_today` equal to 55
- **AND** `failure_rate` MUST equal 8.3 (5 failures out of 60 total, rounded to one decimal)
- **AND** `by_butler` MUST include `{"health": 50, "relationship": 10}`
- **AND** `by_channel` MUST include `{"telegram": 50, "email": 10}`

#### Scenario: Stats with no notifications today

- **WHEN** `GET /api/notifications/stats` is called and no notifications have been created on the current UTC day
- **THEN** `total_sent_today` MUST equal 0
- **AND** `failure_rate` MUST equal 0.0
- **AND** `by_butler` MUST be an empty object
- **AND** `by_channel` MUST be an empty object

#### Scenario: Stats failure rate with all failures

- **WHEN** `GET /api/notifications/stats` is called and today's notifications include 0 sent and 12 failed
- **THEN** `failure_rate` MUST equal 100.0

---

### Requirement: Butler-scoped notification list API

The dashboard API SHALL expose `GET /api/butlers/:name/notifications` which returns a paginated list of notifications filtered to a specific source butler from the Switchboard database, ordered by `created_at` descending.

The endpoint SHALL accept the same query parameters as `GET /api/notifications` except `butler` (which is implicit from the URL path): `limit`, `offset`, `channel`, `status`, `from`, `to`.

#### Scenario: Fetch notifications for a specific butler

- **WHEN** `GET /api/butlers/health/notifications` is called with no query parameters
- **THEN** the API MUST return at most 20 notifications where `source_butler` equals `"health"`, ordered by `created_at` descending
- **AND** each notification object MUST include `id`, `source_butler`, `channel`, `recipient`, `message`, `status`, `error`, `created_at`, and `metadata`

#### Scenario: Filter single-butler notifications by channel and status

- **WHEN** `GET /api/butlers/relationship/notifications?channel=email&status=sent` is called
- **THEN** the API MUST return only notifications where `source_butler` equals `"relationship"` AND `channel` equals `"email"` AND `status` equals `"sent"`

#### Scenario: Butler has no notifications

- **WHEN** `GET /api/butlers/switchboard/notifications` is called and no notifications exist with `source_butler = 'switchboard'`
- **THEN** the API MUST return an empty list
- **AND** the response status MUST be 200

---

### Requirement: Notifications page with reverse-chronological feed

The frontend SHALL render a notifications page at `/notifications` displaying a reverse-chronological feed of all notifications aggregated from the Switchboard database.

Each notification entry in the feed MUST display:
- **Timestamp** -- `created_at` formatted as a human-readable date and time
- **Source butler** -- butler name displayed as a colored badge
- **Channel icon** -- a distinct icon for each channel type (telegram icon for 'telegram', email icon for 'email')
- **Message text** -- the notification `message` content
- **Delivery status badge** -- `sent` displayed as a green badge, `failed` displayed as a red badge, `pending` displayed as a yellow badge

Failed notifications MUST be visually highlighted (e.g., red border or background tint) and MUST display the `error` text inline beneath the message.

Clicking a notification entry MUST open an expanded view displaying:
- Full message text (untruncated)
- Complete `metadata` JSONB rendered as formatted key-value pairs
- Linked session: if `session_id` is non-null, a clickable link navigating to the session detail view for that session

#### Scenario: Notifications page loads with default view

- **WHEN** a user navigates to `/notifications`
- **THEN** the page MUST display the notification feed with the first page of results sorted by `created_at` descending
- **AND** each entry MUST show the timestamp, source butler badge, channel icon, message text, and delivery status badge

#### Scenario: Failed notification is highlighted with error details

- **WHEN** the feed contains a notification with `status = 'failed'` and `error = 'SMTP connection timeout'`
- **THEN** that notification entry MUST be visually highlighted with error styling (red border or background tint)
- **AND** the error text `"SMTP connection timeout"` MUST be displayed beneath the message text

#### Scenario: Expanding a notification with a linked session

- **WHEN** a user clicks on a notification entry that has `session_id = 'abc-123-uuid'` and `metadata = {"template": "daily_digest", "retry_count": 2}`
- **THEN** an expanded view MUST display the full message text
- **AND** the metadata MUST be rendered showing `template: daily_digest` and `retry_count: 2`
- **AND** a clickable session link MUST be displayed that navigates to the session detail for `abc-123-uuid`

#### Scenario: Expanding a notification with no linked session

- **WHEN** a user clicks on a notification entry that has `session_id = null`
- **THEN** the expanded view MUST NOT display a session link
- **AND** a dash or "No linked session" text MUST be shown instead

#### Scenario: Paginating through the feed

- **WHEN** the notification feed shows 20 results and the user scrolls to the bottom or clicks the next page control
- **THEN** the page MUST fetch and display the next page of notifications

---

### Requirement: Notification filter controls

The notifications page at `/notifications` SHALL provide filter controls that allow the user to narrow the displayed notifications.

The following filters MUST be available:
- **Source butler** -- dropdown or multi-select listing all butlers that have sent notifications
- **Channel** -- dropdown or multi-select with options 'telegram' and 'email'
- **Status** -- dropdown or multi-select with options 'sent', 'failed', and 'pending'
- **Date range** -- from/to date-time pickers

Applying any combination of filters MUST update the displayed feed to show only matching notifications. Filter state SHOULD be reflected in URL query parameters to support bookmarking and sharing.

#### Scenario: Filter by source butler and channel

- **WHEN** a user selects butler `"health"` from the source butler filter and `"telegram"` from the channel filter
- **THEN** the feed MUST update to show only notifications where `source_butler = 'health'` AND `channel = 'telegram'`
- **AND** the URL query parameters SHOULD update to include `butler=health&channel=telegram`

#### Scenario: Filter by status

- **WHEN** a user selects `"failed"` from the status filter
- **THEN** the feed MUST update to show only notifications with `status = 'failed'`
- **AND** all displayed entries MUST have a red delivery status badge

#### Scenario: Filter by date range

- **WHEN** a user sets the date range from February 1, 2026 to February 7, 2026
- **THEN** the feed MUST show only notifications with `created_at` between those dates (inclusive)

#### Scenario: Clear all filters

- **WHEN** a user clears all applied filters (e.g., via a "Clear filters" button or by resetting each control)
- **THEN** the feed MUST return to showing the unfiltered reverse-chronological list of all notifications

---

### Requirement: Notification statistics bar

The notifications page at `/notifications` SHALL display a statistics bar above the notification feed, summarizing current notification activity.

The statistics bar MUST display:
- **Total sent today** -- count of notifications with `status = 'sent'` for the current UTC day
- **Failure rate** -- percentage of today's notifications that have `status = 'failed'`, rounded to one decimal place
- **Most active butler** -- the `source_butler` with the highest notification count for the current UTC day, or "N/A" if no notifications today
- **Most used channel** -- the `channel` with the highest notification count for the current UTC day, or "N/A" if no notifications today

The statistics bar MUST update when the page loads and SHOULD refresh if the user applies or clears filters (the stats always reflect the full unfiltered day, not the filtered subset).

#### Scenario: Stats bar displays summary data

- **WHEN** a user navigates to `/notifications` and today has 120 sent notifications, 8 failed notifications, the health butler sent 80 and the relationship butler sent 48, and 100 were via telegram and 28 via email
- **THEN** the stats bar MUST display total sent today as 120
- **AND** failure rate as 6.3% (8 out of 128 total)
- **AND** most active butler as "health"
- **AND** most used channel as "telegram"

#### Scenario: Stats bar with no activity today

- **WHEN** a user navigates to `/notifications` and no notifications have been created on the current UTC day
- **THEN** the stats bar MUST display total sent today as 0
- **AND** failure rate as 0.0%
- **AND** most active butler as "N/A"
- **AND** most used channel as "N/A"

---

### Requirement: Butler detail recent notifications section

The butler detail page's overview tab SHALL include a "Recent notifications" section that displays the last 5 notifications sent by that butler, ordered by `created_at` descending.

Each notification entry in this section MUST display the timestamp, channel icon, message text (truncated if necessary), and delivery status badge.

If a butler has no notifications, the section MUST display an empty state message (e.g., "No notifications sent by this butler").

#### Scenario: Butler overview shows recent notifications

- **WHEN** a user navigates to the `health` butler's overview tab and the health butler has sent 12 notifications
- **THEN** the "Recent notifications" section MUST display exactly the 5 most recent notifications from the health butler, ordered by `created_at` descending
- **AND** each entry MUST show the timestamp, channel icon, truncated message text, and delivery status badge

#### Scenario: Butler has fewer than 5 notifications

- **WHEN** a user views the `relationship` butler's overview tab and the relationship butler has sent only 2 notifications
- **THEN** the "Recent notifications" section MUST display exactly those 2 notifications

#### Scenario: Butler has no notifications

- **WHEN** a user views a butler's overview tab and that butler has sent no notifications
- **THEN** the "Recent notifications" section MUST display an empty state message such as "No notifications sent by this butler"

#### Scenario: Failed notification in recent section

- **WHEN** one of the 5 most recent notifications has `status = 'failed'`
- **THEN** that entry MUST display a red delivery status badge
- **AND** the entry MUST be visually distinguishable from successful notifications (e.g., red tint or error indicator)

---

### Requirement: Overview page failed notification integration

The dashboard overview page's Issues panel SHALL surface failed notification deliveries. Any notification with `status = 'failed'` that was created within the last 24 hours MUST appear as an issue entry in the Issues panel.

Each failed notification issue entry MUST display:
- The source butler name
- The channel that failed (telegram or email)
- The error message
- The timestamp of the failure

Failed notification issues MUST be ordered by `created_at` descending (most recent failure first).

#### Scenario: Failed notifications appear in Issues panel

- **WHEN** a user views the dashboard overview page and 3 notifications have `status = 'failed'` within the last 24 hours
- **THEN** the Issues panel MUST include all 3 failed notifications as issue entries
- **AND** each entry MUST display the source butler name, the failed channel, the error message, and the failure timestamp

#### Scenario: No failed notifications in the last 24 hours

- **WHEN** a user views the dashboard overview page and no notifications have `status = 'failed'` within the last 24 hours
- **THEN** the Issues panel MUST NOT contain any notification failure entries

#### Scenario: Old failures are excluded

- **WHEN** a notification with `status = 'failed'` has `created_at` more than 24 hours ago
- **THEN** that notification MUST NOT appear in the Issues panel

#### Scenario: Mixed issues in the panel

- **WHEN** the Issues panel contains both failed notifications and other issue types (e.g., health check failures)
- **THEN** failed notification entries MUST be visually distinguishable from other issue types (e.g., via a notification-specific icon or label)
