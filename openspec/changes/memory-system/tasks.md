## 1. Memory Butler Scaffold & Database Schema

- [ ] 1.1 Create `butlers/memory/` config directory with `butler.toml`, `MANIFESTO.md`, `CLAUDE.md`, `AGENTS.md`
- [ ] 1.2 Add `sentence-transformers` and `pgvector` (asyncpg pgvector support) to project dependencies in `pyproject.toml`
- [ ] 1.3 Create Alembic migration `001_create_episodes` — episodes table with all columns, indexes (butler+created_at, expires_at, unconsolidated, GIN search_vector), branch label `memory`
- [ ] 1.4 Create Alembic migration `002_create_facts` — facts table with all columns, indexes (scope+validity partial, subject+predicate, GIN search_vector, GIN tags), FK to episodes
- [ ] 1.5 Create Alembic migration `003_create_rules` — rules table with all columns, indexes (scope+maturity, GIN search_vector), FK to episodes
- [ ] 1.6 Create Alembic migration `004_create_memory_links` — memory_links table with composite PK, target index
- [ ] 1.7 Create Alembic migration `005_add_vector_indexes` — enable pgvector + uuid-ossp extensions, add IVFFlat indexes (20 lists) on episodes.embedding, facts.embedding, rules.embedding
- [ ] 1.8 Register memory migration chain in `src/butlers/migrations.py` (add `"memory"` to shared chains)
- [ ] 1.9 Write tests: migration chain runs cleanly against empty database, all tables and indexes created

## 2. Embedding Engine

- [ ] 2.1 Create `butlers/memory/embedding.py` — EmbeddingEngine class that loads `all-MiniLM-L6-v2` at init time and exposes `embed(text) -> list[float]` and `embed_batch(texts) -> list[list[float]]`
- [ ] 2.2 Create `butlers/memory/search_vector.py` — helper to generate tsvector content from text (for populating `search_vector` columns at write time)
- [ ] 2.3 Write tests: embedding produces 384-dim vectors, batch embedding matches individual results, search vector generation handles edge cases (empty text, special characters)

## 3. Core Storage Operations (CRUD)

- [ ] 3.1 Create `butlers/memory/storage.py` — episode CRUD: `store_episode(pool, content, butler, embedding_engine, ...)` generates embedding + search_vector, inserts row, returns UUID
- [ ] 3.2 Add fact CRUD to storage.py: `store_fact(pool, subject, predicate, content, embedding_engine, ...)` with permanence-to-decay_rate mapping, subject-predicate conflict check, and automatic supersession (update old fact validity, set supersedes_id, create memory_link)
- [ ] 3.3 Add rule CRUD to storage.py: `store_rule(pool, content, embedding_engine, ...)` creates rule as candidate with confidence=0.5
- [ ] 3.4 Add memory_links CRUD to storage.py: `create_link(pool, source_type, source_id, target_type, target_id, relation)`
- [ ] 3.5 Add `get_memory(pool, type, id)` — retrieve single memory by type+UUID, bump reference_count and last_referenced_at
- [ ] 3.6 Add `forget_memory(pool, type, id)` — set validity to 'forgotten'
- [ ] 3.7 Add permanence validation — reject invalid permanence values, map permanence to decay_rate constants
- [ ] 3.8 Write tests: store/get/forget for each type, supersession creates correct links, permanence mapping, invalid permanence rejected

## 4. Search & Retrieval

- [ ] 4.1 Create `butlers/memory/search.py` — `semantic_search(pool, query_embedding, table, limit, scope?)` using pgvector `<=>` operator
- [ ] 4.2 Add `keyword_search(pool, query_text, table, limit, scope?)` using tsvector/tsquery
- [ ] 4.3 Add `hybrid_search(pool, query_text, query_embedding, table, limit, scope?)` — run both searches, fuse via RRF (`k=60`), handle results appearing in only one list
- [ ] 4.4 Add composite scoring function: `compute_composite_score(relevance, importance, recency, effective_confidence, weights)` with default weights (0.4, 0.3, 0.2, 0.1)
- [ ] 4.5 Add `recall(pool, topic, embedding_engine, scope?, limit?, min_confidence?, weights?)` — embed topic, hybrid search facts+rules, compute composite scores, filter by effective confidence threshold, bump reference counts, return sorted results
- [ ] 4.6 Add `search(pool, query, embedding_engine, types?, scope?, mode?, limit?, min_confidence?)` — general search across specified types with mode selection
- [ ] 4.7 Add effective confidence computation: `effective_confidence(confidence, decay_rate, last_confirmed_at)` using `confidence × exp(-λ × days)`
- [ ] 4.8 Add scope filtering: facts/rules filter `scope IN ('global', <scope>)`, episodes filter `butler = <scope>`
- [ ] 4.9 Write tests: semantic search ranking, keyword search with stemming, hybrid RRF fusion, composite scoring math, effective confidence decay math, scope filtering, reference count bumping, min_confidence filtering

## 5. Confidence Decay & Rule Maturity

- [ ] 5.1 Add `confirm_memory(pool, type, id)` — reset `last_confirmed_at` to now for facts/rules, reject episodes
- [ ] 5.2 Add `mark_helpful(pool, rule_id)` — increment success_count + applied_count, recalculate effectiveness_score, update last_applied_at, evaluate maturity promotion (candidate→established: success≥5 && effectiveness≥0.6; established→proven: success≥15 && effectiveness≥0.8 && age≥30d)
- [ ] 5.3 Add `mark_harmful(pool, rule_id, reason?)` — increment harmful_count + applied_count, recalculate effectiveness_score with 4x weight (`success / (success + 4×harmful + 0.01)`), evaluate demotion (effectiveness below current level threshold), evaluate anti-pattern inversion (harmful≥3 && effectiveness<0.3)
- [ ] 5.4 Implement anti-pattern inversion: rewrite rule content as "ANTI-PATTERN: Do NOT {original}. This caused problems because: {reasons}", set maturity to anti-pattern state
- [ ] 5.5 Add `run_decay_sweep(pool)` — compute effective_confidence for all active facts/rules, mark fading (0.05≤eff<0.2), expire (eff<0.05 → validity='expired')
- [ ] 5.6 Write tests: confirm resets decay clock, mark_helpful promotion thresholds, mark_harmful demotion + 4x weight, effectiveness_score formula, anti-pattern inversion trigger + content rewrite, decay sweep transitions (active→fading→expired), permanent facts never decay

## 6. Memory MCP Tools

- [ ] 6.1 Create `butlers/memory/tools.py` — register all memory tools on the Memory Butler's FastMCP server following the `@mcp.tool()` pattern from existing butlers
- [ ] 6.2 Implement writing tools: `memory_store_episode`, `memory_store_fact`, `memory_store_rule` — each delegates to storage.py and returns the created ID
- [ ] 6.3 Implement reading tools: `memory_search`, `memory_recall`, `memory_get` — each delegates to search.py/storage.py
- [ ] 6.4 Implement feedback tools: `memory_confirm`, `memory_mark_helpful`, `memory_mark_harmful` — each delegates to the corresponding function in storage/maturity
- [ ] 6.5 Implement management tools: `memory_forget`, `memory_stats` (counts by type, scope, status — active/fading/expired facts, candidate/established/proven rules, total/unconsolidated episodes, backlog age)
- [ ] 6.6 Implement `memory_context` tool — embed trigger prompt, query top-scored facts+rules for butler scope, format as structured text block within token budget, order by score (highest first), include recent episodes section
- [ ] 6.7 Initialize EmbeddingEngine at Memory Butler startup (load MiniLM-L6 model once, hold in memory)
- [ ] 6.8 Write tests: each MCP tool callable with valid args, error cases (nonexistent ID, invalid type, confirm on episode), memory_context respects token budget and score ordering

## 7. Consolidation Engine

- [ ] 7.1 Create `butlers/memory/consolidation.py` — `run_consolidation(pool, spawner, embedding_engine)`: fetch unconsolidated episodes, group by butler
- [ ] 7.2 Build consolidation prompt template — include episodes, existing active facts (scoped), existing active rules (scoped), extraction instructions (new facts with permanence, updated facts with supersession, new rules, confirmations)
- [ ] 7.3 Implement consolidation output parser — parse CC response into structured actions: new facts (with permanence), superseded facts, new rules, confirmations, provenance links
- [ ] 7.4 Implement consolidation executor — for each parsed action: store facts/rules via storage.py, create derived_from/supports/contradicts links via memory_links, call confirm on referenced facts, mark processed episodes as `consolidated=true`
- [ ] 7.5 Create `butlers/memory/skills/consolidate/SKILL.md` — skill documentation for the consolidation CC session
- [ ] 7.6 Add `run_episode_cleanup(pool, max_entries)` — delete expired episodes, enforce capacity cap, protect unconsolidated unexpired episodes
- [ ] 7.7 Wire scheduled tasks in `butlers/memory/butler.toml`: consolidate (0 */6 * * *), decay_sweep (0 3 * * *), episode_cleanup (0 4 * * *)
- [ ] 7.8 Write tests: consolidation groups by butler, prompt includes existing facts/rules, output parser handles valid/malformed CC output, episode cleanup respects unconsolidated protection, full consolidation pipeline integration test (episodes → CC → facts + rules + links)

## 8. Butler Integration

- [ ] 8.1 Update `src/butlers/core/spawner.py` — before spawning CC, call `memory_context(trigger_prompt, butler_name)` on Memory MCP server, inject returned block into system prompt after CLAUDE.md
- [ ] 8.2 Add graceful fallback in spawner — if memory_context call fails (Memory Butler unreachable), log warning and spawn without memory context
- [ ] 8.3 Update spawner post-session — after CC session completes, call `memory_store_episode(content, butler, session_id)` on Memory MCP server with extracted session observations
- [ ] 8.4 Add graceful fallback for episode storage — if memory_store_episode fails, log warning, do not block session completion
- [ ] 8.5 Update ephemeral MCP config generation — include Memory MCP server (port 8150) in all butlers' CC instance configs alongside butler-specific tools
- [ ] 8.6 Add `[butler.memory]` config section support to config.py — parse retrieval weights, confidence thresholds, token budget from butler.toml
- [ ] 8.7 Register Memory Butler with Switchboard as a routable butler
- [ ] 8.8 Write tests: spawner injects memory context, spawner handles Memory Butler unavailability, episode stored after session, MCP config includes memory server, end-to-end test (trigger → session → episode → consolidation → fact retrieval)

## 9. Dashboard Integration

- [ ] 9.1 Implement dashboard API: `GET /api/memory/stats` — system-wide counts (facts by permanence, rules by maturity, episodes total/unconsolidated, fading count)
- [ ] 9.2 Implement dashboard API: `GET /api/memory/facts` with query params (scope, subject, q, min_confidence), `GET /api/memory/facts/:id` with provenance/links
- [ ] 9.3 Implement dashboard API: `PUT /api/memory/facts/:id` (edit → create superseding fact via MCP), `DELETE /api/memory/facts/:id` (soft-delete via MCP)
- [ ] 9.4 Implement dashboard API: `GET /api/memory/rules` with query params (scope, maturity, q), `GET /api/memory/rules/:id` with application history
- [ ] 9.5 Implement dashboard API: `PUT /api/memory/rules/:id` (edit → reset maturity to candidate via MCP), `DELETE /api/memory/rules/:id` (soft-delete via MCP)
- [ ] 9.6 Implement dashboard API: `GET /api/memory/episodes` with query params (butler, from, to), `GET /api/memory/episodes/:id`
- [ ] 9.7 Implement dashboard API: `GET /api/memory/activity` — consolidation activity feed (fact creations, rule promotions, supersessions, expirations, anti-pattern inversions)
- [ ] 9.8 Implement butler-scoped endpoints: `GET /api/butlers/:name/memory/{stats,facts,rules,episodes}`
- [ ] 9.9 Build butler memory tab frontend (`/butlers/:name/memory`) — facts panel (cards grouped by subject, confidence bars, permanence badges), playbook panel (rules by maturity, effectiveness scores), episode stream (chronological, consolidated badges)
- [ ] 9.10 Build cross-butler memory page frontend (`/memory`) — overview cards, knowledge browser with search/filters, consolidation activity feed, health indicators (confidence distribution, episode backlog, rule effectiveness)
- [ ] 9.11 Add memory events to unified timeline — fact created, rule promoted, fact expired, anti-pattern inverted
- [ ] 9.12 Add facts and rules to global search (Cmd+K) — memory type badge, content preview, scope, confidence/maturity
- [ ] 9.13 Write tests: API endpoint responses match expected formats, scope filtering on butler-scoped endpoints, fact edit creates supersession, fact delete sets validity to forgotten
