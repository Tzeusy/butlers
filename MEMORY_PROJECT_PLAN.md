# Butler Memory System — Project Plan (Draft)

> This is a separate project plan for the memory subsystem. It will be integrated into the main PROJECT_PLAN.md once the design is solidified.

**Goal:** Give each butler a tiered memory system inspired by JVM generational garbage collection. Recent context lives in fast, volatile "Eden" memory. Frequently-referenced memories promote to longer-lived tiers. Unreferenced memories decay and eventually evict. All tiers are accessible to CC instances via MCP tools.

---

## Architecture: Generational Memory

```
┌─────────────────────────────────────────────────────────────┐
│                    Butler Memory System                      │
│                                                             │
│  ┌──────────────┐   promote    ┌──────────────┐  promote   │
│  │    Eden      │ ──────────▶  │   Mid-Term   │ ────────▶  │
│  │  (short-term)│   if ref'd   │   (working)  │  if ref'd  │
│  │              │              │              │            │
│  │ recent CC    │   evict      │ summarized   │  evict     │
│  │ sessions,    │ ◀──────────  │ insights,    │ ◀────────  │
│  │ raw context  │  if stale    │ patterns     │  if stale  │
│  └──────────────┘              └──────────────┘            │
│                                       │                     │
│                                  promote if ref'd           │
│                                       ▼                     │
│                              ┌──────────────┐               │
│                              │  Long-Term   │               │
│                              │  (identity)  │               │
│                              │              │               │
│                              │ core facts,  │               │
│                              │ preferences, │               │
│                              │ learned rules│               │
│                              └──────────────┘               │
└─────────────────────────────────────────────────────────────┘
```

### The Three Tiers

| Tier | Name | Lifespan | Contents | Capacity | Eviction |
|------|------|----------|----------|----------|----------|
| **Eden** | Short-term | Hours | Raw CC session transcripts, recent tool call results, immediate context | Large but aggressive eviction | LRU — unreferenced entries evict after N hours |
| **Mid-Term** | Working memory | Days–weeks | Summarized insights from Eden, patterns, in-progress knowledge, recent decisions | Medium | LRU — entries not referenced in N days decay |
| **Long-Term** | Identity memory | Months+ | Core facts, user preferences, learned rules, stable knowledge | Small, high-value | LRU — only evicts if truly never referenced; highest retention |

### LRU-Like Mechanism

Every memory entry tracks:
- `created_at` — when it was first stored
- `last_referenced_at` — last time a CC instance read or cited it
- `reference_count` — total times referenced
- `tier` — current tier (eden, mid, long)

**Promotion:** When an Eden entry is referenced across multiple CC sessions, it promotes to Mid-Term (typically as a summary). When a Mid-Term entry is referenced consistently over days, it promotes to Long-Term.

**Eviction:** Each tier has a capacity limit and a staleness threshold. Entries that haven't been referenced within the tier's threshold are candidates for eviction. The least-recently-referenced entries evict first.

**Summarization on promotion:** When an entry moves from Eden → Mid-Term, it gets summarized (by a CC instance) to extract the key insight. Raw transcripts compress into concise facts. Mid-Term → Long-Term promotion further distills into stable, atomic facts.

---

## Memory Entry Schema

```sql
CREATE TABLE memories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tier TEXT NOT NULL DEFAULT 'eden',       -- 'eden', 'mid', 'long'
    content TEXT NOT NULL,                    -- the memory content
    summary TEXT,                             -- summarized version (populated on promotion)
    tags JSONB NOT NULL DEFAULT '[]',         -- searchable tags
    source TEXT NOT NULL,                     -- 'session:<id>', 'promotion:<id>', 'manual'
    metadata JSONB NOT NULL DEFAULT '{}',     -- arbitrary structured data
    reference_count INT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_referenced_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    promoted_at TIMESTAMPTZ,                 -- when last promoted to current tier
    expires_at TIMESTAMPTZ                   -- computed from tier thresholds
);

CREATE INDEX idx_memories_tier ON memories(tier);
CREATE INDEX idx_memories_last_ref ON memories(last_referenced_at);
CREATE INDEX idx_memories_tags ON memories USING GIN(tags);
```

---

## MCP Tools

Core memory tools exposed by every butler:

```
Memory Tools
├── memory_store(content, tags?, tier?)     → store a new memory (defaults to Eden)
├── memory_search(query, tier?, limit?)     → semantic/tag search across tiers
├── memory_get(id)                          → retrieve a specific memory (bumps reference)
├── memory_recall(topic, limit?)            → retrieve relevant memories (bumps references)
├── memory_forget(id)                       → manually evict a memory
└── memory_stats()                          → counts and health per tier
```

**Key behavior:** `memory_search`, `memory_get`, and `memory_recall` all bump `last_referenced_at` and `reference_count`. This is the core mechanism that keeps important memories alive and lets unimportant ones decay.

---

## Lifecycle Flows

### 1. Session → Eden

After every CC session completes, the session log is automatically stored as an Eden memory:
```
CC session completes →
  daemon extracts key facts from session transcript →
  stores as Eden memory with tags derived from tool calls and content →
  sets expires_at = now() + eden_ttl (e.g., 24 hours)
```

### 2. Eden → Mid-Term Promotion

Periodically (e.g., on heartbeat tick), the butler checks Eden for promotion candidates:
```
For each Eden entry where reference_count >= threshold AND age >= min_age:
  spawn CC with prompt: "Summarize this into a concise insight: {content}"
  store summary as Mid-Term memory
  link to original Eden entry
  mark Eden entry for eviction (or keep as detail behind the summary)
```

### 3. Mid-Term → Long-Term Promotion

Less frequently, the butler checks Mid-Term for promotion:
```
For each Mid-Term entry where reference_count >= threshold AND age >= min_age:
  spawn CC with prompt: "Distill this into a core fact or rule: {content}"
  store as Long-Term memory
  Long-Term entries have very long or no expiry
```

### 4. Eviction Sweep

On each tick (or dedicated memory maintenance task):
```
For each tier:
  evict entries where expires_at < now() AND reference_count < protection_threshold
  OR evict LRU entries when tier exceeds capacity limit
```

---

## Configuration

```toml
# In butler.toml (future)
[butler.memory]
enabled = true

[butler.memory.eden]
ttl_hours = 24              # entries expire after 24h if unreferenced
max_entries = 1000
promote_after_refs = 3       # promote to mid after 3 references
promote_after_hours = 6      # minimum age before promotion

[butler.memory.mid]
ttl_days = 30
max_entries = 500
promote_after_refs = 10
promote_after_days = 7

[butler.memory.long]
ttl_days = 365              # very long retention
max_entries = 200
```

---

## Integration with Core Components

- **Session Log → Eden:** Every CC session result automatically becomes an Eden memory
- **Scheduler:** Memory maintenance (promotion, eviction) runs as a scheduled task
- **CC Spawner:** Each CC instance gets relevant memories injected into its context (e.g., "Here are your recent memories about this topic: ...")
- **State Store:** Memory system is separate from the state store. State is for structured KV data. Memory is for unstructured, decaying, promotable knowledge.

---

## Open Questions

| Question | Notes |
|----------|-------|
| Semantic search vs tag-based search? | Start with tag-based + full-text. Add embeddings later if needed. |
| Who does the summarization on promotion? | A CC instance triggered by the butler. Cost consideration: each promotion costs a CC invocation. |
| Should CC instances automatically recall relevant memories? | Could inject relevant memories into the system prompt based on the trigger prompt. |
| Memory sharing between butlers? | Strict isolation per butler DB. Butlers could share memories via Switchboard MCP tools if needed. |
| Embedding storage for semantic search? | pgvector extension? Separate vector store? Defer to v2. |
| How to handle memory conflicts? | If two CC sessions store contradictory facts, how to resolve? Probably last-write-wins for Eden, manual curation for Long-Term. |
| Cost control for promotion summarization | Batch promotions? Use a cheaper model for summarization? |
