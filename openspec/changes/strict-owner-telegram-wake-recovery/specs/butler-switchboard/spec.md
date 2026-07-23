## ADDED Requirements

### Requirement: Switchboard-Only Trusted Wake-Recovery Coordination
Switchboard SHALL be the sole cross-butler coordinator for strict owner
Telegram wake recovery. It SHALL create a candidate only from the post-commit
accepted-event proof for a canonical-owner direct Telegram-bot native-text DM,
own the owner/window run and fence, and invoke authenticated versioned
prepare/commit/abort/release MCP operations for Health, every registered
origin, and Messenger. Switchboard SHALL NOT accept HA, OwnTracks, location,
user-client, group/channel, callback, media/caption, schedule, briefing, or
broker-catch-up authority for this protocol.

The coordinator SHALL send every receiver the same immutable owner/window,
accepted-event, participant-digest, fence, and action correlation material. It
SHALL NOT obtain origin queue rows through direct SQL, a shared DSN, or an
origin-pool handoff. It SHALL retain an all-or-nothing run on an unavailable,
conflicting, oversized, or target-mismatched response instead of omitting an
origin or dispatching a partial release.

#### Scenario: Only accepted ingress may start coordination
- **WHEN** a raw Telegram connector callback arrives before its normal
  Switchboard ingestion transaction commits
- **THEN** Switchboard does not invoke a wake-recovery participant
- **AND** only the later durable accepted-event record may be considered

#### Scenario: Receiver rejects inconsistent coordinator material
- **WHEN** a prepare, commit, abort, or release request carries a stale fence,
  a mismatched participant digest, or an unsupported schema version
- **THEN** the receiving participant rejects it without mutating its local
  cohort or egress state
- **AND** Switchboard records a retained or blocked run rather than retrying
  with a partial participant set
