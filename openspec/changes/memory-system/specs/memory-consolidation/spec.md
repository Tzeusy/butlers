## ADDED Requirements

### Requirement: Consolidation scheduled task

The Memory Butler SHALL run consolidation every 6 hours via a scheduled task (`cron = "0 */6 * * *"`). The task SHALL fetch all episodes where `consolidated = false`, group them by source butler, and process each group.

#### Scenario: Consolidation processes unconsolidated episodes
- **WHEN** the consolidation task fires
- **AND** 10 unconsolidated episodes exist (5 from 'health', 5 from 'general')
- **THEN** the system SHALL process 2 groups (health and general)
- **AND** all 10 episodes SHALL be marked `consolidated = true` after processing

#### Scenario: No unconsolidated episodes
- **WHEN** the consolidation task fires
- **AND** no unconsolidated episodes exist
- **THEN** no CC instances SHALL be spawned

### Requirement: Consolidation spawns CC with extraction prompt

For each butler group, consolidation SHALL spawn a CC instance with a prompt that includes: the unconsolidated episodes, existing active facts (scoped to the butler), and existing active rules (scoped to the butler). The prompt SHALL instruct extraction of new facts (with permanence classification), updated facts (supersession), new rules, and confirmations of existing facts.

#### Scenario: CC extracts new fact from episodes
- **WHEN** consolidation processes episodes containing "User mentioned they are lactose intolerant"
- **AND** no existing fact covers this information
- **THEN** the CC output SHALL include a new fact with `subject='user'`, `predicate='dietary_restriction'`, `content='Lactose intolerant'`, and `permanence='stable'`

#### Scenario: CC identifies fact to supersede
- **WHEN** consolidation processes episodes containing "User now prefers tea over coffee"
- **AND** an existing fact states "User's preferred drink is coffee"
- **THEN** the CC output SHALL include an updated fact that supersedes the existing one

#### Scenario: CC confirms existing facts
- **WHEN** consolidation processes episodes where the user references their known name
- **AND** a fact already stores the user's name
- **THEN** the CC output SHALL include a confirmation of the existing fact's ID

### Requirement: Consolidation creates provenance links

When consolidation creates a new fact or rule from episodes, the system SHALL create `derived_from` memory links connecting the new fact/rule to the source episode(s). When a fact supports a rule, a `supports` link SHALL be created.

#### Scenario: Fact linked to source episode
- **WHEN** consolidation extracts a fact from episode E1
- **THEN** a memory link SHALL exist with `source_type='fact'`, `target_type='episode'`, `target_id=E1.id`, `relation='derived_from'`

### Requirement: Decay sweep scheduled task

The Memory Butler SHALL run a daily decay sweep (`cron = "0 3 * * *"`) that computes `effective_confidence = confidence × exp(-decay_rate × days_since_last_confirmed)` for all active facts and rules.

#### Scenario: Fact transitions to fading
- **WHEN** the decay sweep runs
- **AND** a fact's effective_confidence is 0.15 (below 0.2, above 0.05)
- **THEN** the fact's metadata SHALL include `status='fading'`

#### Scenario: Fact transitions to expired
- **WHEN** the decay sweep runs
- **AND** a fact's effective_confidence is 0.03 (below 0.05)
- **THEN** the fact's `validity` SHALL be set to 'expired'

#### Scenario: Permanent fact never decays
- **WHEN** the decay sweep runs
- **AND** a fact has `permanence='permanent'` (decay_rate=0.0)
- **THEN** the fact's effective_confidence SHALL remain unchanged regardless of time elapsed

### Requirement: Episode cleanup scheduled task

The Memory Butler SHALL run daily episode cleanup (`cron = "0 4 * * *"`) that deletes episodes where `expires_at < now()`. If episode count exceeds `max_entries` (default 10,000), the oldest episodes SHALL be deleted first. Unconsolidated episodes that have not expired SHALL never be deleted by cleanup.

#### Scenario: Expired episodes deleted
- **WHEN** episode cleanup runs
- **AND** 5 episodes have `expires_at` in the past
- **THEN** those 5 episodes SHALL be deleted

#### Scenario: Unconsolidated episodes preserved
- **WHEN** episode cleanup runs
- **AND** an episode has `consolidated=false` and `expires_at` in the future
- **THEN** the episode SHALL NOT be deleted even if the max_entries cap is reached

#### Scenario: Capacity enforcement
- **WHEN** episode cleanup runs
- **AND** 10,500 episodes exist (500 over max_entries)
- **THEN** the 500 oldest consolidated expired episodes SHALL be deleted
