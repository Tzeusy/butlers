## ADDED Requirements

### Requirement: List collections with entity counts
The dashboard API SHALL expose `GET /api/butlers/general/collections` which MUST return all collections from the `collections` table (id, name, description, schema_hint, created_at) along with a computed `entity_count` for each collection. The endpoint is read-only.

#### Scenario: Retrieve all collections
- **WHEN** a client sends `GET /api/butlers/general/collections`
- **THEN** the response MUST be a JSON array of collection objects, each including `id`, `name`, `description`, `schema_hint`, `created_at`, and `entity_count` (integer count of entities in that collection)

#### Scenario: Collection with no entities
- **WHEN** a collection exists but has zero associated entities
- **THEN** the collection MUST still appear in the response with `entity_count` set to `0`

---

### Requirement: Collection detail with schema hint
The dashboard API SHALL expose `GET /api/butlers/general/collections/:id` which MUST return a single collection by UUID, including its full `schema_hint` JSONB payload.

#### Scenario: Retrieve existing collection by ID
- **WHEN** a client sends `GET /api/butlers/general/collections/:id` with a valid collection UUID
- **THEN** the response MUST be a JSON object containing `id`, `name`, `description`, `schema_hint`, `created_at`, and `entity_count`

#### Scenario: Collection not found
- **WHEN** a client sends `GET /api/butlers/general/collections/:id` with a UUID that does not match any collection
- **THEN** the response MUST be HTTP 404 with an error message

---

### Requirement: List and search entities
The dashboard API SHALL expose `GET /api/butlers/general/entities` which MUST support listing and searching entities. The endpoint MUST accept query parameters: `collection` (UUID, filter by collection_id), `tag` (text, filter entities whose `tags` array contains the value), `q` (text, full-text search across `title` and `data` JSONB), `limit` (integer, default 50), and `offset` (integer, default 0). The endpoint is read-only.

#### Scenario: List all entities with default pagination
- **WHEN** a client sends `GET /api/butlers/general/entities` with no query parameters
- **THEN** the response MUST return up to 50 entities ordered by `created_at` descending, with `limit` and `offset` reflected in the response metadata

#### Scenario: Filter entities by collection
- **WHEN** a client sends `GET /api/butlers/general/entities?collection=<uuid>`
- **THEN** the response MUST contain only entities whose `collection_id` matches the provided UUID

#### Scenario: Filter entities by tag
- **WHEN** a client sends `GET /api/butlers/general/entities?tag=important`
- **THEN** the response MUST contain only entities whose `tags` array includes the value `important`

#### Scenario: Search entities by query string
- **WHEN** a client sends `GET /api/butlers/general/entities?q=meeting`
- **THEN** the response MUST contain only entities where `title` or any text value within `data` JSONB matches the search term `meeting`

#### Scenario: Combine collection filter with search
- **WHEN** a client sends `GET /api/butlers/general/entities?collection=<uuid>&q=report`
- **THEN** the response MUST contain only entities matching both the collection filter and the search term

---

### Requirement: Entity detail with full JSONB data
The dashboard API SHALL expose `GET /api/butlers/general/entities/:id` which MUST return a single entity by UUID, including its full `data` JSONB payload.

#### Scenario: Retrieve existing entity by ID
- **WHEN** a client sends `GET /api/butlers/general/entities/:id` with a valid entity UUID
- **THEN** the response MUST be a JSON object containing `id`, `collection_id`, `title`, `data` (full JSONB), `tags`, `created_at`, and `updated_at`

#### Scenario: Entity not found
- **WHEN** a client sends `GET /api/butlers/general/entities/:id` with a UUID that does not match any entity
- **THEN** the response MUST be HTTP 404 with an error message

---

### Requirement: Collections page
The dashboard frontend SHALL render a collections page displaying each collection as a card. Each card MUST show the collection `name`, `description`, `entity_count`, and a preview of `schema_hint`. Cards MUST link to the collection detail or a filtered entities view.

#### Scenario: Display collection cards
- **WHEN** a user navigates to the collections page
- **THEN** the page MUST display one card per collection, each showing name, description, entity count, and a truncated schema hint preview

#### Scenario: Empty state
- **WHEN** no collections exist
- **THEN** the page MUST display an informative empty-state message

---

### Requirement: Entities page with search and filters
The dashboard frontend SHALL render an entities page as a table with columns: title, collection badge, tags, created_at, and updated_at. The page MUST provide a search input (searching title + data), a collection filter dropdown, and a tag filter. Clicking an entity row MUST navigate to entity detail with a collapsible JSON tree viewer.

#### Scenario: Display entities table with filters
- **WHEN** a user navigates to the entities page
- **THEN** the page MUST display a table of entities with search input, collection filter, and tag filter controls above it

#### Scenario: Apply search filter
- **WHEN** a user types a query into the search input
- **THEN** the table MUST update to show only entities matching the search term in title or data

#### Scenario: Navigate to entity detail
- **WHEN** a user clicks an entity row in the table
- **THEN** the page MUST navigate to entity detail showing full metadata and a collapsible JSON tree viewer for the `data` field

---

### Requirement: JSON viewer component
The dashboard frontend SHALL provide a JSON viewer component used for displaying entity `data` and collection `schema_hint`. The viewer MUST support syntax highlighting, collapsible/expandable tree nodes, and a copy-to-clipboard button for the full JSON payload.

#### Scenario: Render nested JSON with collapsible nodes
- **WHEN** the JSON viewer receives a nested JSON object
- **THEN** the viewer MUST render it as a syntax-highlighted tree with each object and array node collapsible

#### Scenario: Copy JSON to clipboard
- **WHEN** a user clicks the copy-to-clipboard button on the JSON viewer
- **THEN** the full JSON payload MUST be copied to the system clipboard as formatted text
