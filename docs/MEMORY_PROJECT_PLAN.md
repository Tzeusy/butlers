# Butler Memory System — Project Plan

> The shared institutional memory for the butler ecosystem. A dedicated Memory Butler owns a PostgreSQL database with pgvector, hosts an MCP server that all butlers connect to, and runs background consolidation to transform raw session episodes into durable facts and learned rules.

---

## Design Principles

1. **Three memory types, not three tiers.** Episodic, semantic, and procedural memory have genuinely different schemas, lifecycles, and query patterns. They get separate tables, not a polymorphic blob.
2. **Shared by default, scoped when needed.** All memory lives in one database (`butler_memory`). Any butler can access any memory. Butler-specific knowledge uses a `scope` field, not a separate store.
3. **Forgetting is a feature.** Every fact has a subjective decay rate assigned by the Memory Butler at consolidation time. Identity facts never decay. Yesterday's lunch fades in days. Unreferenced memories expire naturally.
4. **Local-first retrieval.** Embeddings are generated in-process by a local model (sentence-transformers MiniLM-L6). No cloud round-trips for search. LLM calls are reserved for consolidation, which runs offline in background batches.
5. **The user can see and edit everything.** The dashboard exposes facts, rules, and episodes with full provenance. Users can correct wrong facts, promote/demote rules, and delete anything. Trust requires transparency.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                    Memory Butler (port 8150)                      │
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌─────────────────────────┐ │
│  │ MCP Server   │  │ Embedding    │  │ Consolidation Engine    │ │
│  │              │  │ Engine       │  │ (scheduled, batched)    │ │
│  │ store/search │  │              │  │                         │ │
│  │ recall/forget│  │ MiniLM-L6   │  │ episodes → facts/rules  │ │
│  │ confirm/mark │  │ 384-dim     │  │ dedup & supersession    │ │
│  │              │  │ in-process   │  │ decay sweep             │ │
│  └──────┬───────┘  └──────┬───────┘  └───────────┬─────────────┘ │
│         │                 │                      │               │
│         └─────────────────┴──────────────────────┘               │
│                            │                                     │
│                            ▼                                     │
│              ┌──────────────────────────────┐                    │
│              │  PostgreSQL: butler_memory    │                    │
│              │                              │                    │
│              │  episodes │ facts │ rules    │                    │
│              │  memory_links                │                    │
│              │  + pgvector + tsvector       │                    │
│              └──────────────────────────────┘                    │
└──────────────────────────────────────────────────────────────────┘
         ▲           ▲           ▲           ▲
         │ MCP       │ MCP       │ MCP       │ SQL (read-only)
    ┌────┴───┐  ┌────┴───┐  ┌───┴────┐  ┌───┴────────┐
    │Health  │  │General │  │Relation│  │Dashboard   │
    │Butler  │  │Butler  │  │Butler  │  │API         │
    └────────┘  └────────┘  └────────┘  └────────────┘
```

The Memory Butler is both a standard butler (with its own CC instances for consolidation tasks) and the host of the shared Memory MCP server. Every other butler's CC instances get the Memory MCP server wired into their ephemeral MCP config alongside their butler-specific tools.

The Dashboard API reads `butler_memory` directly for frontend views (same pattern as other butler DBs — read-only SQL, writes go through MCP).

---

## The Three Memory Types

### Episodes (What Happened)

Raw observations extracted from CC sessions. High volume, short-lived. The source material that consolidation transforms into durable facts and rules.

**Examples:**
- "User asked health butler to log weight 75kg, mentioned they started a new diet last week"
- "Relationship butler drafted a birthday message for Maria, user edited the tone to be more casual"
- "General butler created a recipe entity, user specified ingredients should always be listed, not prose"

**Lifecycle:** Created automatically after each CC session. Expire after a configurable TTL (default 7 days). Most episodes expire without promotion — this is expected and correct. Only notable observations survive consolidation.

### Facts (What Is True)

Distilled knowledge with subject-predicate structure. The core of the memory system. Facts have subjective confidence decay — identity facts never fade, preferences drift, ephemeral observations vanish in days.

**Examples:**
- `subject="user", predicate="name", content="John"` — permanence: permanent
- `subject="user", predicate="dietary_restriction", content="Lactose intolerant"` — permanence: stable
- `subject="user", predicate="current_interest", content="Currently reading Dune"` — permanence: standard
- `subject="user", predicate="recent_meal", content="Had ramen for dinner"` — permanence: ephemeral

**Lifecycle:** Created by the consolidation engine from episodes, or manually by a CC instance via `memory_store_fact`. Confidence decays at a per-fact rate. Facts below the retrieval threshold fade from agent context but remain in the DB for dashboard visibility. Superseded facts keep an audit trail.

### Rules (How To Do Things)

Learned behavioral patterns — the system's procedural playbook. Rules earn trust through a maturity progression and can be marked as harmful. Inspired by the CASS Memory System's playbook pattern.

**Examples:**
- "Always confirm with the user before sending outbound telegram messages" — scope: global, maturity: proven
- "When user says 'feeling off', they usually mean mild nausea, not mood" — scope: health, maturity: established
- "For the recipes collection, format ingredients as a bulleted list" — scope: general, maturity: candidate

**Lifecycle:** Created by the consolidation engine when patterns are detected across episodes, or manually. Rules start as candidates and must earn trust through successful application. Harmful marks carry 4x the weight of success marks, ensuring bad rules are demoted quickly.

---

## Database Schema

### Prerequisites

```sql
CREATE EXTENSION IF NOT EXISTS vector;        -- pgvector
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";   -- gen_random_uuid fallback
```

### Episodes

```sql
CREATE TABLE episodes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    butler TEXT NOT NULL,
    session_id UUID,
    content TEXT NOT NULL,
    embedding vector(384),
    search_vector tsvector,

    importance FLOAT NOT NULL DEFAULT 5.0,
    reference_count INT NOT NULL DEFAULT 0,
    consolidated BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_referenced_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL DEFAULT (now() + INTERVAL '7 days'),

    metadata JSONB NOT NULL DEFAULT '{}'
);

CREATE INDEX idx_episodes_butler ON episodes(butler, created_at DESC);
CREATE INDEX idx_episodes_expires ON episodes(expires_at) WHERE expires_at IS NOT NULL;
CREATE INDEX idx_episodes_unconsolidated ON episodes(created_at)
    WHERE consolidated = false;
CREATE INDEX idx_episodes_embedding ON episodes
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 20);
CREATE INDEX idx_episodes_search ON episodes USING GIN(search_vector);
```

### Facts

```sql
CREATE TABLE facts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    subject TEXT NOT NULL,
    predicate TEXT NOT NULL,
    content TEXT NOT NULL,
    embedding vector(384),
    search_vector tsvector,

    -- Scoring & decay
    importance FLOAT NOT NULL DEFAULT 5.0,
    confidence FLOAT NOT NULL DEFAULT 1.0,
    decay_rate FLOAT NOT NULL DEFAULT 0.008,
    permanence TEXT NOT NULL DEFAULT 'standard',

    -- Provenance
    source_butler TEXT,
    source_episode_id UUID REFERENCES episodes(id) ON DELETE SET NULL,
    supersedes_id UUID REFERENCES facts(id) ON DELETE SET NULL,
    validity TEXT NOT NULL DEFAULT 'active',
    scope TEXT NOT NULL DEFAULT 'global',

    -- Lifecycle
    reference_count INT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_referenced_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_confirmed_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    tags JSONB NOT NULL DEFAULT '[]',
    metadata JSONB NOT NULL DEFAULT '{}'
);

CREATE INDEX idx_facts_scope_validity ON facts(scope, validity)
    WHERE validity = 'active';
CREATE INDEX idx_facts_subject ON facts(subject, predicate);
CREATE INDEX idx_facts_embedding ON facts
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 20);
CREATE INDEX idx_facts_search ON facts USING GIN(search_vector);
CREATE INDEX idx_facts_tags ON facts USING GIN(tags);
```

### Rules

```sql
CREATE TABLE rules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    content TEXT NOT NULL,
    embedding vector(384),
    search_vector tsvector,
    scope TEXT NOT NULL DEFAULT 'global',

    -- Maturity & effectiveness
    maturity TEXT NOT NULL DEFAULT 'candidate',
    confidence FLOAT NOT NULL DEFAULT 0.5,
    decay_rate FLOAT NOT NULL DEFAULT 0.008,
    permanence TEXT NOT NULL DEFAULT 'standard',
    effectiveness_score FLOAT NOT NULL DEFAULT 0.0,
    applied_count INT NOT NULL DEFAULT 0,
    success_count INT NOT NULL DEFAULT 0,
    harmful_count INT NOT NULL DEFAULT 0,

    -- Provenance
    source_episode_id UUID REFERENCES episodes(id) ON DELETE SET NULL,
    source_butler TEXT,

    -- Lifecycle
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_applied_at TIMESTAMPTZ,
    last_evaluated_at TIMESTAMPTZ,

    tags JSONB NOT NULL DEFAULT '[]',
    metadata JSONB NOT NULL DEFAULT '{}'
);

CREATE INDEX idx_rules_scope_maturity ON rules(scope, maturity);
CREATE INDEX idx_rules_embedding ON rules
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 20);
CREATE INDEX idx_rules_search ON rules USING GIN(search_vector);
```

### Memory Links

Lightweight provenance and relationship tracking. Not a full knowledge graph — just enough to trace how facts were derived from episodes, which facts support which rules, and where contradictions exist.

```sql
CREATE TABLE memory_links (
    source_type TEXT NOT NULL,
    source_id UUID NOT NULL,
    target_type TEXT NOT NULL,
    target_id UUID NOT NULL,
    relation TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (source_type, source_id, target_type, target_id)
);

CREATE INDEX idx_memory_links_target ON memory_links(target_type, target_id);
```

**Relation types:**
- `derived_from` — fact/rule was extracted from this episode
- `supports` — this fact provides evidence for this rule
- `contradicts` — these two facts or a fact and rule are in tension
- `supersedes` — this fact replaced that fact (mirrors `facts.supersedes_id` but queryable both directions)
- `related_to` — general semantic association

---

## Confidence Decay

Every fact and rule has a subjective `decay_rate` (λ) assigned by the Memory Butler during consolidation. Confidence at any point in time is:

```
effective_confidence = confidence × exp(-decay_rate × days_since_last_confirmed)
```

The `last_confirmed_at` timestamp resets whenever an agent retrieves and uses a fact (implicit confirmation via `memory_confirm`), or when a user explicitly re-confirms via the dashboard.

### Permanence Categories

The Memory Butler assigns a permanence label and corresponding decay rate when creating each fact or rule:

| Permanence | λ (decay_rate) | Half-Life | When to Use |
|-----------|----------------|-----------|-------------|
| `permanent` | 0.0 | Never decays | Identity: name, birthday, allergies, family relationships, medical conditions |
| `stable` | 0.002 | ~346 days | Long-term preferences, professional info, habits, long-standing relationships |
| `standard` | 0.008 | ~87 days | Current interests, opinions, ongoing projects, possessions |
| `volatile` | 0.03 | ~23 days | Temporary states, short-term plans, current health status, in-progress work |
| `ephemeral` | 0.1 | ~7 days | What happened today, transient observations, one-off events |

The Memory Butler's consolidation prompt includes guidance on how to classify each extracted fact. This is an LLM judgment call — the model is good at distinguishing "user's name is John" (permanent) from "had ramen yesterday" (ephemeral).

### Decay Thresholds

| Threshold | Effect |
|-----------|--------|
| `effective_confidence >= 0.2` | Normal: included in retrieval results |
| `0.05 <= effective_confidence < 0.2` | Fading: excluded from agent retrieval, visible in dashboard with "fading" badge |
| `effective_confidence < 0.05` | Expired: soft-deleted (`validity = 'expired'`), visible only in dashboard archive |

### Re-Confirmation

When an agent retrieves a fact via `memory_recall` and uses it without contradiction, it should call `memory_confirm(id)`. This resets `last_confirmed_at` to now, restoring confidence to its original level. A `standard` fact about liking broccoli that gets referenced every few weeks never decays below threshold. If the user stops mentioning broccoli for 6 months, it fades. If they mention it again and the butler uses the fact, it snaps back. This mirrors spaced-retrieval dynamics in human memory.

---

## Rule Maturity & Effectiveness

Rules follow a trust progression inspired by the CASS Memory System's playbook pattern:

```
candidate ──(N successful applications)──▶ established ──(sustained effectiveness)──▶ proven
    │                                           │                                       │
    │◀──(harmful marks)──────────────────────── │◀──(harmful marks)──────────────────────│
    │                                           │
    ▼                                           ▼
 demoted/inverted                           demoted
```

### Maturity Levels

| Level | Threshold | Behavior |
|-------|-----------|----------|
| `candidate` | New rules start here | Included in retrieval but with lower weight. Must earn trust. |
| `established` | `success_count >= 5` and `effectiveness_score >= 0.6` | Full weight in retrieval. Reliable. |
| `proven` | `success_count >= 15` and `effectiveness_score >= 0.8` and `age >= 30 days` | Highest weight. Core system knowledge. |

### Effectiveness Scoring

```
effectiveness_score = success_count / (success_count + 4 × harmful_count + 0.01)
```

The 4× multiplier on `harmful_count` is the key insight from CASS Memory: bad advice must be penalized aggressively. A rule that helps 10 times but causes harm twice has an effectiveness of `10 / (10 + 8) = 0.56` — not enough for `established` status.

### Anti-Pattern Learning

Rules marked harmful multiple times are not deleted — they are **inverted** into warnings. A rule marked harmful 3+ times gets its content rewritten as: "ANTI-PATTERN: Do NOT {original rule}. This caused problems because: {harmful feedback}". Anti-patterns are valuable — they prevent the system from re-learning a bad rule.

---

## Search & Retrieval

### Embedding Model

**Model:** `sentence-transformers/all-MiniLM-L6-v2`
- 384 dimensions
- ~80MB model file, loaded once into Memory Butler process
- ~5ms per embedding on CPU
- No network calls, no API costs

Embeddings are generated at write time (when storing a memory) and at query time (when searching). The Memory Butler holds the model in memory as a long-running daemon.

### Three Search Modes

```
memory_search(query, mode="hybrid")
├── mode="semantic"    → pgvector cosine similarity
├── mode="keyword"     → PostgreSQL tsvector/tsquery full-text search
└── mode="hybrid"      → both, fused via Reciprocal Rank Fusion
```

**Reciprocal Rank Fusion** combines semantic and keyword results:

```python
def rrf_score(semantic_rank: int, keyword_rank: int, k: int = 60) -> float:
    return 1.0 / (k + semantic_rank) + 1.0 / (k + keyword_rank)
```

### Composite Scoring

The `memory_recall` tool returns results scored by a composite of four signals:

```
final_score = (
    w_relevance  × relevance      +    # RRF or cosine similarity, normalized 0-1
    w_importance × importance      +    # stored importance rating / 10
    w_recency    × recency         +    # exponential decay from last_referenced_at
    w_confidence × eff_confidence       # effective confidence after decay
)
```

Default weights: `relevance=0.4, importance=0.3, recency=0.2, confidence=0.1`. Configurable per butler via `butler.toml`.

### Scope Filtering

When a butler's CC instance calls `memory_recall(topic, scope="health")`, the query filters facts and rules to `scope IN ('global', 'health')`. Each butler's system prompt instructs it to pass its own name as the scope parameter. Episodes are filtered by `butler` column.

If scope is omitted, all scopes are searched (useful for the Memory Butler's own consolidation and for cross-butler queries via the dashboard).

---

## MCP Tools

The Memory MCP server exposes these tools to all connected CC instances:

```
Memory Tools
│
├── Writing
│   ├── memory_store_episode(content, butler, session_id?, importance?)
│   │     Store a raw episode from a CC session. Typically called automatically
│   │     by the butler daemon after session completion.
│   │
│   ├── memory_store_fact(subject, predicate, content, importance?,
│   │                     permanence?, scope?, tags?)
│   │     Store a fact directly. Used by CC instances that discover something
│   │     worth remembering mid-session, or by the consolidation engine.
│   │
│   └── memory_store_rule(content, scope?, tags?)
│         Store a new rule as a candidate. Used by CC instances that discover
│         a useful pattern, or by the consolidation engine.
│
├── Reading
│   ├── memory_search(query, types?, scope?, mode?, limit?, min_confidence?)
│   │     Search across memory types. Returns scored results.
│   │     types: list of 'episode', 'fact', 'rule' (default: all)
│   │     mode: 'hybrid', 'semantic', 'keyword' (default: 'hybrid')
│   │
│   ├── memory_recall(topic, scope?, limit?)
│   │     High-level recall — composite-scored retrieval of the most relevant
│   │     facts and rules for a topic. The primary tool CC instances should use.
│   │     Automatically bumps reference counts on returned results.
│   │
│   └── memory_get(type, id)
│         Retrieve a specific memory by type and ID. Bumps reference count.
│
├── Feedback
│   ├── memory_confirm(type, id)
│   │     Confirm a fact or rule is still accurate. Resets confidence decay.
│   │     Call after retrieving and successfully using a memory.
│   │
│   ├── memory_mark_helpful(rule_id)
│   │     Report that a rule was applied successfully. Increments success_count
│   │     and recalculates effectiveness.
│   │
│   └── memory_mark_harmful(rule_id, reason?)
│         Report that a rule caused problems. Increments harmful_count (4x weight).
│         Recalculates effectiveness. May trigger demotion or anti-pattern inversion.
│
├── Management
│   ├── memory_forget(type, id)
│   │     Soft-delete a memory. Sets validity to 'forgotten'. Recoverable.
│   │
│   └── memory_stats(scope?)
│         Counts and health indicators per memory type. Episode backlog,
│         fact confidence distribution, rule effectiveness summary.
│
└── Context Building (internal, used by butler daemons)
    └── memory_context(trigger_prompt, butler, token_budget?)
          Build a memory context block for injection into a CC instance's
          system prompt. Returns the highest-scored memories formatted as
          a structured text block within the token budget (default 3000 tokens).
```

### Key Behaviors

- `memory_search`, `memory_recall`, and `memory_get` all bump `last_referenced_at` and `reference_count`. This is the core mechanism that keeps important memories alive.
- `memory_recall` excludes fading memories (effective_confidence < 0.2) by default. Pass `min_confidence=0` to include them.
- `memory_store_fact` checks for existing facts with the same `subject + predicate`. If found, the new fact supersedes the old one (sets `supersedes_id`, marks old fact as `validity='superseded'`). This provides automatic contradiction resolution for simple cases.

---

## Memory Context Injection

When a butler daemon spawns a CC instance, it calls `memory_context(trigger_prompt, butler)` to build a memory block for the system prompt. This is the bridge between stored memory and active agent behavior.

### Injection Strategy

1. **Token budget:** Fixed at 3000 tokens by default (configurable). This is the maximum memory block size injected into any CC instance's context.
2. **Content selection:** The memory context builder embeds the trigger prompt, queries the top-k facts and rules by composite score (scoped to the butler), and formats them into a structured block.
3. **Ordering:** Critical memories (highest-scored) go at the top of the block. LLMs exhibit primacy bias — information at the beginning of context gets more attention.
4. **Format:**

```
## Your Memory

### What You Know (Facts)
- User's name is John [permanent, confirmed 2d ago]
- User is lactose intolerant [stable, confirmed 12d ago]
- User is currently reading Dune [standard, confirmed 5d ago]

### How To Behave (Rules)
- Always confirm before sending outbound messages [proven, global]
- When user says 'feeling off', they usually mean mild nausea [established, health]

### Recent Context (Episodes)
- [2h ago] User asked to reschedule dentist appointment, preferred morning slots
```

5. **Reinjection:** If the butler's CC session runs long enough for context compression, the memory block is included in the compressed context to prevent memory loss mid-session.

---

## Consolidation Engine

The Memory Butler runs consolidation as a scheduled task. This is the process that transforms raw episodes into durable facts and rules.

### Schedule

```toml
[butler.schedule]
consolidate = { cron = "0 */6 * * *", prompt = "Run memory consolidation" }
decay_sweep = { cron = "0 3 * * *", prompt = "Run confidence decay sweep" }
episode_cleanup = { cron = "0 4 * * *", prompt = "Expire old episodes" }
```

### Consolidation Flow

```
1. Fetch all episodes WHERE consolidated = false, ordered by created_at
2. Group by source butler
3. For each group, spawn CC with consolidation prompt:

   "Review these recent episodes from the {butler} butler.

   Extract:
   a) NEW FACTS — things the system learned about the user, their preferences,
      relationships, or world. Use subject-predicate structure.
      For each fact, assess permanence:
      - permanent: identity, medical, biographical (never changes)
      - stable: long-term preferences, professional info (changes rarely)
      - standard: current interests, opinions, projects (shifts over months)
      - volatile: temporary states, short-term plans (changes over weeks)
      - ephemeral: what happened today, one-off events (irrelevant in days)

   b) UPDATED FACTS — if an episode contradicts or updates an existing fact,
      specify which fact to supersede and the new content.

   c) NEW RULES — behavioral patterns worth remembering. E.g., 'user prefers
      X when Y', 'always do Z before W'. Include the scope (global or butler name).

   d) CONFIRMATIONS — existing facts that these episodes support (list fact IDs).

   Do NOT extract:
   - Ephemeral small talk that won't matter in a week
   - Facts that are already stored and unchanged
   - Rules that duplicate existing rules

   Existing facts for reference:
   {inject current active facts, scoped to this butler}

   Existing rules for reference:
   {inject current active rules, scoped to this butler}

   Episodes to process:
   {episode contents}"

4. Parse CC output → store facts, rules, links, confirmations
5. Mark processed episodes as consolidated = true
```

### Decay Sweep Flow (Daily)

```
1. For all active facts and rules, compute effective_confidence
2. effective_confidence < 0.2 → set metadata.status = 'fading'
3. effective_confidence < 0.05 → set validity = 'expired'
4. Rules with harmful_count >= 3 and effectiveness_score < 0.3 →
   invert into anti-pattern
5. Log sweep results to episode stream for dashboard visibility
```

### Episode Cleanup (Daily)

```
1. DELETE episodes WHERE expires_at < now()
2. If episode count > max_episodes (default 10000), delete oldest first
3. Never delete unconsolidated episodes that haven't expired
```

---

## Memory Butler Configuration

```
butlers/memory/
├── MANIFESTO.md
├── CLAUDE.md
├── AGENTS.md
├── butler.toml
└── skills/
    └── consolidate/
        └── SKILL.md
```

### butler.toml

```toml
[butler]
name = "memory"
port = 8150
description = "Shared institutional memory — stores, searches, consolidates, and maintains knowledge across all butlers"

[butler.db]
name = "butler_memory"

[butler.schedule]
consolidate = { cron = "0 */6 * * *", prompt = "Run memory consolidation" }
decay_sweep = { cron = "0 3 * * *", prompt = "Run confidence decay sweep and flag fading memories" }
episode_cleanup = { cron = "0 4 * * *", prompt = "Expire old episodes and enforce capacity limits" }
```

### Memory-Specific Configuration

```toml
[butler.memory]
embedding_model = "all-MiniLM-L6-v2"
embedding_dimensions = 384

[butler.memory.episodes]
default_ttl_days = 7
max_entries = 10000

[butler.memory.facts]
retrieval_confidence_threshold = 0.2
expiry_confidence_threshold = 0.05

[butler.memory.rules]
promote_to_established = { min_successes = 5, min_effectiveness = 0.6 }
promote_to_proven = { min_successes = 15, min_effectiveness = 0.8, min_age_days = 30 }
harmful_to_antipattern = { min_harmful = 3, max_effectiveness = 0.3 }

[butler.memory.retrieval]
default_limit = 20
default_mode = "hybrid"
context_token_budget = 3000
score_weights = { relevance = 0.4, importance = 0.3, recency = 0.2, confidence = 0.1 }
```

---

## Dashboard Integration

The frontend dashboard provides full visibility and control over the memory system. Memory features integrate into the existing dashboard architecture (see `FRONTEND_PROJECT_PLAN.md`).

### Memory Tab on Butler Detail (`/butlers/:name/memory`)

Scoped to memories relevant to the selected butler (`scope IN ('global', butler_name)` for facts/rules, `butler = butler_name` for episodes).

**Facts Panel (primary):**
- Card list of active facts grouped by subject
- Each card shows: subject tag, predicate, content, confidence bar (color-coded: green >0.8, yellow 0.5-0.8, red <0.5), permanence badge, last confirmed date
- Superseded facts shown as strikethrough with link to replacement
- Click → detail drawer: full provenance (source episode, source butler, linked rules, supersession chain)
- Edit button: user corrects a fact → creates new fact that supersedes the old one
- Delete button: soft-deletes the fact
- Filters: subject, source butler, confidence threshold, permanence

**Playbook Panel (sidebar):**
- Rules grouped by maturity: Proven → Established → Candidate
- Each rule: content, scope badge, effectiveness score bar, applied/success/harmful counts
- Anti-patterns shown with warning icon
- Toggle to promote/demote/disable rules manually
- Click → detail drawer: provenance, application history

**Episode Stream (collapsible bottom):**
- Chronological stream of recent episodes
- Each: timestamp, butler badge, content preview, importance score, consolidated badge
- Expandable for full content
- Filters: butler, date range, consolidated/pending

### Cross-Butler Memory View (`/memory`)

New top-level page in the sidebar navigation.

- **Overview cards:** total facts (by permanence), total rules (by maturity), active episodes, fading count
- **Knowledge browser:** unified search across all memory types with type/scope/permanence filters
- **Consolidation activity feed:** recent fact creations, rule maturity changes, supersessions, expirations, anti-pattern inversions
- **Health indicators:**
  - Confidence distribution chart (how many facts are in each confidence band?)
  - Episode backlog (unconsolidated count, time since last consolidation)
  - Rule effectiveness distribution (what % of rules are actually helping?)

### Memory in Other Dashboard Views

- **Session detail drawer:** "Memories from this session" section listing any episodes/facts/rules linked to the session via `source_episode_id` → `session_id`
- **Butler overview tab:** "Recent learnings" widget — last 3 facts learned by this butler
- **Unified timeline:** Memory events (fact created, rule promoted, confidence alert, anti-pattern inverted) as event types
- **Global search (Cmd+K):** Include facts and rules in search results

### Dashboard API Endpoints

```
GET  /api/memory/stats                    → system-wide memory health and counts
GET  /api/memory/facts                    → browse/search facts (?scope=&subject=&q=&min_confidence=)
GET  /api/memory/facts/:id                → fact detail with provenance and links
PUT  /api/memory/facts/:id                → edit fact (creates superseding fact)
DELETE /api/memory/facts/:id              → soft-delete
GET  /api/memory/rules                    → browse/search rules (?scope=&maturity=&q=)
GET  /api/memory/rules/:id                → rule detail with application history
PUT  /api/memory/rules/:id                → edit rule (resets maturity to candidate)
DELETE /api/memory/rules/:id              → soft-delete
GET  /api/memory/episodes                 → browse episodes (?butler=&from=&to=)
GET  /api/memory/episodes/:id             → episode detail
GET  /api/memory/activity                 → consolidation activity feed
GET  /api/butlers/:name/memory/stats      → butler-scoped memory stats
GET  /api/butlers/:name/memory/facts      → butler-scoped facts
GET  /api/butlers/:name/memory/rules      → butler-scoped rules
GET  /api/butlers/:name/memory/episodes   → butler's episodes
```

---

## Integration with Butler Framework

### Session → Episode Pipeline

After every CC session completes, the butler daemon automatically stores an episode:

```
CC session completes →
  butler daemon calls memory_store_episode(
    content = extracted key observations from session transcript,
    butler = butler_name,
    session_id = session.id,
    importance = LLM-rated importance of what happened (1-10)
  ) →
  Memory MCP server generates embedding, stores episode,
  sets expires_at = now() + configured TTL
```

The session transcript extraction can be lightweight — a brief summary of what happened, what the user said, and what was decided. It does not need to be the full transcript. The butler daemon can use the CC response summary or a cheap extraction prompt.

### CC Spawner Integration

When a butler daemon spawns a CC instance, it prepends memory context:

```
1. Butler daemon receives trigger (external MCP call, scheduler, heartbeat)
2. Daemon calls memory_context(trigger_prompt=prompt, butler=butler_name)
3. Memory MCP server returns formatted memory block (within token budget)
4. Daemon injects memory block into CC system prompt, after CLAUDE.md
5. CC instance runs with memory-aware context
6. After session completes → episode storage (see above)
```

### Heartbeat Integration

The Heartbeat Butler triggers the Memory Butler's scheduled tasks like any other butler. The Memory Butler's `consolidate`, `decay_sweep`, and `episode_cleanup` schedules fire on their cron expressions during heartbeat ticks.

### State Store vs Memory

These are distinct systems with different purposes:

| | State Store | Memory |
|---|---|---|
| **Purpose** | Structured operational data | Unstructured knowledge that decays |
| **Schema** | Key-value (JSONB) | Episodes, facts, rules with embeddings |
| **Lifecycle** | Persistent until explicitly deleted | Decays, expires, gets superseded |
| **Ownership** | Per-butler, isolated | Shared across butlers |
| **Access** | Butler's own tools only | Memory MCP tools (all butlers) |
| **Examples** | `last_check_time`, `medication_schedule` | "User prefers morning appointments" |

---

## Scalability

### Scale Profile (Per-User Federation)

Each deployment serves one user. Expected volumes after years of operation:

| Type | Growth Rate | Active Count | Total After 3 Years |
|------|------------|--------------|---------------------|
| Episodes | ~5-50/day, 7-day TTL | 35-350 | N/A (rolling window) |
| Facts | ~1-5/week | 500-2,000 | 500-2,000 (supersession keeps it bounded) |
| Rules | ~1-5/month | 50-200 | 50-200 (maturity system keeps it bounded) |

This is trivially small for PostgreSQL + pgvector. No sharding, partitioning, or complex indexing strategies needed. A single `ivfflat` index with 20 lists is sufficient for vector search at this scale.

### Long-Term Maintenance

- **Episode rotation:** Hard cap at `max_entries` (default 10,000). FIFO eviction after that. Plus TTL-based expiry.
- **Fact deduplication:** The `subject + predicate` check on `memory_store_fact` prevents duplicates. The consolidation prompt is instructed to check existing facts before creating new ones.
- **Rule deduplication:** The consolidation prompt includes existing rules for reference. Duplicate detection is an LLM judgment call during consolidation.
- **Confidence decay sweep:** Daily job prunes fading/expired facts. The DB stays clean without manual intervention.
- **Embedding model migration:** If the model changes, run a backfill migration that re-embeds all content. At <20k rows, this takes seconds.

### Backup

Standard pg_dump of `butler_memory`. Expected size: <100MB even after years of operation.

---

## Alembic Migrations

Following the existing pattern of version chains in `alembic/versions/`:

```
alembic/versions/memory/
├── 001_create_episodes.py
├── 002_create_facts.py
├── 003_create_rules.py
├── 004_create_memory_links.py
└── 005_add_search_vectors.py
```

The Memory Butler runs migrations on startup (same pattern as other butler daemons). Each migration uses `branch_labels = ("memory",)`.

---

## Milestones

### M1: Schema & Memory MCP Server

Stand up the Memory Butler with its database, MCP server, and core tools.

- [ ] Create `butler_memory` database and Alembic migration chain
- [ ] Implement episodes, facts, rules, memory_links tables
- [ ] Implement Memory MCP server with store/search/recall/get tools
- [ ] Integrate `sentence-transformers` for local embedding generation
- [ ] Implement hybrid search (pgvector cosine + tsvector full-text + RRF)
- [ ] Implement composite scoring (relevance, importance, recency, confidence)
- [ ] Implement scope filtering on all retrieval tools
- [ ] Implement `memory_store_fact` with subject-predicate dedup/supersession
- [ ] Write tests for all MCP tools

### M2: Confidence Decay & Rule Maturity

Implement the dynamic lifecycle behaviors.

- [ ] Implement per-fact confidence decay with subjective `decay_rate`
- [ ] Implement `memory_confirm` tool (resets `last_confirmed_at`)
- [ ] Implement `memory_mark_helpful` / `memory_mark_harmful` tools
- [ ] Implement rule maturity progression (candidate → established → proven)
- [ ] Implement effectiveness scoring with 4× harmful weight
- [ ] Implement anti-pattern inversion for repeatedly harmful rules
- [ ] Implement decay sweep scheduled task
- [ ] Write tests for decay math, maturity transitions, anti-pattern inversion

### M3: Consolidation Engine

The Memory Butler's core intelligence — transforming episodes into durable knowledge.

- [ ] Implement consolidation scheduled task
- [ ] Design and test the consolidation prompt (episode → facts/rules extraction)
- [ ] Implement fact creation with permanence classification from LLM output
- [ ] Implement rule creation from detected patterns
- [ ] Implement fact supersession from consolidation output
- [ ] Implement confirmation of existing facts from consolidation output
- [ ] Implement memory_links creation (derived_from, supports, contradicts)
- [ ] Implement episode cleanup scheduled task
- [ ] Write integration tests for the full consolidation pipeline

### M4: Butler Integration

Wire the Memory MCP server into all butlers' CC instances.

- [ ] Update CC spawner to call `memory_context` before spawning
- [ ] Implement `memory_context` tool (token-budgeted context builder)
- [ ] Update CC spawner to call `memory_store_episode` after session completion
- [ ] Wire Memory MCP server into ephemeral MCP configs for all butlers
- [ ] Add `[butler.memory]` config section to butler.toml schema
- [ ] Register Memory Butler with Switchboard
- [ ] Write end-to-end test: trigger butler → session → episode → consolidation → fact retrieval

### M5: Dashboard Integration

Frontend visibility and control over the memory system.

- [ ] Implement dashboard API endpoints for facts, rules, episodes, activity, stats
- [ ] Butler-scoped memory tab: facts panel, playbook panel, episode stream
- [ ] Cross-butler memory page (`/memory`): overview cards, knowledge browser, activity feed, health indicators
- [ ] Fact edit/delete from dashboard (via Memory MCP client)
- [ ] Rule promote/demote/disable from dashboard
- [ ] Memory events in unified timeline
- [ ] Facts and rules in global search (Cmd+K)
- [ ] Memory health indicators on butler overview tab

---

## Design References

This design draws on patterns from:

- **Park et al., "Generative Agents" (2023)** — composite scoring (recency × importance × relevance), reflection as a consolidation mechanism
- **MemoryBank (Zhong et al., 2023)** — Ebbinghaus forgetting curve for biologically-inspired confidence decay
- **A-Mem (Xu et al., NeurIPS 2025)** — Zettelkasten-inspired memory linking, memories that evolve existing memories
- **CASS Memory System** — three-layer cognitive architecture (episodic/working/procedural), confidence decay with half-life, anti-pattern learning, harmful marks with 4× weight, evidence-gated rule validation, ACE pipeline
- **CASS Session Search** — hybrid BM25 + semantic search with Reciprocal Rank Fusion, local-first embedding
- **LangMem (LangChain)** — episodic/semantic/procedural taxonomy, procedural memory as self-modifying instructions
- **Mem0** — selective memory formation over summarization, cost-efficient flat memory
- **MemGPT/Letta** — transparent memory management with explicit tools, OS-inspired resource management
- **Zep/Graphiti** — bi-temporal model for fact validity tracking, supersession as a first-class operation
