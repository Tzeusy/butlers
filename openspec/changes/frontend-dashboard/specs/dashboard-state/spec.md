# Dashboard State

State store browser and editor for the Butlers dashboard. Provides read-only API endpoints for browsing state entries (via direct DB reads) and write endpoints that proxy through the butler's MCP tools (`state_set`, `state_delete`). The frontend renders a state store tab within each butler's detail page with a searchable key-value table, JSON syntax highlighting, and modal-based write operations.

Each butler's database contains a `state` table with columns: `key` (TEXT PRIMARY KEY), `value` (JSONB NOT NULL), `updated_at` (TIMESTAMPTZ NOT NULL DEFAULT now()). The dashboard API never writes directly to the state table -- all mutations go through MCP tools to preserve the butler's write semantics and any side effects.

## ADDED Requirements

### Requirement: List state entries API

The dashboard API SHALL expose `GET /api/butlers/:name/state` which returns a list of state entries from the specified butler's `state` table via a direct database read.

The endpoint SHALL accept the following optional query parameter:
- `prefix` (string, optional) -- filter keys to those starting with the given prefix (SQL `LIKE prefix || '%'`)

The response SHALL be a JSON array of objects, each containing:
- `key` (string) -- the state key
- `value` (any JSON) -- the JSONB value
- `updated_at` (string, ISO 8601) -- the timestamp of the last update

The results SHALL be ordered by `key` ascending. If no entries match (or the state table is empty), the response SHALL be an empty array with HTTP 200.

#### Scenario: List all state entries with no filter

- **WHEN** `GET /api/butlers/health/state` is called with no query parameters
- **THEN** the API MUST query the `health` butler's `state` table and return all entries
- **AND** each entry MUST include `key`, `value`, and `updated_at`
- **AND** the entries MUST be ordered by `key` ascending
- **AND** the response status MUST be 200

#### Scenario: List state entries filtered by prefix

- **WHEN** `GET /api/butlers/health/state?prefix=config.` is called
- **THEN** the API MUST return only entries whose `key` starts with `"config."`
- **AND** entries with keys like `"counter"` or `"status"` MUST NOT be included

#### Scenario: No entries match the prefix

- **WHEN** `GET /api/butlers/health/state?prefix=nonexistent.` is called and no keys start with `"nonexistent."`
- **THEN** the API MUST return an empty array
- **AND** the response status MUST be 200

#### Scenario: Butler does not exist

- **WHEN** `GET /api/butlers/nonexistent/state` is called and no butler named `"nonexistent"` is registered
- **THEN** the API MUST return a 404 response with error code `"BUTLER_NOT_FOUND"`

---

### Requirement: Get single state entry API

The dashboard API SHALL expose `GET /api/butlers/:name/state/:key` which returns the value of a single state entry from the specified butler's `state` table via a direct database read.

The response SHALL be a JSON object containing:
- `key` (string) -- the state key
- `value` (any JSON) -- the JSONB value
- `updated_at` (string, ISO 8601) -- the timestamp of the last update

#### Scenario: Key exists in state table

- **WHEN** `GET /api/butlers/health/state/config.notifications` is called and the key `"config.notifications"` exists in the `health` butler's state table
- **THEN** the API MUST return the entry with `key`, `value`, and `updated_at`
- **AND** the response status MUST be 200

#### Scenario: Key does not exist

- **WHEN** `GET /api/butlers/health/state/nonexistent.key` is called and no entry with that key exists
- **THEN** the API MUST return a 404 response with an error message indicating the key was not found

#### Scenario: Key contains special characters

- **WHEN** `GET /api/butlers/health/state/metrics%2Fcpu%2Fusage` is called (URL-decoded: `"metrics/cpu/usage"`)
- **THEN** the API MUST correctly decode the key and look up `"metrics/cpu/usage"` in the state table

#### Scenario: Butler does not exist

- **WHEN** `GET /api/butlers/nonexistent/state/some.key` is called and no butler named `"nonexistent"` is registered
- **THEN** the API MUST return a 404 response with error code `"BUTLER_NOT_FOUND"`

---

### Requirement: Set state entry via MCP

The dashboard API SHALL expose `PUT /api/butlers/:name/state/:key` which sets a state entry by calling the butler's `state_set` MCP tool. The dashboard API MUST NOT write directly to the database.

The request body SHALL be a JSON object with a single field:
- `value` (any valid JSON) -- the value to set

The endpoint SHALL call `state_set(key, value)` on the specified butler via the MCP client manager. On success, the response SHALL be HTTP 200 with the updated entry (`key`, `value`, `updated_at`) read back from the database after the MCP call completes.

#### Scenario: Set a new key

- **WHEN** `PUT /api/butlers/health/state/config.theme` is called with body `{"value": "dark"}`
- **AND** the key `"config.theme"` does not yet exist in the `health` butler's state table
- **THEN** the API MUST call `state_set("config.theme", "dark")` via MCP on the `health` butler
- **AND** the response status MUST be 200
- **AND** the response body MUST include `key`, `value`, and `updated_at`

#### Scenario: Update an existing key

- **WHEN** `PUT /api/butlers/health/state/config.theme` is called with body `{"value": "light"}`
- **AND** the key `"config.theme"` already exists
- **THEN** the API MUST call `state_set("config.theme", "light")` via MCP on the `health` butler
- **AND** the response MUST reflect the updated value

#### Scenario: Set a complex JSONB value

- **WHEN** `PUT /api/butlers/health/state/prefs` is called with body `{"value": {"notifications": {"email": true, "sms": false}, "timezone": "UTC"}}`
- **THEN** the API MUST call `state_set("prefs", {"notifications": {"email": true, "sms": false}, "timezone": "UTC"})` via MCP
- **AND** the nested object MUST be preserved exactly as provided

#### Scenario: Request body missing value field

- **WHEN** `PUT /api/butlers/health/state/config.theme` is called with body `{}` (no `value` field)
- **THEN** the API MUST return a 422 response with error code `"VALIDATION_ERROR"`

#### Scenario: Request body with invalid JSON

- **WHEN** `PUT /api/butlers/health/state/config.theme` is called with a body that is not valid JSON
- **THEN** the API MUST return a 422 response with error code `"VALIDATION_ERROR"`

#### Scenario: Butler daemon is unreachable

- **WHEN** `PUT /api/butlers/health/state/config.theme` is called with body `{"value": "dark"}` but the `health` butler daemon is not running
- **THEN** the API MUST return a 502 response with error code `"BUTLER_UNREACHABLE"`

#### Scenario: Butler does not exist

- **WHEN** `PUT /api/butlers/nonexistent/state/some.key` is called
- **THEN** the API MUST return a 404 response with error code `"BUTLER_NOT_FOUND"`

---

### Requirement: Delete state entry via MCP

The dashboard API SHALL expose `DELETE /api/butlers/:name/state/:key` which deletes a state entry by calling the butler's `state_delete` MCP tool. The dashboard API MUST NOT delete directly from the database.

The endpoint SHALL call `state_delete(key)` on the specified butler via the MCP client manager. On success, the response SHALL be HTTP 204 with no body.

#### Scenario: Delete an existing key

- **WHEN** `DELETE /api/butlers/health/state/config.theme` is called and the key `"config.theme"` exists
- **THEN** the API MUST call `state_delete("config.theme")` via MCP on the `health` butler
- **AND** the response status MUST be 204
- **AND** the response body MUST be empty

#### Scenario: Delete a nonexistent key

- **WHEN** `DELETE /api/butlers/health/state/nonexistent.key` is called and the key does not exist
- **THEN** the API MUST call `state_delete("nonexistent.key")` via MCP on the `health` butler
- **AND** the response status MUST be 204 (the MCP tool treats this as a no-op)

#### Scenario: Butler daemon is unreachable

- **WHEN** `DELETE /api/butlers/health/state/config.theme` is called but the `health` butler daemon is not running
- **THEN** the API MUST return a 502 response with error code `"BUTLER_UNREACHABLE"`

#### Scenario: Butler does not exist

- **WHEN** `DELETE /api/butlers/nonexistent/state/some.key` is called
- **THEN** the API MUST return a 404 response with error code `"BUTLER_NOT_FOUND"`

---

### Requirement: State store tab with key-value table

The frontend SHALL render a state store tab within each butler's detail page that displays a searchable, sortable table of all state entries.

The table SHALL display the following columns:
- **Key** -- the state key as a monospace string
- **Value** -- the JSONB value, JSON pretty-printed with syntax highlighting. For values exceeding a maximum preview height (e.g., 3 lines), the row SHALL be collapsed by default with an expand control to reveal the full value.
- **Updated** -- `updated_at` formatted as a human-readable relative timestamp (e.g., "2 minutes ago", "3 days ago") with the full ISO timestamp shown on hover as a tooltip

The tab SHALL provide a prefix search input that filters the displayed entries by key prefix. The search input SHALL debounce user input (minimum 300ms) before issuing a new API request with the `prefix` query parameter.

#### Scenario: State tab loads with all entries

- **WHEN** a user navigates to the `health` butler's detail page and selects the state store tab
- **THEN** the table MUST display all state entries from the `health` butler ordered by key ascending
- **AND** the prefix search input MUST be visible and empty

#### Scenario: User searches by prefix

- **WHEN** the user types `"config."` into the prefix search input
- **THEN** after the debounce period, the table MUST update to show only entries whose keys start with `"config."`
- **AND** the API call MUST include `?prefix=config.`

#### Scenario: Large JSONB value is collapsed by default

- **WHEN** a state entry has a value that is a deeply nested JSON object exceeding the maximum preview height
- **THEN** the value cell MUST display a truncated preview of the JSON
- **AND** an expand control (e.g., "Show more" or chevron icon) MUST be visible
- **AND** clicking the expand control MUST reveal the full pretty-printed JSON with syntax highlighting

#### Scenario: Small JSONB value is displayed inline

- **WHEN** a state entry has a value that is a simple scalar or small object (e.g., `42`, `"active"`, `{"enabled": true}`)
- **THEN** the value cell MUST display the full pretty-printed JSON inline without an expand control

#### Scenario: JSON syntax highlighting

- **WHEN** a JSONB value is rendered in the table (collapsed or expanded)
- **THEN** the display MUST use syntax highlighting to visually distinguish JSON keys, string values, numeric values, boolean values, and null

#### Scenario: Empty state table

- **WHEN** the `health` butler has no state entries
- **THEN** the state tab MUST display an empty state message (e.g., "No state entries found")
- **AND** the prefix search input MUST still be visible

#### Scenario: Prefix search with no results

- **WHEN** the user types a prefix that matches no keys
- **THEN** the table MUST display an empty state message (e.g., "No entries match the prefix")

---

### Requirement: State write operations

The frontend SHALL provide UI controls for setting and deleting state entries within the state store tab.

**Set key modal:** A "Set Key" button SHALL open a modal dialog containing:
- A text input for the key (required, non-empty)
- A JSON editor for the value with real-time validation (required, must be valid JSON)
- A "Save" button that is disabled when the key is empty or the JSON is invalid
- A "Cancel" button that closes the modal without side effects

When the user clicks "Save", the frontend SHALL issue a `PUT /api/butlers/:name/state/:key` request with the entered value. On success, a success toast MUST be shown (e.g., "Key 'config.theme' saved") and the state table MUST refresh to reflect the change. On error, an error toast MUST be shown with the error message from the API response.

**Delete key:** Each row in the state table SHALL include a delete action (e.g., a trash icon button). Clicking the delete action SHALL open a confirmation dialog displaying the key name and asking the user to confirm deletion.

When the user confirms, the frontend SHALL issue a `DELETE /api/butlers/:name/state/:key` request. On success, a success toast MUST be shown (e.g., "Key 'config.theme' deleted") and the state table MUST refresh. On error, an error toast MUST be shown with the error message.

#### Scenario: Open set key modal and save a new entry

- **WHEN** the user clicks the "Set Key" button
- **THEN** a modal dialog MUST appear with an empty key input and an empty JSON editor
- **AND** the "Save" button MUST be disabled
- **WHEN** the user enters key `"config.theme"` and value `"dark"` (valid JSON string)
- **THEN** the "Save" button MUST become enabled
- **WHEN** the user clicks "Save"
- **THEN** the frontend MUST issue `PUT /api/butlers/health/state/config.theme` with body `{"value": "dark"}`
- **AND** on success, a toast MUST display "Key 'config.theme' saved"
- **AND** the modal MUST close
- **AND** the state table MUST refresh to include the new entry

#### Scenario: Set key modal with invalid JSON

- **WHEN** the user enters key `"config.theme"` and types `{invalid` in the JSON editor
- **THEN** the JSON editor MUST display a validation error indicator
- **AND** the "Save" button MUST remain disabled

#### Scenario: Set key modal with empty key

- **WHEN** the JSON editor contains valid JSON but the key input is empty
- **THEN** the "Save" button MUST remain disabled

#### Scenario: Set key modal cancelled

- **WHEN** the user clicks "Cancel" on the set key modal
- **THEN** the modal MUST close without issuing any API request
- **AND** the state table MUST NOT refresh

#### Scenario: Edit existing key via set key modal

- **WHEN** the user clicks an edit action on an existing state entry row
- **THEN** the set key modal MUST open pre-filled with the entry's current key and value
- **AND** the key input SHOULD be read-only (since the user is editing an existing entry)
- **WHEN** the user modifies the value and clicks "Save"
- **THEN** the frontend MUST issue a PUT request with the updated value

#### Scenario: Delete key with confirmation

- **WHEN** the user clicks the delete action on the row with key `"config.theme"`
- **THEN** a confirmation dialog MUST appear with text indicating that key `"config.theme"` will be deleted
- **WHEN** the user confirms the deletion
- **THEN** the frontend MUST issue `DELETE /api/butlers/health/state/config.theme`
- **AND** on success, a toast MUST display "Key 'config.theme' deleted"
- **AND** the state table MUST refresh to remove the entry

#### Scenario: Delete key cancelled

- **WHEN** the user clicks the delete action and then clicks "Cancel" on the confirmation dialog
- **THEN** the dialog MUST close without issuing any API request
- **AND** the state table MUST NOT be modified

#### Scenario: Write operation fails with butler unreachable

- **WHEN** the user saves a key but the butler daemon is not running
- **THEN** an error toast MUST be shown with a message indicating the butler is unreachable
- **AND** the modal or dialog MUST remain open so the user can retry or cancel

#### Scenario: Write operation fails with server error

- **WHEN** the user saves or deletes a key and the API returns a 500 error
- **THEN** an error toast MUST be shown with the error message from the API response
- **AND** the state table MUST NOT be modified (no optimistic update)
