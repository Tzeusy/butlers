# Dashboard Search

Global search via a Cmd+K command palette for the Butlers dashboard. The search API performs fan-out queries across all butler databases using PostgreSQL `ILIKE` for text matching, searching sessions (prompt, result), state (keys, values), contacts (name, company, notes -- Relationship butler), entities (title, tags, data -- General butler), skills (name, SKILL.md content -- from filesystem), and research (topic/tags, title -- Health butler). Results are grouped by category and presented in a cmdk-based command palette overlay.

---

## ADDED Requirements

### Requirement: Cross-butler search API

The dashboard API SHALL expose `GET /api/search` which performs a fan-out text search across all butler databases and the butler config filesystem, returning results grouped by category.

The endpoint SHALL accept the following query parameters:
- `q` (string, required) -- the search query string. MUST be at least 1 character. Leading and trailing whitespace SHALL be trimmed.
- `limit` (integer, optional, default 5) -- maximum number of results to return per category
- `categories` (comma-separated string, optional) -- restrict search to specific categories. Valid values: `sessions`, `contacts`, `entities`, `state`, `skills`, `research`. If omitted, all categories SHALL be searched.

The response SHALL conform to the following structure:
```json
{
  "results": {
    "sessions": [...],
    "contacts": [...],
    "entities": [...],
    "state": [...],
    "skills": [...],
    "research": [...]
  },
  "total": 42
}
```

Each result object SHALL include:
- `id` -- unique identifier (UUID for DB records, skill directory name for skills)
- `title` -- primary display text (e.g., contact name, entity title, state key, skill name, research title, session prompt truncated to 100 characters)
- `subtitle` -- butler name and category label (e.g., `"relationship / contacts"`, `"health / research"`)
- `snippet` -- text excerpt showing the match context, with the matching substring indicated. The snippet SHALL be at most 200 characters, centered around the first match occurrence.
- `butler` -- the butler name that owns the result
- `category` -- one of `sessions`, `contacts`, `entities`, `state`, `skills`, `research`
- `url` -- a frontend-routable path to the detail view for the result

The `total` field SHALL be the sum of result counts across all categories (respecting the per-category limit).

Categories SHALL be searched as follows:
- **sessions** -- fan-out across all butler DBs. Search `prompt` and `result` columns in the `sessions` table using `ILIKE '%<q>%'`. Each result's `title` SHALL be the prompt text truncated to 100 characters. The `url` SHALL be `/butlers/<butler>/sessions/<id>`.
- **state** -- fan-out across all butler DBs. Search `key` and `value::text` columns in the `state` table using `ILIKE '%<q>%'`. Each result's `title` SHALL be the state key. The `url` SHALL be `/butlers/<butler>?tab=state`.
- **contacts** -- query the Relationship butler's DB only. Search `first_name`, `last_name`, `company` columns in the `contacts` table and `body` column in the `notes` table (joined via `contact_id`) using `ILIKE '%<q>%'`. Each result's `title` SHALL be the contact's full name (`first_name || ' ' || last_name`). The `url` SHALL be `/butlers/relationship/contacts/<id>`.
- **entities** -- query the General butler's DB only. Search `title` and `data::text` columns in the `entities` table, and match against `tags` array elements using `ILIKE`, via `EXISTS (SELECT 1 FROM jsonb_array_elements_text(tags) AS t WHERE t ILIKE '%<q>%')`. Each result's `title` SHALL be the entity title. The `url` SHALL be `/butlers/general/entities/<id>`.
- **skills** -- scan the filesystem. For each butler's config directory, read `skills/*/SKILL.md` files and match the skill directory name and file content against the query using case-insensitive substring matching. Each result's `title` SHALL be the skill directory name. The `subtitle` SHALL include the butler that owns the skill. The `url` SHALL be `/butlers/<butler>?tab=skills`.
- **research** -- query the Health butler's DB only. Search `title` and `content` columns in the `research` table using `ILIKE '%<q>%'`, and match against `tags` array elements using `EXISTS (SELECT 1 FROM jsonb_array_elements_text(tags) AS t WHERE t ILIKE '%<q>%')`. Each result's `title` SHALL be the research title. The `url` SHALL be `/butlers/health/research/<id>`.

Empty categories (no matches) SHALL be included in the response as empty arrays. If the `q` parameter is missing or empty after trimming, the API SHALL return HTTP 422 with a validation error.

#### Scenario: Search across all categories with default limit

- **WHEN** `GET /api/search?q=morning` is called
- **THEN** the API MUST query all butler databases concurrently for sessions and state matches
- **AND** the API MUST query the Relationship butler's DB for contact and note matches
- **AND** the API MUST query the General butler's DB for entity matches
- **AND** the API MUST query the Health butler's DB for research matches
- **AND** the API MUST scan the filesystem for skill matches
- **AND** the response MUST contain a `results` object with keys for all six categories
- **AND** each category MUST contain at most 5 results
- **AND** the `total` field MUST equal the sum of results across all categories

#### Scenario: Search returns matching session by prompt content

- **WHEN** `GET /api/search?q=health+vitals` is called
- **AND** a session in the Health butler's DB has a `prompt` containing "Check health vitals for this week"
- **THEN** the `sessions` array MUST contain a result with `title` set to the truncated prompt, `butler` set to `"health"`, `subtitle` set to `"health / sessions"`, and a `snippet` showing the match context around "health vitals"

#### Scenario: Search returns matching contact by name

- **WHEN** `GET /api/search?q=alice` is called
- **AND** a contact in the Relationship butler's DB has `first_name = "Alice"` and `last_name = "Smith"`
- **THEN** the `contacts` array MUST contain a result with `title` set to `"Alice Smith"`, `butler` set to `"relationship"`, and `url` set to `/butlers/relationship/contacts/<contact-uuid>`

#### Scenario: Search returns matching contact by associated note

- **WHEN** `GET /api/search?q=trip+to+paris` is called
- **AND** a note in the Relationship butler's DB has `body` containing "trip to Paris last summer" associated with contact "Bob Jones"
- **THEN** the `contacts` array MUST contain a result with `title` set to `"Bob Jones"` and a `snippet` showing the match context from the note body

#### Scenario: Search returns matching entity by tag

- **WHEN** `GET /api/search?q=recipe` is called
- **AND** an entity in the General butler's DB has `tags = ["recipe", "cooking"]`
- **THEN** the `entities` array MUST contain a result with `title` set to the entity's title and a `snippet` referencing the matched tag

#### Scenario: Search returns matching skill by SKILL.md content

- **WHEN** `GET /api/search?q=briefing` is called
- **AND** the Health butler has a skill directory `skills/morning-briefing/` with a `SKILL.md` containing "Generate a morning health briefing"
- **THEN** the `skills` array MUST contain a result with `title` set to `"morning-briefing"`, `butler` set to `"health"`, and a `snippet` showing the match context from the SKILL.md content

#### Scenario: Search returns matching research by title

- **WHEN** `GET /api/search?q=vitamin+D` is called
- **AND** the Health butler's DB has a research entry with `title = "Vitamin D supplementation guidelines"`
- **THEN** the `research` array MUST contain a result with `title` set to `"Vitamin D supplementation guidelines"`, `butler` set to `"health"`, and `url` set to `/butlers/health/research/<research-uuid>`

#### Scenario: Search returns matching state by key

- **WHEN** `GET /api/search?q=telegram` is called
- **AND** the Switchboard butler's state table has a row with `key = "telegram_bot_status"`
- **THEN** the `state` array MUST contain a result with `title` set to `"telegram_bot_status"`, `butler` set to `"switchboard"`, and `url` set to `/butlers/switchboard?tab=state`

#### Scenario: Search returns matching state by value content

- **WHEN** `GET /api/search?q=pending` is called
- **AND** the General butler's state table has a row with `key = "task_queue"` and `value = {"items": [{"status": "pending"}]}`
- **THEN** the `state` array MUST contain a result with `title` set to `"task_queue"` and a `snippet` showing the match context from the serialized value

#### Scenario: Filter search to specific categories

- **WHEN** `GET /api/search?q=alice&categories=contacts,sessions` is called
- **THEN** the API MUST search only the `contacts` and `sessions` categories
- **AND** the `entities`, `state`, `skills`, and `research` arrays in the response MUST be empty

#### Scenario: Custom per-category limit

- **WHEN** `GET /api/search?q=morning&limit=3` is called
- **THEN** each category in the response MUST contain at most 3 results

#### Scenario: Empty query returns validation error

- **WHEN** `GET /api/search?q=` is called (empty query string)
- **THEN** the API MUST return HTTP 422 with error code `"VALIDATION_ERROR"` and a message indicating the search query is required

#### Scenario: No matches returns empty arrays

- **WHEN** `GET /api/search?q=xyznonexistent` is called and no data matches the query
- **THEN** the response MUST contain empty arrays for all six categories
- **AND** `total` MUST be `0`
- **AND** the HTTP status MUST be 200

#### Scenario: Fan-out tolerates individual database failures

- **WHEN** `GET /api/search?q=test` is called and the Health butler's database is unreachable
- **THEN** the `research` array MUST be empty
- **AND** session and state results from other reachable butler databases MUST be returned normally
- **AND** the error MUST be logged server-side

#### Scenario: Special characters in query are escaped for ILIKE

- **WHEN** `GET /api/search?q=%25discount` is called (URL-decoded: `%discount`)
- **THEN** the API MUST escape the `%` and `_` characters in the query before constructing `ILIKE` patterns
- **AND** the search MUST match literal `%discount` in text, not treat `%` as a wildcard

---

### Requirement: Command palette with Cmd+K

The frontend SHALL render a cmdk-based command palette overlay that serves as the global search interface. The palette SHALL be a modal dialog rendered above all page content with a dimmed backdrop.

The palette SHALL be opened by any of the following:
- Pressing `Cmd+K` on macOS or `Ctrl+K` on Windows/Linux
- Pressing the `/` key when no text input or textarea is focused
- Clicking the Search trigger item in the sidebar

The palette SHALL be closed by any of the following:
- Pressing `Escape`
- Clicking the dimmed backdrop area outside the palette
- Navigating to a result (after navigation completes)

The palette SHALL contain:
1. A search input field at the top, auto-focused when the palette opens
2. A results area below the input, displaying grouped results or recent searches
3. Keyboard navigation support (arrow keys to move between results, Enter to select)

When the search input is empty, the palette SHALL display a list of recent searches (up to 10), persisted in `localStorage` under a well-known key. Each recent search item SHALL display the query text and be selectable to re-run that search. If no recent searches exist, the palette SHALL display a placeholder message (e.g., "Start typing to search across all butlers...").

When the search input has text, the palette SHALL make a debounced API call to `GET /api/search?q=<input>` with a debounce delay of 300ms. While the API call is in flight, a loading indicator SHALL be displayed in the results area. When results arrive, they SHALL replace the loading indicator.

#### Scenario: Cmd+K opens the command palette

- **WHEN** the user presses `Cmd+K` (macOS) or `Ctrl+K` (Windows/Linux) on any page
- **THEN** the command palette dialog MUST appear as a centered modal overlay with a dimmed backdrop
- **AND** the search input field MUST be auto-focused
- **AND** the palette MUST be rendered above all other page content (highest z-index layer)

#### Scenario: Slash key opens the command palette when no input is focused

- **WHEN** the user presses `/` and no `<input>`, `<textarea>`, or `[contenteditable]` element is focused
- **THEN** the command palette MUST open
- **AND** the `/` character MUST NOT be typed into the search input

#### Scenario: Slash key does not open palette when input is focused

- **WHEN** the user presses `/` while a text input or textarea is focused
- **THEN** the command palette MUST NOT open
- **AND** the `/` character MUST be typed into the currently focused input as normal

#### Scenario: Escape closes the command palette

- **WHEN** the command palette is open and the user presses `Escape`
- **THEN** the palette MUST close
- **AND** the search input text MUST be cleared
- **AND** focus MUST return to the element that was focused before the palette opened

#### Scenario: Backdrop click closes the command palette

- **WHEN** the command palette is open and the user clicks the dimmed backdrop
- **THEN** the palette MUST close

#### Scenario: Recent searches shown when input is empty

- **WHEN** the command palette opens and the search input is empty
- **AND** the user has previously searched for "alice", "morning briefing", and "vitamin D"
- **THEN** the results area MUST display the recent searches in reverse chronological order: "vitamin D", "morning briefing", "alice"
- **AND** each recent search MUST be selectable

#### Scenario: Selecting a recent search re-runs the query

- **WHEN** the user selects a recent search item "alice" from the list
- **THEN** the search input MUST be populated with "alice"
- **AND** a search API call MUST be triggered with `q=alice`

#### Scenario: Recent searches persisted in localStorage

- **WHEN** the user performs a search for "blood pressure"
- **THEN** "blood pressure" MUST be added to the recent searches list in `localStorage`
- **AND** if the list exceeds 10 entries, the oldest entry MUST be removed
- **AND** duplicate entries MUST be deduplicated (moved to the most recent position)

#### Scenario: Empty recent searches shows placeholder

- **WHEN** the command palette opens and no recent searches exist in `localStorage`
- **THEN** the results area MUST display the placeholder message "Start typing to search across all butlers..."

#### Scenario: Debounced API call on input

- **WHEN** the user types "morn" into the search input
- **THEN** the palette MUST NOT make an API call until 300ms have elapsed since the last keystroke
- **AND** if the user continues typing "morning" within 300ms, only one API call SHALL be made with `q=morning`

#### Scenario: Loading indicator during API call

- **WHEN** the search input has text and the API call is in flight
- **THEN** a loading indicator (spinner or skeleton) MUST be displayed in the results area
- **AND** the loading indicator MUST be replaced by results when the API responds

---

### Requirement: Search results display in command palette

Search results in the command palette SHALL be displayed grouped by category, with each group labeled by its category name and icon. Within each group, results SHALL be displayed as individual selectable items.

Each category group SHALL display:
- A category header with an icon and label: Sessions (clock icon), Contacts (user icon), Entities (box icon), State (database icon), Skills (code icon), Research (book icon)
- Up to the per-category limit of results beneath the header

Each result item SHALL display:
- **Title** -- the result's `title` field, styled as primary text
- **Butler badge** -- a small colored badge showing the butler name (using the same color mapping as the sidebar butler list)
- **Snippet** -- the result's `snippet` field, styled as secondary/muted text beneath the title, with the matching substring highlighted (bold or background color)

Categories with zero results SHALL NOT display a group header. If all categories have zero results, the palette SHALL display a "No results found" message.

The currently highlighted result (via keyboard navigation or mouse hover) SHALL be visually distinguished with a background highlight.

#### Scenario: Results grouped by category with icons

- **WHEN** a search for "morning" returns 2 sessions, 1 skill, and 0 results in other categories
- **THEN** the results area MUST display a "Sessions" group header with a clock icon followed by the 2 session results
- **AND** a "Skills" group header with a code icon followed by the 1 skill result
- **AND** no group headers MUST be displayed for contacts, entities, state, or research

#### Scenario: Result item displays title, butler badge, and snippet

- **WHEN** a search result has `title = "Alice Smith"`, `butler = "relationship"`, `category = "contacts"`, and `snippet = "...trip to **Paris** last summer..."`
- **THEN** the result item MUST display "Alice Smith" as primary text
- **AND** a badge labeled "relationship" with the relationship butler's color
- **AND** the snippet with the matching portion visually highlighted

#### Scenario: Keyboard navigation through results

- **WHEN** the command palette shows results and the user presses the down arrow key
- **THEN** the highlight MUST move to the next result item
- **AND** if the highlight is on the last result of a category group, the next press MUST move to the first result of the next non-empty category group

#### Scenario: Enter navigates to selected result

- **WHEN** a result item is highlighted and the user presses `Enter`
- **THEN** the application MUST navigate to the result's `url` path via React Router
- **AND** the command palette MUST close
- **AND** the search query MUST be saved to recent searches in `localStorage`

#### Scenario: Mouse click on result navigates to detail

- **WHEN** the user clicks on a result item
- **THEN** the application MUST navigate to the result's `url` path
- **AND** the command palette MUST close
- **AND** the search query MUST be saved to recent searches

#### Scenario: No results found message

- **WHEN** a search returns zero results across all categories
- **THEN** the results area MUST display a "No results found" message
- **AND** no category group headers MUST be displayed

#### Scenario: Mouse hover highlights result

- **WHEN** the user moves the mouse over a result item
- **THEN** that result MUST receive the highlight styling
- **AND** any previously keyboard-highlighted result MUST lose its highlight
