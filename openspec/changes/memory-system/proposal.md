## Why

Butlers currently have no shared memory. Each CC session starts from scratch — no recall of user preferences, past interactions, or learned behavioral patterns. The Memory Butler introduces institutional memory so that every butler can remember what matters, forget what doesn't, and learn from experience.

## What Changes

- **New butler: Memory Butler** — a dedicated butler that owns a PostgreSQL database (`butler_memory` with pgvector), hosts an MCP server accessible to all other butlers, and runs background consolidation to transform raw session episodes into durable facts and learned rules.
- **Three memory types with separate schemas and lifecycles:**
  - *Episodes* — raw observations from CC sessions, short-lived (7-day TTL), source material for consolidation
  - *Facts* — distilled subject-predicate knowledge with subjective confidence decay (permanent → ephemeral)
  - *Rules* — learned behavioral patterns with maturity progression (candidate → established → proven) and anti-pattern inversion
- **Local-first embedding** — `sentence-transformers/all-MiniLM-L6-v2` (384-dim) loaded in-process for zero-latency search. No cloud round-trips.
- **Hybrid search** — pgvector cosine similarity + PostgreSQL tsvector full-text search, fused via Reciprocal Rank Fusion
- **Confidence decay** — facts and rules decay at subjective rates (permanence categories from `permanent` λ=0 to `ephemeral` λ=0.1). Re-confirmation resets decay. Forgetting is a feature.
- **Consolidation engine** — scheduled task that spawns CC instances to extract facts and rules from unconsolidated episodes, detect contradictions, and maintain provenance links
- **Memory context injection** — CC spawner calls `memory_context()` before spawning any CC instance, injecting a token-budgeted memory block into the system prompt
- **Session-to-episode pipeline** — butler daemons automatically store episodes after each CC session completes
- **Memory MCP tools** — store, search, recall, confirm, mark helpful/harmful, forget, stats, and context building
- **Dashboard integration** — butler-scoped memory tab, cross-butler `/memory` page, fact/rule editing, consolidation activity feed, health indicators

## Capabilities

### New Capabilities

- `memory-storage`: Episodes, facts, and rules tables with pgvector embeddings, tsvector search vectors, confidence decay, permanence categories, and provenance tracking. Includes the Alembic migration chain and all CRUD operations.
- `memory-search`: Hybrid retrieval (semantic, keyword, hybrid via RRF), composite scoring (relevance, importance, recency, confidence), scope filtering, and the `memory_recall` high-level API.
- `memory-mcp-tools`: The Memory MCP server tool surface — store/search/recall/get for reading and writing, confirm/mark-helpful/mark-harmful for feedback, forget/stats for management, and context building for CC injection.
- `memory-consolidation`: The consolidation engine that transforms episodes into facts and rules via scheduled CC sessions, plus decay sweep and episode cleanup tasks.
- `memory-rule-maturity`: Rule trust progression (candidate → established → proven), effectiveness scoring with 4x harmful weight, anti-pattern inversion, and demotion logic.
- `memory-butler-integration`: CC spawner integration (memory context injection + session-to-episode pipeline), butler.toml memory config, and Memory Butler registration with Switchboard.
- `memory-dashboard`: Dashboard API endpoints and frontend views — butler-scoped memory tab, cross-butler memory page, fact/rule CRUD, activity feed, health indicators, and global search integration.

### Modified Capabilities

*None — no existing specs to modify.*

## Impact

- **New dependencies:** `pgvector` PostgreSQL extension, `sentence-transformers` Python package (~80MB model), `asyncpg` for database access
- **New database:** `butler_memory` (dedicated PostgreSQL database for the Memory Butler)
- **CC spawner changes:** All butler daemons must call `memory_context()` before spawning and `memory_store_episode()` after session completion
- **MCP config changes:** Every butler's ephemeral MCP config gains the Memory MCP server alongside butler-specific tools
- **butler.toml schema:** New `[butler.memory]` config section for retrieval weights, confidence thresholds, and embedding settings
- **Switchboard:** Memory Butler registered as a routable butler
- **Dashboard:** New `/memory` top-level page, new memory tab on butler detail pages, memory events in unified timeline, facts/rules in global search
