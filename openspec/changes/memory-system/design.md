## Context

Butlers currently have no shared memory. Each CC session starts from a blank slate — the only persistence is per-butler state store (KV JSONB) and session logs. The Memory Butler introduces institutional memory as a dedicated butler that owns a PostgreSQL database with pgvector, hosts an MCP server, and runs background consolidation.

The existing codebase provides all the infrastructure needed: the Module ABC with `register_tools()`, programmatic Alembic migrations with branch labels, asyncpg connection pools, the CC spawner with MCP config generation, and per-butler database isolation. Memory needs to fill in the domain logic within these patterns.

## Goals / Non-Goals

**Goals:**

- Shared memory accessible to all butlers via MCP tools
- Three distinct memory types (episodes, facts, rules) with separate schemas, lifecycles, and query patterns
- Local-first embedding (no cloud round-trips for search)
- Hybrid search combining semantic similarity and keyword matching
- Subjective confidence decay so memories fade naturally without manual cleanup
- Rule maturity system that earns trust through successful application and penalizes harmful rules aggressively
- Consolidation engine that transforms raw episodes into durable knowledge via scheduled CC sessions
- Memory context injection into every CC instance's system prompt
- Full dashboard visibility and user editability

**Non-Goals:**

- Knowledge graph / graph database — memory_links provide lightweight provenance, not a full graph
- Multi-user / multi-tenant — one deployment serves one user, one memory database
- Real-time consolidation — episodes batch-process on a schedule, not inline during sessions
- Cloud embedding APIs — local model only, even if slightly less capable
- Full session transcript storage — episodes contain extracted observations, not raw transcripts
- Cross-deployment federation — no syncing memory between separate butlers deployments

## Decisions

### D1: Memory Butler as a standard butler, not a framework-level service

**Decision:** The Memory Butler is a normal butler with its own `butlers/memory/` config directory, `butler.toml`, `tools.py`, and migrations. It is not a special framework construct.

**Rationale:** The butler framework already provides everything needed: database provisioning, MCP server hosting, scheduled tasks, CC spawning. Making memory "special" would violate the principle that all butlers are peers. The Memory Butler's uniqueness is that other butlers' CC configs include its MCP server — but that's a spawner config concern, not an architectural exception.

**Alternative considered:** A core framework module that runs inside every butler. Rejected because memory needs its own database (cross-butler shared state violates per-butler isolation), its own scheduled tasks (consolidation, decay sweeps), and its own CC instances (for consolidation prompts). A module can't own a separate database.

### D2: Memory tools in `butlers/memory/tools.py`, not a Module subclass

**Decision:** Memory tools are implemented as butler-specific tool functions in `butlers/memory/tools.py`, following the same pattern as `butlers/general/tools.py`. Not as a `Module` subclass.

**Rationale:** Modules are opt-in plugins that individual butlers enable via `[modules.X]` in their `butler.toml`. Memory isn't opt-in for the Memory Butler — it's the butler's entire purpose. The existing pattern of butler-specific tools in `tools.py` is the right fit. Other butlers access memory tools via the Memory MCP server in their CC config, not by loading a module.

**Alternative considered:** A `MemoryModule` that the Memory Butler enables. Adds indirection without benefit — the Memory Butler would be the only consumer.

### D3: Embedding via `sentence-transformers` loaded in-process

**Decision:** Use `sentence-transformers/all-MiniLM-L6-v2` (384-dim, ~80MB), loaded once at Memory Butler startup and held in memory for the process lifetime.

**Rationale:** At our scale (<20k rows), embedding latency matters more than model quality. MiniLM-L6 produces embeddings in ~5ms on CPU. No network calls, no API costs, no availability dependencies. The model is small enough to hold in memory alongside the butler process.

**Alternative considered:** OpenAI/Anthropic embedding APIs — better quality but adds latency, cost, and a hard dependency on external services. Not worth it for a personal-scale system. Can revisit if local quality proves insufficient.

### D4: pgvector with IVFFlat indexing

**Decision:** Use pgvector for vector storage and cosine similarity search. IVFFlat index with 20 lists.

**Rationale:** pgvector keeps everything in PostgreSQL — no separate vector database to operate. At our expected scale (500-2000 facts, 50-200 rules, 35-350 active episodes), IVFFlat with 20 lists is sufficient. HNSW would be overkill and uses more memory.

**Alternative considered:** Dedicated vector DB (Qdrant, Weaviate, Milvus). Rejected — adds operational complexity for no benefit at personal scale. pgvector is good enough and keeps the stack simple.

### D5: Hybrid search via Reciprocal Rank Fusion

**Decision:** Support three search modes: `semantic` (pgvector cosine), `keyword` (tsvector/tsquery), `hybrid` (both fused via RRF). Default to `hybrid`.

**Rationale:** Semantic search handles conceptual similarity ("feeling unwell" matches "nausea symptoms") while keyword search handles exact matches ("Dr. Smith", "lactose"). RRF is a simple, parameter-free fusion method that doesn't require tuning — it just merges ranked lists. The `k=60` constant is well-established in IR literature.

**Alternative considered:** Weighted linear combination of scores. Rejected because semantic and keyword scores are on different scales — normalizing them correctly is fiddly. RRF operates on ranks, which sidesteps the normalization problem.

### D6: Exponential confidence decay with permanence categories

**Decision:** Confidence decays exponentially: `effective = confidence × exp(-λ × days)`. The Memory Butler assigns a permanence category (permanent/stable/standard/volatile/ephemeral) at consolidation time, which sets λ.

**Rationale:** Exponential decay models human forgetting (Ebbinghaus curve). Permanence categories make the decay rate a semantic judgment call for the LLM, not a numerical parameter. "User's name is John" → permanent (λ=0). "Had ramen for dinner" → ephemeral (λ=0.1, half-life ~7 days). The LLM is good at this classification.

**Alternative considered:** Fixed decay rate for all memories. Rejected — a single rate can't serve both permanent identity facts and ephemeral observations.

### D7: Consolidation as scheduled batch CC sessions

**Decision:** Consolidation runs every 6 hours as a scheduled task. The Memory Butler spawns a CC instance with a consolidation prompt that includes unconsolidated episodes and existing facts/rules. The CC output is parsed to extract new facts, updated facts, new rules, and confirmations.

**Rationale:** Consolidation requires LLM judgment (classifying permanence, detecting patterns, resolving contradictions). Running it as a CC session reuses the existing spawner infrastructure. Batching every 6 hours is cost-efficient and keeps episode volume manageable per batch.

**Alternative considered:** Real-time consolidation during each CC session. Rejected — adds latency to every session, forces each butler's CC to handle memory consolidation concerns, and makes deduplication harder since facts arrive piecemeal.

### D8: Memory context injection via spawner hook

**Decision:** The CC spawner calls `memory_context(trigger_prompt, butler_name)` before spawning any CC instance. The Memory MCP server returns a formatted text block (within a token budget, default 3000 tokens) that gets injected into the system prompt after the butler's `CLAUDE.md`.

**Rationale:** Memory context must be present from the start of a CC session — it can't be fetched mid-conversation. The spawner already builds the system prompt from `CLAUDE.md` and skills; memory context is another section appended to it. Token budgeting prevents memory from consuming too much context.

**Implementation note:** The spawner must make an MCP call to the Memory Butler's server before spawning. This means the Memory Butler must be running before other butlers can spawn CC instances. This is acceptable — memory is infrastructure, and startup ordering is already handled by the Switchboard.

### D9: Episode extraction as lightweight summaries, not full transcripts

**Decision:** After a CC session completes, the butler daemon stores an episode containing key observations extracted from the session — not the full transcript. Extraction uses the CC response summary or a cheap LLM call.

**Rationale:** Full transcripts are noisy and expensive to embed/search. Episodes should capture "what happened that matters" — user preferences discovered, decisions made, corrections given. The consolidation engine then further distills these into facts and rules. Two-stage distillation (transcript → episode → fact) produces cleaner knowledge.

**Alternative considered:** Store full transcripts as episodes. Rejected — wastes storage, makes embedding less meaningful (long text → poor vector representation), and pushes all extraction work to consolidation.

### D10: Fact supersession via subject-predicate deduplication

**Decision:** When `memory_store_fact` receives a fact with the same `subject + predicate` as an existing active fact, the new fact automatically supersedes the old one. The old fact's `validity` is set to `superseded`, and the new fact's `supersedes_id` points to it.

**Rationale:** Simple, deterministic contradiction resolution for the common case. "User's favorite color is blue" naturally supersedes "User's favorite color is green" because they share `subject=user, predicate=favorite_color`. The supersession chain provides an audit trail. Complex contradictions (different subjects, ambiguous predicates) are left for LLM judgment during consolidation.

### D11: Anti-pattern inversion for repeatedly harmful rules

**Decision:** Rules marked harmful 3+ times with effectiveness_score < 0.3 are inverted into anti-pattern warnings: "ANTI-PATTERN: Do NOT {original rule}. This caused problems because: {harmful feedback}".

**Rationale:** Deleting harmful rules risks re-learning them. Inverting preserves the knowledge as a negative constraint. The 4x weight on harmful marks (effectiveness = success / (success + 4×harmful)) ensures bad rules are penalized quickly — a rule that helps 10 times but harms twice scores only 0.56, below the `established` threshold.

### D12: Dashboard reads database directly, writes go through MCP

**Decision:** The dashboard API reads `butler_memory` via direct SQL (read-only connection). All writes (edit fact, delete rule, etc.) go through the Memory MCP server.

**Rationale:** Follows the existing dashboard pattern. Direct reads are faster and simpler for browse/search/filter operations. Routing writes through MCP ensures all business logic (supersession, provenance tracking, embedding generation) is applied consistently. The MCP server is the single source of truth for write operations.

## Risks / Trade-offs

**[Risk] Embedding model quality may be insufficient for nuanced queries**
→ MiniLM-L6 is a trade-off: fast and local, but less capable than larger models. Mitigation: hybrid search compensates — keyword search catches what semantic misses. If quality proves insufficient, the embedding model can be swapped (re-embed all rows, takes seconds at our scale).

**[Risk] Consolidation prompt may extract low-quality facts or miss important ones**
→ LLM judgment is imperfect. Mitigation: facts start with high confidence and decay naturally — bad extractions fade. Rules start as candidates and must earn trust. Users can correct via dashboard. The system is self-healing over time.

**[Risk] Memory Butler must be running before other butlers can spawn CC instances**
→ Creates a startup dependency. Mitigation: if memory_context fails, the spawner falls back to spawning without memory context (degraded but functional). Memory is additive — butlers work fine without it, just without recall.

**[Risk] Token budget may be too small for butlers with rich memory**
→ 3000 tokens (~2250 words) limits how much memory fits in context. Mitigation: configurable per butler via `butler.toml`. Composite scoring ensures the most relevant memories are selected. Butlers that need more can increase the budget at the cost of less room for conversation.

**[Risk] 6-hour consolidation delay means recent episodes aren't yet distilled**
→ Facts from the current session aren't available until the next consolidation run. Mitigation: `memory_store_fact` allows CC instances to store facts directly during a session for immediately important knowledge. The consolidation engine handles the bulk processing.

**[Trade-off] Per-butler database isolation vs. shared memory database**
→ Memory is the one exception to the "one DB per butler" rule — it's a shared database by design. This is architecturally acceptable because memory is read-heavy and the Memory Butler is the sole writer (via MCP). Other butlers never write to `butler_memory` directly.

**[Trade-off] sentence-transformers dependency adds ~80MB to install**
→ Acceptable for a server-side daemon that runs long-term. The model loads once at startup. Docker image size increases but runtime impact is minimal (model stays in memory).

## Migration Plan

1. **Database setup:** Create `butler_memory` database. Run Alembic migrations for episodes, facts, rules, and memory_links tables. Enable pgvector and uuid-ossp extensions.
2. **Memory Butler deploy:** Deploy as a standard butler (port 8150). Verify MCP server starts and tools are callable.
3. **Embedding verification:** Confirm MiniLM-L6 loads at startup. Test embedding generation and vector search on sample data.
4. **Integration rollout:** Update CC spawner to call `memory_context` and `memory_store_episode`. Wire Memory MCP server into all butlers' CC configs. This can be done butler-by-butler.
5. **Consolidation enable:** Enable scheduled consolidation once episodes are flowing. Monitor extraction quality and tune the prompt.
6. **Dashboard integration:** Add memory API endpoints, then frontend views. Can deploy incrementally.
7. **Rollback:** If memory causes issues, remove the Memory MCP server from CC configs. Butlers revert to stateless sessions. Memory data persists in `butler_memory` for later re-integration.

## Open Questions

1. **Episode extraction method:** Should episode extraction use the CC response summary (free, available immediately), a cheap LLM call (better quality, adds latency), or a configurable choice per butler?
2. **Cross-butler memory visibility:** Should a butler's CC instance see facts scoped to other butlers, or only `global` + its own scope? The project plan says "any butler can access any memory" but scope filtering defaults to butler-specific.
3. **Consolidation prompt iteration:** The consolidation prompt is the most critical piece of the system. How much iteration/testing is needed before it's reliable enough for production?
