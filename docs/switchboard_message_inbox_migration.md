# Switchboard message_inbox Partition Migration (`sw_006`)

## Scope
`sw_006` rewrites `message_inbox` from the legacy flat table (`sw_005`) into a month-partitioned lifecycle store.

New lifecycle payload columns:
- `request_context`
- `raw_payload`
- `normalized_text`
- `decomposition_output`
- `dispatch_outcomes`
- `response_summary`
- `lifecycle_state`
- `schema_version`
- `processing_metadata`
- `final_state_at`

## Upgrade Behavior
1. Rename `message_inbox` to a temporary backup table.
2. Create partitioned `message_inbox` (`PARTITION BY RANGE (received_at)`).
3. Install partition maintenance functions:
- `switchboard_message_inbox_ensure_partition(reference_ts)`
- `switchboard_message_inbox_drop_expired_partitions(retention default '1 month', reference_ts)`
4. Backfill all `sw_005` rows into the canonical `sw_006` shape.
5. Apply one-month retention cleanup.

## Default Retention Policy
- Default hot retention is one month (`INTERVAL '1 month'`).
- Write paths should call partition maintenance before inserts.

## Rollback (Downgrade to `sw_005`)
Run:

```bash
uv run python -c "import asyncio; from butlers.migrations import run_migrations; asyncio.run(run_migrations('<DB_URL>', chain='switchboard'))"
# Then downgrade with Alembic target switchboard@sw_005 if needed.
```

Downgrade reconstructs the legacy `sw_005` schema from `sw_006` records by:
1. Renaming partitioned `message_inbox` to backup.
2. Recreating legacy columns/indexes.
3. Backfilling legacy-compatible fields from canonical payloads.
4. Dropping partition maintenance functions.

The downgrade path is covered by migration integration tests.
