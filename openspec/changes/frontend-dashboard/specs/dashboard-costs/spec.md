# Dashboard Costs

Token usage and cost tracking for the Butlers dashboard. Provides aggregate cost summaries, daily time series, top-session rankings, and per-schedule cost analysis across all five butlers (Switchboard, General, Relationship, Health, Heartbeat).

Cost is derived at query time from the `sessions` table columns `input_tokens`, `output_tokens`, and `model`. The formula is: `input_tokens * input_price + output_tokens * output_price`, where per-model pricing is loaded from a `pricing.toml` configuration file at API startup. Cost is never stored in the database.

## ADDED Requirements

### Requirement: Cost summary API

The dashboard API SHALL expose `GET /api/costs/summary` which returns aggregate cost data across all butler databases.

The response MUST include:
- `today` -- total estimated cost for sessions with `started_at` on the current calendar day (UTC)
- `last_7d` -- total estimated cost for sessions with `started_at` within the last 7 days
- `last_30d` -- total estimated cost for sessions with `started_at` within the last 30 days
- `by_butler` -- an array of per-butler breakdowns, each containing `butler` (string), `today` (number or null), `last_7d` (number or null), `last_30d` (number or null), `input_tokens` (total), and `output_tokens` (total)

The endpoint SHALL query sessions from all five butler databases via concurrent fan-out queries and merge the results. Sessions without token data (null `input_tokens` or `output_tokens`) MUST be excluded from cost totals but MUST still be counted in session counts.

#### Scenario: Fetch cost summary with sessions across all butlers

- **WHEN** `GET /api/costs/summary` is called and all five butler databases contain sessions with token data
- **THEN** the API MUST return `today`, `last_7d`, and `last_30d` totals computed as the sum of `(input_tokens * input_price + output_tokens * output_price)` for each session, grouped by the session's `model`
- **AND** the `by_butler` array MUST contain exactly 5 entries, one per butler, each with that butler's individual cost totals and token counts

#### Scenario: Butler with no sessions today

- **WHEN** `GET /api/costs/summary` is called and the `heartbeat` butler has no sessions with `started_at` on the current day
- **THEN** the `heartbeat` entry in `by_butler` MUST have `today` set to `0`
- **AND** the `last_7d` and `last_30d` values MUST still reflect any sessions within those respective windows

#### Scenario: Sessions with missing token data excluded from cost

- **WHEN** `GET /api/costs/summary` is called and some sessions have null `input_tokens` or `output_tokens`
- **THEN** those sessions MUST NOT contribute to any cost totals
- **AND** the response status MUST be 200

---

### Requirement: Daily cost time series API

The dashboard API SHALL expose `GET /api/costs/daily` which returns a daily cost time series suitable for charting.

The endpoint SHALL accept the following query parameters:
- `from` (ISO 8601 date, required) -- start date (inclusive)
- `to` (ISO 8601 date, required) -- end date (inclusive)

The response MUST be an array of objects ordered by date ascending, each containing:
- `date` -- the calendar date in `YYYY-MM-DD` format
- `cost` -- total estimated cost for that date across all butlers
- `butler_breakdown` -- an object mapping butler names to their individual cost for that date

Days with no sessions MUST still appear in the response with `cost` set to `0` and all butler values set to `0`.

#### Scenario: Fetch daily costs for a 7-day range

- **WHEN** `GET /api/costs/daily?from=2026-02-01&to=2026-02-07` is called
- **THEN** the API MUST return an array of exactly 7 objects, one per day from February 1 to February 7
- **AND** each object MUST include `date`, `cost`, and `butler_breakdown` with entries for all five butlers
- **AND** the array MUST be sorted by `date` ascending

#### Scenario: Date range with no sessions on some days

- **WHEN** `GET /api/costs/daily?from=2026-02-01&to=2026-02-03` is called and no sessions exist on February 2
- **THEN** the February 2 entry MUST have `cost` set to `0`
- **AND** the `butler_breakdown` for February 2 MUST have all five butler values set to `0`

#### Scenario: Missing required query parameters

- **WHEN** `GET /api/costs/daily` is called without `from` or `to` query parameters
- **THEN** the API MUST return a 400 response with an error message indicating the missing parameters

---

### Requirement: Top sessions by cost API

The dashboard API SHALL expose `GET /api/costs/top-sessions` which returns the most expensive sessions ranked by estimated cost.

The endpoint SHALL accept the following query parameter:
- `limit` (integer, optional, default 10) -- maximum number of sessions to return

Each session object in the response MUST include: `id`, `butler` (string), `trigger_source`, `started_at`, `model`, `input_tokens`, `output_tokens`, `estimated_cost`, and `duration_ms`. The results MUST be sorted by `estimated_cost` descending.

Sessions with null token data MUST be excluded from the results since their cost cannot be computed.

#### Scenario: Fetch top 10 most expensive sessions

- **WHEN** `GET /api/costs/top-sessions` is called with no query parameters
- **THEN** the API MUST query all butler databases, compute the estimated cost for each session with available token data, and return the top 10 sessions sorted by `estimated_cost` descending
- **AND** each session MUST include a `butler` field identifying which butler owns the session

#### Scenario: Fetch top 3 most expensive sessions

- **WHEN** `GET /api/costs/top-sessions?limit=3` is called
- **THEN** the API MUST return at most 3 sessions sorted by `estimated_cost` descending

#### Scenario: Sessions without token data excluded

- **WHEN** `GET /api/costs/top-sessions` is called and some sessions have null `input_tokens` or `output_tokens`
- **THEN** those sessions MUST NOT appear in the results
- **AND** the ranking MUST be based only on sessions with complete token data

---

### Requirement: Per-schedule cost analysis API

The dashboard API SHALL expose `GET /api/costs/by-schedule` which returns per-scheduled-task average cost and projected monthly spend.

The endpoint SHALL join sessions by `trigger_source` to identify schedule-triggered sessions and compute, for each distinct `trigger_source` value:
- `trigger_source` -- the schedule identifier
- `butler` -- the butler that owns the sessions
- `session_count` -- total number of sessions with that trigger source in the last 30 days
- `avg_cost` -- average estimated cost per session (excluding sessions with null token data)
- `total_cost_30d` -- total estimated cost for the last 30 days
- `projected_monthly` -- projected monthly spend computed as `(total_cost_30d / days_elapsed_in_window) * 30`

#### Scenario: Fetch per-schedule cost breakdown

- **WHEN** `GET /api/costs/by-schedule` is called and the `health` butler has 60 sessions triggered by `"tick"` in the last 30 days with an average cost of $0.02 each
- **THEN** the response MUST include an entry with `trigger_source` set to `"tick"`, `butler` set to `"health"`, `session_count` set to `60`, `avg_cost` approximately `0.02`, and `total_cost_30d` approximately `1.20`
- **AND** `projected_monthly` MUST be computed based on the rate of sessions over the elapsed window

#### Scenario: Schedule with sessions missing token data

- **WHEN** `GET /api/costs/by-schedule` is called and a trigger source has 10 sessions total but only 7 have complete token data
- **THEN** the `session_count` MUST be `10` (total sessions)
- **AND** the `avg_cost` MUST be computed using only the 7 sessions with complete token data

#### Scenario: No schedule-triggered sessions exist

- **WHEN** `GET /api/costs/by-schedule` is called and no sessions exist in any butler database
- **THEN** the API MUST return an empty array
- **AND** the response status MUST be 200

---

### Requirement: Pricing configuration via pricing.toml

The dashboard API SHALL load per-model token pricing from a `pricing.toml` configuration file at startup. The pricing configuration MUST NOT be stored in the database.

The `pricing.toml` file SHALL map model identifiers to pricing objects with the following structure:
- `input` -- price per input token (decimal number)
- `output` -- price per output token (decimal number)

The API SHALL use this pricing data to compute estimated costs at query time. If a session's `model` value does not exist in the pricing configuration, the estimated cost for that session MUST be null.

#### Scenario: Pricing config loaded at startup

- **WHEN** the dashboard API starts and `pricing.toml` contains an entry `[claude-sonnet-4-20250514]` with `input = 0.000003` and `output = 0.000015`
- **THEN** all cost computations for sessions with `model = "claude-sonnet-4-20250514"` MUST use those prices

#### Scenario: Unknown model falls back to null cost

- **WHEN** a session has `model = "unknown-model-v1"` and `pricing.toml` does not contain an entry for `"unknown-model-v1"`
- **THEN** the estimated cost for that session MUST be null
- **AND** the session's token counts MUST still be returned normally

#### Scenario: Pricing config updated without restart

- **WHEN** the operator modifies `pricing.toml` to add a new model or change an existing price
- **THEN** the dashboard API MUST reflect the updated prices on subsequent requests after a config reload
- **AND** no database migration SHALL be required

---

### Requirement: Cost estimation logic

All cost estimation across the dashboard SHALL use the formula: `cost = input_tokens * input_price + output_tokens * output_price`, where `input_price` and `output_price` are looked up from the pricing configuration by the session's `model` value.

Sessions where `input_tokens` or `output_tokens` is null MUST return null for estimated cost. No partial cost calculation SHALL be attempted.

#### Scenario: Standard cost computation

- **WHEN** a session has `input_tokens = 2000`, `output_tokens = 800`, and `model = "claude-sonnet-4-20250514"`
- **AND** the pricing config specifies input price as `0.000003` per token and output price as `0.000015` per token
- **THEN** the estimated cost MUST be `(2000 * 0.000003) + (800 * 0.000015) = 0.006 + 0.012 = 0.018`

#### Scenario: Null input tokens yields null cost

- **WHEN** a session has `input_tokens = null`, `output_tokens = 500`, and a valid model
- **THEN** the estimated cost MUST be null
- **AND** no partial calculation using only output tokens SHALL be performed

#### Scenario: Null output tokens yields null cost

- **WHEN** a session has `input_tokens = 1000`, `output_tokens = null`, and a valid model
- **THEN** the estimated cost MUST be null

#### Scenario: Both tokens null yields null cost

- **WHEN** a session has `input_tokens = null` and `output_tokens = null`
- **THEN** the estimated cost MUST be null

---

### Requirement: Costs page with charts and tables

The frontend SHALL render a costs page at `/costs` displaying a comprehensive cost analysis dashboard.

The page MUST contain the following sections:

1. **Spend area chart** -- a stacked area chart (Recharts) showing daily cost over the selected time range (daily, weekly, or monthly), stacked by butler. Each butler MUST be represented by a distinct color. The time range SHALL be selectable via toggle buttons (7d, 30d, 90d).
2. **Butler breakdown table** -- a table showing each butler's total cost for the selected period, percentage of total spend, total input tokens, total output tokens, and session count. The table MUST be sorted by total cost descending.
3. **Top expensive sessions table** -- a table showing the most expensive sessions with columns: timestamp, butler, trigger source, model, tokens (input + output), estimated cost, and duration. The table MUST display 10 sessions by default.
4. **Per-schedule cost analysis** -- a table showing each scheduled task's trigger source, butler, session count, average cost per session, total 30-day cost, and projected monthly spend. The table MUST be sorted by projected monthly spend descending.

#### Scenario: Costs page loads with default 30-day view

- **WHEN** a user navigates to `/costs`
- **THEN** the page MUST display the spend area chart with 30 days of data stacked by butler
- **AND** the butler breakdown table MUST show cost totals for the last 30 days
- **AND** the top expensive sessions table MUST show the 10 most expensive sessions
- **AND** the per-schedule cost analysis table MUST be populated

#### Scenario: User switches time range to 7 days

- **WHEN** the user clicks the "7d" toggle on the costs page
- **THEN** the spend area chart MUST update to show only the last 7 days of data
- **AND** the butler breakdown table MUST update to reflect 7-day totals

#### Scenario: Stacked area chart shows butler distinction

- **WHEN** the costs page renders the spend area chart with data from multiple butlers
- **THEN** each butler MUST be represented by a distinct color in the stacked area
- **AND** hovering over a data point MUST display a tooltip showing the date, total cost, and per-butler cost breakdown

#### Scenario: Empty state when no cost data exists

- **WHEN** a user navigates to `/costs` and no sessions with token data exist
- **THEN** the page MUST display an empty state message (e.g., "No cost data available yet")
- **AND** the charts and tables MUST render gracefully without errors

---

### Requirement: Cost widget on overview page

The frontend SHALL render a cost summary widget on the dashboard overview page displaying today's spend, a 7-day sparkline, and the top spender butler.

The widget MUST include:
- **Today's spend** -- the total estimated cost for all sessions today, formatted as a currency value (e.g., "$0.42")
- **7-day sparkline** -- a small inline chart showing daily cost for the last 7 days
- **Top spender** -- the butler name with the highest cost in the last 7 days, displayed as a colored badge

#### Scenario: Overview page renders cost widget with data

- **WHEN** a user navigates to the overview page and sessions exist with token data
- **THEN** the cost widget MUST display today's total spend as a formatted currency value
- **AND** the 7-day sparkline MUST render a small line chart with 7 data points
- **AND** the top spender MUST display the butler name that incurred the highest cost in the last 7 days

#### Scenario: Cost widget shows zero when no sessions today

- **WHEN** a user navigates to the overview page and no sessions have occurred today
- **THEN** the cost widget MUST display "$0.00" for today's spend
- **AND** the sparkline MUST still render with historical data for the prior 6 days

#### Scenario: Cost widget handles all butlers having zero cost

- **WHEN** no sessions with token data exist in the last 7 days
- **THEN** the cost widget MUST display "$0.00" for today's spend
- **AND** the sparkline MUST render as a flat line at zero
- **AND** the top spender section MUST display a dash or "N/A"

---

### Requirement: Cost card on butler detail overview tab

The frontend SHALL render a cost summary card on each butler's detail page overview tab displaying that butler's session count today, tokens used, estimated cost, and a 7-day trend.

The card MUST include:
- **Sessions today** -- count of sessions with `started_at` on the current day
- **Tokens used today** -- total `input_tokens + output_tokens` for today's sessions
- **Estimated cost today** -- total estimated cost for today's sessions, formatted as currency
- **7-day trend** -- a sparkline or small chart showing the butler's daily cost for the last 7 days

#### Scenario: Butler detail page shows cost card with data

- **WHEN** a user navigates to the `health` butler's detail page and the `health` butler has 5 sessions today totaling 15,000 input tokens and 3,000 output tokens
- **THEN** the cost card MUST display "5" for sessions today
- **AND** tokens used MUST display "18,000" (formatted with comma separator)
- **AND** estimated cost MUST be computed from the token counts using the pricing config for each session's model
- **AND** the 7-day trend MUST render a sparkline with 7 data points for the `health` butler only

#### Scenario: Butler with no sessions today

- **WHEN** a user navigates to the `switchboard` butler's detail page and the `switchboard` butler has no sessions today
- **THEN** the cost card MUST display "0" for sessions today, "0" for tokens used, and "$0.00" for estimated cost
- **AND** the 7-day trend MUST still render with historical data

#### Scenario: Butler sessions span multiple models

- **WHEN** the `general` butler has sessions today using both `claude-sonnet-4-20250514` and `claude-opus-4-20250514`
- **THEN** the estimated cost MUST be computed by applying the correct pricing for each session's respective model and summing the results

---

### Requirement: Cost anomaly detection

The dashboard SHALL flag sessions whose estimated cost exceeds 3 times the owning butler's 7-day rolling average session cost. Flagged sessions MUST be visually distinguished with an anomaly badge.

The 7-day rolling average SHALL be computed as: total estimated cost of the butler's sessions in the last 7 days divided by the number of sessions with valid cost data in that period. Sessions without token data MUST be excluded from the average calculation.

#### Scenario: Session cost exceeds 3x the 7-day average

- **WHEN** the `general` butler's 7-day average session cost is $0.02 and a session has an estimated cost of $0.08
- **THEN** the session MUST be flagged as an anomaly because `0.08 > 3 * 0.02`
- **AND** the session MUST display an anomaly badge (e.g., a warning icon or colored label) in all session tables and the session detail drawer

#### Scenario: Session cost is exactly 3x the average

- **WHEN** the `general` butler's 7-day average session cost is $0.02 and a session has an estimated cost of $0.06
- **THEN** the session MUST NOT be flagged as an anomaly because the threshold is strictly greater than 3x

#### Scenario: Session cost is below the anomaly threshold

- **WHEN** the `health` butler's 7-day average session cost is $0.05 and a session has an estimated cost of $0.10
- **THEN** the session MUST NOT be flagged as an anomaly because `0.10 < 3 * 0.05 = 0.15`

#### Scenario: Butler with no prior sessions has no baseline for anomaly detection

- **WHEN** a butler has no sessions with valid cost data in the last 7 days and a new session arrives
- **THEN** the new session MUST NOT be flagged as an anomaly (no baseline exists)
- **AND** anomaly detection for that butler MUST begin once at least one session with valid cost data exists in the 7-day window

#### Scenario: Anomaly badge displayed in top sessions table

- **WHEN** the top expensive sessions table on the `/costs` page includes a session flagged as an anomaly
- **THEN** that session's row MUST display the anomaly badge alongside the cost value

#### Scenario: Anomaly badge displayed in session detail drawer

- **WHEN** a user opens the session detail drawer for an anomaly-flagged session
- **THEN** the drawer header MUST display the anomaly badge next to the cost information
