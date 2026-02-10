# Dashboard Health

Health butler domain views in the dashboard. Provides read-only API endpoints for browsing health data (measurements, medications, conditions, symptoms, meals, research) via direct database reads against the `butler_health` database, and a set of frontend pages for visualizing and exploring that data.

All endpoints follow the dual data-access pattern (D1): direct DB reads for browsing, no write operations. The health butler's database contains the following tables: `measurements`, `medications`, `medication_doses`, `conditions`, `symptoms`, `meals`, and `research`.

> **Note:** Write operations (e.g., logging new measurements) are intentionally deferred for v1. Health data entry is handled via chat interactions with the Health butler. Dashboard health views are read-only.

## ADDED Requirements

### Requirement: Measurements list API

The dashboard API SHALL expose `GET /api/butlers/health/measurements` which returns a paginated list of measurement records from the health butler's `measurements` table via a direct database read.

The endpoint SHALL accept the following query parameters:
- `type` (string, optional) -- filter by measurement type (e.g., `weight`, `blood_pressure`, `heart_rate`, `blood_glucose`)
- `from` (ISO 8601 timestamp, optional) -- include only measurements with `measured_at >= from`
- `to` (ISO 8601 timestamp, optional) -- include only measurements with `measured_at <= to`
- `limit` (integer, default 100) -- maximum number of records to return
- `offset` (integer, default 0) -- number of records to skip for pagination

The response SHALL be a JSON object containing:
- `items` (array) -- measurement records, each including `id`, `type`, `value`, `unit`, `details`, `notes`, `measured_at`, `created_at`
- `total` (integer) -- total count of matching records (for pagination UI)

Results SHALL be ordered by `measured_at` descending.

#### Scenario: Fetch all measurements with default pagination

- **WHEN** `GET /api/butlers/health/measurements` is called with no query parameters
- **THEN** the API MUST return at most 100 measurements ordered by `measured_at` descending
- **AND** each measurement object MUST include `id`, `type`, `value`, `unit`, `details`, `notes`, `measured_at`, `created_at`
- **AND** the response MUST include a `total` count of all measurements

#### Scenario: Filter measurements by type

- **WHEN** `GET /api/butlers/health/measurements?type=weight` is called
- **THEN** the API MUST return only measurements where `type` equals `"weight"`
- **AND** the `total` count MUST reflect only weight measurements

#### Scenario: Filter measurements by date range

- **WHEN** `GET /api/butlers/health/measurements?from=2026-01-01T00:00:00Z&to=2026-01-31T23:59:59Z` is called
- **THEN** the API MUST return only measurements with `measured_at` between the specified timestamps (inclusive)

#### Scenario: Filter measurements by type and date range combined

- **WHEN** `GET /api/butlers/health/measurements?type=blood_pressure&from=2026-02-01T00:00:00Z&to=2026-02-07T23:59:59Z` is called
- **THEN** the API MUST return only blood pressure measurements within the specified date range

#### Scenario: Paginate through measurements

- **WHEN** `GET /api/butlers/health/measurements?limit=20&offset=40` is called
- **THEN** the API MUST skip the first 40 matching measurements and return at most 20

#### Scenario: No measurements match the filters

- **WHEN** `GET /api/butlers/health/measurements?type=blood_glucose` is called and no blood glucose measurements exist
- **THEN** the API MUST return an empty `items` array and `total` of 0
- **AND** the response status MUST be 200

---

### Requirement: Medications list API

The dashboard API SHALL expose `GET /api/butlers/health/medications` which returns a list of medication records from the health butler's `medications` table via a direct database read.

The endpoint SHALL accept the following query parameter:
- `active` (boolean, optional) -- when `true`, return only medications where `active = true`; when `false`, return only inactive medications; when omitted, return all medications

Each medication object in the response MUST include `id`, `name`, `dosage`, `frequency`, `schedule_times`, `active`, `prescribed_at`, `notes`, `created_at`.

Results SHALL be ordered by `name` ascending.

#### Scenario: Fetch all medications with no filter

- **WHEN** `GET /api/butlers/health/medications` is called with no query parameters
- **THEN** the API MUST return all medications (both active and inactive) ordered by `name` ascending
- **AND** each medication object MUST include `id`, `name`, `dosage`, `frequency`, `schedule_times`, `active`, `prescribed_at`, `notes`, `created_at`

#### Scenario: Fetch only active medications

- **WHEN** `GET /api/butlers/health/medications?active=true` is called
- **THEN** the API MUST return only medications where `active` is `true`

#### Scenario: Fetch only inactive medications

- **WHEN** `GET /api/butlers/health/medications?active=false` is called
- **THEN** the API MUST return only medications where `active` is `false`

#### Scenario: No medications exist

- **WHEN** `GET /api/butlers/health/medications` is called and the `medications` table is empty
- **THEN** the API MUST return an empty array
- **AND** the response status MUST be 200

---

### Requirement: Medication doses list API

The dashboard API SHALL expose `GET /api/butlers/health/medications/:id/doses` which returns a paginated list of dose records for a specific medication from the health butler's `medication_doses` table via a direct database read.

The endpoint SHALL accept the following query parameters:
- `from` (ISO 8601 timestamp, optional) -- include only doses with `taken_at >= from` (or `scheduled_for >= from` when `taken_at` is null)
- `to` (ISO 8601 timestamp, optional) -- include only doses with `taken_at <= to` (or `scheduled_for <= to` when `taken_at` is null)
- `limit` (integer, default 50) -- maximum number of records to return
- `offset` (integer, default 0) -- number of records to skip for pagination

Each dose object in the response MUST include `id`, `medication_id`, `status`, `taken_at`, `scheduled_for`, `notes`, `created_at`.

The response SHALL also include an `adherence` object containing:
- `total_doses` (integer) -- total dose records matching the filters for this medication
- `taken_count` (integer) -- count of doses with `status = 'taken'`
- `skipped_count` (integer) -- count of doses with `status = 'skipped'`
- `late_count` (integer) -- count of doses with `status = 'late'`
- `adherence_pct` (number) -- percentage of non-skipped doses (`(taken_count + late_count) / total_doses * 100`), or `null` if `total_doses` is 0

Results SHALL be ordered by `taken_at` descending (falling back to `scheduled_for` descending when `taken_at` is null).

#### Scenario: Fetch dose log for a medication

- **WHEN** `GET /api/butlers/health/medications/abc-123-uuid/doses` is called with a valid medication ID
- **THEN** the API MUST return at most 50 dose records for that medication ordered by `taken_at` descending
- **AND** the response MUST include an `adherence` object with counts and percentage

#### Scenario: Filter doses by date range

- **WHEN** `GET /api/butlers/health/medications/abc-123-uuid/doses?from=2026-02-01T00:00:00Z&to=2026-02-07T23:59:59Z` is called
- **THEN** the API MUST return only doses within the specified date range
- **AND** the `adherence` object MUST be computed only from doses within that range

#### Scenario: Medication has no doses

- **WHEN** `GET /api/butlers/health/medications/abc-123-uuid/doses` is called and no doses exist for that medication
- **THEN** the API MUST return an empty items list
- **AND** the `adherence` object MUST have `total_doses = 0` and `adherence_pct = null`

#### Scenario: Medication ID does not exist

- **WHEN** `GET /api/butlers/health/medications/nonexistent-uuid/doses` is called and no medication with that ID exists
- **THEN** the API MUST return a 404 response with an error message indicating the medication was not found

#### Scenario: Adherence calculation with mixed statuses

- **WHEN** a medication has 10 doses: 7 with `status = 'taken'`, 2 with `status = 'skipped'`, and 1 with `status = 'late'`
- **THEN** the `adherence` object MUST report `taken_count = 7`, `skipped_count = 2`, `late_count = 1`, `total_doses = 10`, and `adherence_pct = 80.0`

---

### Requirement: Conditions list API

The dashboard API SHALL expose `GET /api/butlers/health/conditions` which returns all condition records from the health butler's `conditions` table via a direct database read.

Each condition object in the response MUST include `id`, `name`, `status`, `diagnosed_at`, `notes`, `created_at`.

Results SHALL be ordered by `created_at` descending.

#### Scenario: Fetch all conditions

- **WHEN** `GET /api/butlers/health/conditions` is called
- **THEN** the API MUST return all conditions ordered by `created_at` descending
- **AND** each condition MUST include `id`, `name`, `status`, `diagnosed_at`, `notes`, `created_at`

#### Scenario: Conditions include multiple statuses

- **WHEN** the conditions table contains conditions with statuses `"active"`, `"managed"`, and `"resolved"`
- **THEN** the API MUST return all conditions regardless of status

#### Scenario: No conditions exist

- **WHEN** `GET /api/butlers/health/conditions` is called and the `conditions` table is empty
- **THEN** the API MUST return an empty array
- **AND** the response status MUST be 200

---

### Requirement: Symptoms list API

The dashboard API SHALL expose `GET /api/butlers/health/symptoms` which returns a paginated list of symptom records from the health butler's `symptoms` table via a direct database read.

The endpoint SHALL accept the following query parameters:
- `name` (string, optional) -- filter by symptom name (case-insensitive partial match using `ILIKE`)
- `from` (ISO 8601 timestamp, optional) -- include only symptoms with `occurred_at >= from`
- `to` (ISO 8601 timestamp, optional) -- include only symptoms with `occurred_at <= to`
- `limit` (integer, default 100) -- maximum number of records to return
- `offset` (integer, default 0) -- number of records to skip for pagination

Each symptom object in the response MUST include `id`, `name`, `severity`, `notes`, `condition_id`, `occurred_at`, `created_at`.

The response SHALL be a JSON object containing:
- `items` (array) -- the symptom records
- `total` (integer) -- total count of matching records

Results SHALL be ordered by `occurred_at` descending.

#### Scenario: Fetch all symptoms with default pagination

- **WHEN** `GET /api/butlers/health/symptoms` is called with no query parameters
- **THEN** the API MUST return at most 100 symptoms ordered by `occurred_at` descending
- **AND** the response MUST include a `total` count

#### Scenario: Filter symptoms by name

- **WHEN** `GET /api/butlers/health/symptoms?name=headache` is called
- **THEN** the API MUST return only symptoms whose `name` matches `"headache"` case-insensitively (e.g., `"Headache"`, `"headache"`, `"HEADACHE"`)

#### Scenario: Filter symptoms by date range

- **WHEN** `GET /api/butlers/health/symptoms?from=2026-02-01T00:00:00Z&to=2026-02-07T23:59:59Z` is called
- **THEN** the API MUST return only symptoms with `occurred_at` within the specified range

#### Scenario: Combined name and date range filter

- **WHEN** `GET /api/butlers/health/symptoms?name=nausea&from=2026-01-01T00:00:00Z` is called
- **THEN** the API MUST return only symptoms named `"nausea"` (case-insensitive) with `occurred_at >= 2026-01-01T00:00:00Z`

#### Scenario: No symptoms match

- **WHEN** `GET /api/butlers/health/symptoms?name=nonexistent` is called and no symptoms match
- **THEN** the API MUST return an empty `items` array and `total` of 0
- **AND** the response status MUST be 200

---

### Requirement: Meals list API

The dashboard API SHALL expose `GET /api/butlers/health/meals` which returns a paginated list of meal records from the health butler's `meals` table via a direct database read.

The endpoint SHALL accept the following query parameters:
- `from` (ISO 8601 timestamp, optional) -- include only meals with `consumed_at >= from`
- `to` (ISO 8601 timestamp, optional) -- include only meals with `consumed_at <= to`
- `limit` (integer, default 100) -- maximum number of records to return
- `offset` (integer, default 0) -- number of records to skip for pagination

Each meal object in the response MUST include `id`, `meal_type`, `description`, `nutrition`, `consumed_at`, `created_at`.

The response SHALL be a JSON object containing:
- `items` (array) -- the meal records
- `total` (integer) -- total count of matching records

Results SHALL be ordered by `consumed_at` descending.

#### Scenario: Fetch all meals with default pagination

- **WHEN** `GET /api/butlers/health/meals` is called with no query parameters
- **THEN** the API MUST return at most 100 meals ordered by `consumed_at` descending
- **AND** the response MUST include a `total` count

#### Scenario: Filter meals by date range

- **WHEN** `GET /api/butlers/health/meals?from=2026-02-10T00:00:00Z&to=2026-02-10T23:59:59Z` is called
- **THEN** the API MUST return only meals consumed on February 10, 2026

#### Scenario: Paginate through meals

- **WHEN** `GET /api/butlers/health/meals?limit=10&offset=30` is called
- **THEN** the API MUST skip the first 30 matching meals and return at most 10

#### Scenario: No meals in date range

- **WHEN** `GET /api/butlers/health/meals?from=2020-01-01T00:00:00Z&to=2020-01-31T23:59:59Z` is called and no meals exist in that range
- **THEN** the API MUST return an empty `items` array and `total` of 0
- **AND** the response status MUST be 200

---

### Requirement: Research list and search API

The dashboard API SHALL expose `GET /api/butlers/health/research` which returns a paginated list of research records from the health butler's `research` table via a direct database read, with optional full-text search.

The endpoint SHALL accept the following query parameters:
- `topic` (string, optional) -- filter by exact topic match
- `q` (string, optional) -- full-text search against `title` and `content` fields (case-insensitive `ILIKE` with `%q%` pattern)
- `limit` (integer, default 50) -- maximum number of records to return
- `offset` (integer, default 0) -- number of records to skip for pagination

Each research object in the response MUST include `id`, `topic`, `title`, `content` (truncated to 500 characters in list view), `source_url`, `tags`, `created_at`.

The response SHALL be a JSON object containing:
- `items` (array) -- the research records
- `total` (integer) -- total count of matching records

Results SHALL be ordered by `created_at` descending.

#### Scenario: Fetch all research with default pagination

- **WHEN** `GET /api/butlers/health/research` is called with no query parameters
- **THEN** the API MUST return at most 50 research records ordered by `created_at` descending
- **AND** each record's `content` field MUST be truncated to 500 characters with an ellipsis appended if the original exceeds 500 characters

#### Scenario: Filter research by topic

- **WHEN** `GET /api/butlers/health/research?topic=diabetes` is called
- **THEN** the API MUST return only research records where `topic` equals `"diabetes"`

#### Scenario: Search research by query string

- **WHEN** `GET /api/butlers/health/research?q=metformin` is called
- **THEN** the API MUST return only research records where `title` or `content` contains `"metformin"` (case-insensitive)

#### Scenario: Combined topic and search query

- **WHEN** `GET /api/butlers/health/research?topic=diabetes&q=longevity` is called
- **THEN** the API MUST return only research records where `topic` equals `"diabetes"` AND (`title` or `content` contains `"longevity"`)

#### Scenario: No research matches

- **WHEN** `GET /api/butlers/health/research?q=nonexistent` is called and no records match
- **THEN** the API MUST return an empty `items` array and `total` of 0
- **AND** the response status MUST be 200

---

### Requirement: Measurements dashboard page

The frontend SHALL render a measurements dashboard within the health butler's detail page that provides interactive charts and tabular data for health measurements.

The measurements dashboard MUST include the following components:

1. **Type selector tabs** -- horizontal tabs allowing the user to select a measurement type (`weight`, `blood_pressure`, `heart_rate`, `blood_glucose`, etc.). The selected type determines which data is displayed in the chart and table. The default selected tab SHALL be `weight`.
2. **Date range picker** -- a date range picker allowing the user to constrain the displayed data to a specific time period. The default range SHALL be the last 30 days.
3. **Line chart (Recharts)** -- a time-series line chart rendered with the Recharts library, plotting measurement values on the Y-axis against `measured_at` timestamps on the X-axis. For `blood_pressure` type, the chart MUST render two lines (systolic and diastolic) from the `details` JSONB field. For other types, the chart SHALL plot the `value` field.
4. **Raw data table toggle** -- a toggle control that reveals a tabular view of the raw measurement records underlying the chart. The table SHALL display `measured_at`, `value`, `unit`, `details`, and `notes` columns.

#### Scenario: Measurements dashboard loads with default view

- **WHEN** a user navigates to the health butler's measurements dashboard
- **THEN** the `weight` tab MUST be selected by default
- **AND** the date range picker MUST default to the last 30 days
- **AND** the line chart MUST display weight measurements over the last 30 days
- **AND** the raw data table MUST be hidden by default

#### Scenario: User selects blood pressure type

- **WHEN** the user clicks the `blood_pressure` tab
- **THEN** the line chart MUST update to display two lines: one for systolic values and one for diastolic values, extracted from the `details` JSONB field
- **AND** the chart legend MUST label the lines as "Systolic" and "Diastolic"

#### Scenario: User selects heart rate type

- **WHEN** the user clicks the `heart_rate` tab
- **THEN** the line chart MUST update to display a single line for heart rate values from the `value` field
- **AND** the Y-axis label MUST reflect the unit (e.g., "bpm")

#### Scenario: User changes date range

- **WHEN** the user selects a custom date range of January 1-31, 2026
- **THEN** the chart MUST re-fetch and display only measurements within that date range
- **AND** the raw data table (if visible) MUST also update to show only records within that range

#### Scenario: User toggles raw data table

- **WHEN** the user clicks the raw data table toggle
- **THEN** a table MUST appear below the chart displaying `measured_at`, `value`, `unit`, `details`, and `notes` for each measurement
- **AND** clicking the toggle again MUST hide the table

#### Scenario: No measurements for selected type and date range

- **WHEN** the selected type and date range yield zero measurements
- **THEN** the chart area MUST display an empty state message (e.g., "No measurements recorded for this period")
- **AND** the raw data table (if visible) MUST display "No data"

#### Scenario: Chart data point hover

- **WHEN** the user hovers over a data point on the line chart
- **THEN** a tooltip MUST appear showing the exact value, unit, and `measured_at` timestamp for that point

---

### Requirement: Medications page

The frontend SHALL render a medications page within the health butler's detail page that displays medication cards and dose log details.

The medications page MUST include the following components:

1. **Active medication cards** -- a card layout displaying each active medication. Each card MUST show the medication `name`, `dosage`, `frequency`, and `schedule_times` (formatted as a human-readable schedule, e.g., "8:00 AM, 8:00 PM"). Inactive medications SHALL be visually de-emphasized or shown in a separate collapsed section.
2. **Dose log table** -- when the user selects a medication card, a dose log table MUST appear showing that medication's dose history. The table SHALL display `taken_at` (or `scheduled_for`), `status` (with color-coded badge: green for "taken", yellow for "late", red for "skipped"), and `notes`.
3. **Adherence percentage** -- each medication card MUST display the adherence percentage for the last 30 days. The adherence percentage SHALL be computed from the `adherence` object returned by the doses API.

#### Scenario: Medications page loads with active medications

- **WHEN** a user navigates to the health butler's medications page
- **THEN** all active medications MUST be displayed as cards with `name`, `dosage`, `frequency`, and `schedule_times`
- **AND** each card MUST display the 30-day adherence percentage

#### Scenario: User selects a medication card to view dose log

- **WHEN** the user clicks on the "Metformin" medication card
- **THEN** a dose log table MUST appear showing dose records for Metformin
- **AND** each dose row MUST display the timestamp, a color-coded status badge, and notes

#### Scenario: Adherence percentage display

- **WHEN** a medication has an adherence percentage of 85%
- **THEN** the card MUST display "85%" as the adherence value
- **AND** the display SHOULD use color coding (e.g., green for >= 80%, yellow for 50-79%, red for < 50%)

#### Scenario: No medications exist

- **WHEN** the medications table is empty
- **THEN** the page MUST display an empty state message (e.g., "No medications tracked")

#### Scenario: Inactive medications section

- **WHEN** both active and inactive medications exist
- **THEN** active medications MUST be displayed prominently as cards
- **AND** inactive medications MUST be available in a separate collapsed section labeled "Inactive Medications"
- **AND** expanding the section MUST show the inactive medication cards with a visual indicator of their inactive status

#### Scenario: Dose log with no doses recorded

- **WHEN** the user selects a medication that has no dose records
- **THEN** the dose log table MUST display an empty state message (e.g., "No doses recorded")
- **AND** the adherence percentage on the card MUST display "N/A"

---

### Requirement: Conditions list page

The frontend SHALL render a conditions list within the health butler's detail page that displays health conditions as cards with status badges.

Each condition card MUST display:
- **Name** -- the condition name
- **Status badge** -- a color-coded badge indicating the condition status: green for `"active"`, blue for `"managed"`, gray for `"resolved"`
- **Diagnosed at** -- the `diagnosed_at` date, formatted as a human-readable date, or "Unknown" if null
- **Notes** -- the condition notes, truncated with ellipsis if longer than 150 characters

#### Scenario: Conditions page loads with all conditions

- **WHEN** a user navigates to the health butler's conditions page
- **THEN** all conditions MUST be displayed as cards
- **AND** each card MUST show the condition name and a color-coded status badge

#### Scenario: Status badge colors

- **WHEN** conditions with statuses `"active"`, `"managed"`, and `"resolved"` are displayed
- **THEN** the `"active"` condition MUST have a green badge
- **AND** the `"managed"` condition MUST have a blue badge
- **AND** the `"resolved"` condition MUST have a gray badge

#### Scenario: Condition with no diagnosed_at date

- **WHEN** a condition has `diagnosed_at` set to `null`
- **THEN** the "Diagnosed at" field MUST display "Unknown"

#### Scenario: No conditions exist

- **WHEN** the conditions table is empty
- **THEN** the page MUST display an empty state message (e.g., "No conditions tracked")

#### Scenario: Condition notes truncation

- **WHEN** a condition has notes longer than 150 characters
- **THEN** the card MUST display the first 150 characters followed by an ellipsis
- **AND** a "Show more" control MUST be available to reveal the full notes

---

### Requirement: Symptoms log page

The frontend SHALL render a symptoms log page within the health butler's detail page that displays symptom records in a filterable table with severity visualization.

The symptoms log MUST include the following components:

1. **Symptoms table** -- a paginated table displaying symptom records with columns: `occurred_at` (formatted timestamp), `name`, `severity` (displayed as a horizontal bar scaled 1-10 with color gradient from green at 1 to red at 10), `notes`, and `condition_id` (displayed as the linked condition name if available, or a dash).
2. **Filter controls** -- a name search input (debounced, 300ms) and a date range picker for filtering the table.
3. **Severity trend chart (optional)** -- a line chart showing average daily severity over time for the filtered symptoms. This component is OPTIONAL for the initial implementation but the API data MUST support it.

#### Scenario: Symptoms log loads with default view

- **WHEN** a user navigates to the health butler's symptoms log
- **THEN** the symptoms table MUST display the first page of symptoms ordered by `occurred_at` descending
- **AND** each row MUST include a severity bar visualization scaled 1-10

#### Scenario: Severity bar visualization

- **WHEN** a symptom has `severity = 3`
- **THEN** the severity bar MUST be filled to 30% of its width
- **AND** the bar color MUST be in the green range
- **WHEN** a symptom has `severity = 9`
- **THEN** the severity bar MUST be filled to 90% of its width
- **AND** the bar color MUST be in the red range

#### Scenario: User filters by symptom name

- **WHEN** the user types `"headache"` into the name search input
- **THEN** after the 300ms debounce, the table MUST update to show only symptoms matching `"headache"` (case-insensitive)

#### Scenario: User filters by date range

- **WHEN** the user selects a date range of February 1-7, 2026
- **THEN** the table MUST update to show only symptoms within that date range

#### Scenario: No symptoms match the filters

- **WHEN** the applied filters match no symptoms
- **THEN** the table MUST display an empty state message (e.g., "No symptoms recorded for the selected filters")

#### Scenario: Symptom linked to a condition

- **WHEN** a symptom has a non-null `condition_id`
- **THEN** the condition column MUST display the linked condition's name (resolved via the conditions API or joined in the query)

---

### Requirement: Meals log page

The frontend SHALL render a meals log page within the health butler's detail page that displays meals in a daily timeline view.

The meals log MUST include the following components:

1. **Daily timeline view** -- meals grouped by date, displayed as a vertical timeline. Each day is a section header (e.g., "Monday, February 10, 2026"). Within each day, meals are displayed in chronological order with a time marker, `meal_type` badge (color-coded: breakfast=yellow, lunch=green, dinner=blue, snack=gray), `description`, and `nutrition` summary if available.
2. **Date range picker** -- a date range picker to constrain which days are shown. The default range SHALL be the last 7 days.
3. **Nutrition summary** -- when a meal has non-empty `nutrition` JSONB data, the timeline entry MUST display a compact nutrition summary (e.g., "450 cal | 25g protein | 60g carbs | 15g fat").

#### Scenario: Meals log loads with default view

- **WHEN** a user navigates to the health butler's meals log
- **THEN** the page MUST display a daily timeline for the last 7 days
- **AND** meals within each day MUST be ordered chronologically by `consumed_at`

#### Scenario: Meal type badges

- **WHEN** meals of types `breakfast`, `lunch`, `dinner`, and `snack` are displayed
- **THEN** each meal MUST have a colored badge matching its type: yellow for breakfast, green for lunch, blue for dinner, gray for snack

#### Scenario: Meal with nutrition data

- **WHEN** a meal has `nutrition = {"calories": 450, "protein_g": 25, "carbs_g": 60, "fat_g": 15}`
- **THEN** the timeline entry MUST display a compact nutrition summary: "450 cal | 25g protein | 60g carbs | 15g fat"

#### Scenario: Meal without nutrition data

- **WHEN** a meal has `nutrition` as an empty object `{}` or null
- **THEN** the timeline entry MUST NOT display a nutrition summary line

#### Scenario: User changes date range

- **WHEN** the user selects a date range of February 1-3, 2026
- **THEN** the timeline MUST update to show only meals consumed within those three days

#### Scenario: Day with no meals

- **WHEN** a date within the selected range has no meals
- **THEN** that day MUST either be omitted from the timeline or shown with an "No meals recorded" indicator

#### Scenario: No meals in the entire range

- **WHEN** the selected date range has no meals at all
- **THEN** the page MUST display an empty state message (e.g., "No meals recorded for this period")

---

### Requirement: Research page

The frontend SHALL render a research page within the health butler's detail page that provides a searchable list of research articles with topic tag filtering.

The research page MUST include the following components:

1. **Search input** -- a text input for searching research by title and content. The search SHALL be debounced (300ms) and use the `q` query parameter.
2. **Topic tags** -- a set of clickable tag chips displaying all unique topics. Clicking a topic tag SHALL filter the list to only research with that topic. The active tag SHALL be visually highlighted.
3. **Research list** -- a list of research entries, each displaying `title`, `topic` (as a badge), content preview (truncated to 500 characters), `tags` (as small chips), `source_url` (as a clickable link if present), and `created_at`.
4. **Pagination** -- standard pagination controls at the bottom of the list.

#### Scenario: Research page loads with default view

- **WHEN** a user navigates to the health butler's research page
- **THEN** the page MUST display the first page of research records ordered by `created_at` descending
- **AND** the search input MUST be empty
- **AND** no topic tag MUST be selected by default

#### Scenario: User searches by text query

- **WHEN** the user types `"metformin"` into the search input
- **THEN** after the 300ms debounce, the list MUST update to show only research where the title or content contains `"metformin"`

#### Scenario: User filters by topic tag

- **WHEN** the user clicks the `"diabetes"` topic tag
- **THEN** the list MUST update to show only research with `topic` equal to `"diabetes"`
- **AND** the `"diabetes"` tag chip MUST be visually highlighted as active

#### Scenario: Combined search and topic filter

- **WHEN** the user selects the `"diabetes"` topic tag and types `"longevity"` in the search input
- **THEN** the list MUST show only research matching both: `topic = "diabetes"` AND title or content contains `"longevity"`

#### Scenario: Research entry with source URL

- **WHEN** a research entry has a non-null `source_url`
- **THEN** the entry MUST display the URL as a clickable link that opens in a new tab

#### Scenario: Research entry without source URL

- **WHEN** a research entry has `source_url` set to null
- **THEN** no link MUST be displayed for that entry

#### Scenario: No research matches

- **WHEN** the search query and/or topic filter yield zero results
- **THEN** the page MUST display an empty state message (e.g., "No research articles found")

#### Scenario: User deselects topic tag

- **WHEN** the user clicks the currently active topic tag
- **THEN** the topic filter MUST be cleared
- **AND** the list MUST update to show all research (subject to any text search query)

#### Scenario: Research tags displayed as chips

- **WHEN** a research entry has `tags = ["diabetes", "longevity", "metformin"]`
- **THEN** the entry MUST display three small tag chips with those values
