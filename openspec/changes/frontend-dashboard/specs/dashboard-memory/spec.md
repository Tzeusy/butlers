## ADDED Requirements

> **Note:** All requirements in this spec are CONTINGENT on the memory system being implemented as described in `MEMORY_PROJECT_PLAN.md`. These requirements SHALL only be built after the three-tier memory system (Eden, Mid-Term, Long-Term) is finalized and operational.

### Requirement: Memory stats endpoint
The dashboard API SHALL expose `GET /api/butlers/:name/memory/stats` which MUST return tier counts, capacity usage, and health indicators for the named butler's memory system. This requirement is CONTINGENT on memory system implementation.

#### Scenario: Retrieve memory stats
- **WHEN** a client sends `GET /api/butlers/:name/memory/stats` for a butler with an active memory system
- **THEN** the response MUST include per-tier data (Eden, Mid-Term, Long-Term) with `count`, `capacity`, `usage_percent`, and health indicators (`eviction_rate`, `saturation_percent`, `promotion_rate`)

#### Scenario: Butler has no memory data
- **WHEN** a client sends `GET /api/butlers/:name/memory/stats` and the butler's `memories` table is empty
- **THEN** the response MUST return zero counts and zero usage for all tiers with healthy default indicators

---

### Requirement: Browse and search memory entries
The dashboard API SHALL expose `GET /api/butlers/:name/memory/entries` which MUST support browsing and searching memory entries. The endpoint MUST accept query parameters: `tier` (one of `eden`, `mid-term`, `long-term`), `tag` (text, filter entries whose `tags` array contains the value), `q` (text, full-text search across `content`), `limit` (integer, default 50), and `offset` (integer, default 0). This requirement is CONTINGENT on memory system implementation.

#### Scenario: List all memory entries with default pagination
- **WHEN** a client sends `GET /api/butlers/:name/memory/entries` with no query parameters
- **THEN** the response MUST return up to 50 memory entries ordered by `last_referenced` descending, each containing `id`, `tier`, `content` (truncated), `tags`, `ref_count`, `last_referenced`, and `created_at`

#### Scenario: Filter by tier
- **WHEN** a client sends `GET /api/butlers/:name/memory/entries?tier=eden`
- **THEN** the response MUST contain only entries with `tier` equal to `eden`

#### Scenario: Search memory content
- **WHEN** a client sends `GET /api/butlers/:name/memory/entries?q=deployment`
- **THEN** the response MUST contain only entries whose `content` matches the search term `deployment`

#### Scenario: Combine tier and tag filters
- **WHEN** a client sends `GET /api/butlers/:name/memory/entries?tier=long-term&tag=important`
- **THEN** the response MUST contain only entries in the `long-term` tier whose `tags` array includes `important`

---

### Requirement: Single memory entry detail
The dashboard API SHALL expose `GET /api/butlers/:name/memory/entries/:id` which MUST return a single memory entry by UUID, including its full `content` and all metadata. This requirement is CONTINGENT on memory system implementation.

#### Scenario: Retrieve existing memory entry
- **WHEN** a client sends `GET /api/butlers/:name/memory/entries/:id` with a valid memory entry UUID
- **THEN** the response MUST include `id`, `tier`, `content` (full text), `tags`, `ref_count`, `last_referenced`, and `created_at`

#### Scenario: Memory entry not found
- **WHEN** a client sends `GET /api/butlers/:name/memory/entries/:id` with a UUID that does not match any entry
- **THEN** the response MUST be HTTP 404 with an error message

---

### Requirement: Memory activity feed
The dashboard API SHALL expose `GET /api/butlers/:name/memory/activity` which MUST return recent promotions and evictions in the memory system. Results MUST be ordered by timestamp descending. The endpoint MUST accept `limit` (integer, default 50) and `offset` (integer, default 0) query parameters. This requirement is CONTINGENT on memory system implementation.

#### Scenario: Retrieve recent memory activity
- **WHEN** a client sends `GET /api/butlers/:name/memory/activity`
- **THEN** the response MUST return up to 50 recent memory activity events, each containing event type (`promotion` or `eviction`), affected memory entry ID, source tier, target tier (for promotions) or null (for evictions), and timestamp

#### Scenario: No recent activity
- **WHEN** a client sends `GET /api/butlers/:name/memory/activity` and no promotions or evictions have occurred
- **THEN** the response MUST be an empty JSON array

---

### Requirement: Memory tab on butler detail page
The dashboard frontend SHALL render a memory tab on the butler detail page. The tab MUST display: tier overview cards (Eden, Mid-Term, Long-Term) each showing entry count, a capacity bar, and oldest/newest entry timestamps; a promotion/eviction timeline; and a memory browser table with columns: tier badge, content (truncated), tags, ref count, and last referenced. Clicking a row MUST navigate to the full memory entry detail with complete content and metadata. This requirement is CONTINGENT on memory system implementation.

#### Scenario: Display tier overview cards
- **WHEN** a user navigates to the memory tab of a butler detail page
- **THEN** the page MUST display three tier cards (Eden, Mid-Term, Long-Term), each showing entry count, a visual capacity bar representing usage percentage, and the oldest and newest entry timestamps

#### Scenario: Display promotion/eviction timeline
- **WHEN** a user views the memory tab
- **THEN** the page MUST display a timeline of recent promotion and eviction events ordered by timestamp descending

#### Scenario: Browse and click memory entries
- **WHEN** a user clicks a row in the memory browser table
- **THEN** the page MUST navigate to the full memory entry detail showing complete content and all metadata (tier, tags, ref_count, last_referenced, created_at)

#### Scenario: Empty memory state
- **WHEN** a butler has no memory entries
- **THEN** the memory tab MUST display an informative empty-state message indicating no memories exist yet

---

### Requirement: Memory health indicators
The dashboard frontend SHALL display memory health indicators on the memory tab. Health indicators MUST include: eviction rate (evictions per time period), saturation percentage (entries vs. capacity per tier), and promotion rate (promotions per time period). These indicators MUST be derived from the stats endpoint. This requirement is CONTINGENT on memory system implementation.

#### Scenario: Display health indicators
- **WHEN** a user views the memory tab
- **THEN** the page MUST display eviction rate, saturation percentage per tier, and promotion rate as clearly labeled metrics

#### Scenario: Healthy memory system
- **WHEN** all tiers are below 80% saturation and eviction rate is low
- **THEN** health indicators MUST display in a normal/healthy visual state

#### Scenario: Saturated tier warning
- **WHEN** any tier exceeds 90% saturation
- **THEN** the corresponding health indicator MUST display in a warning visual state to alert the user
