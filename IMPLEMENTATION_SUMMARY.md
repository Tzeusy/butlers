# Extraction Audit Log Implementation Summary

## Overview
Implemented a comprehensive extraction audit log system for the Switchboard butler to provide transparency and user control over autonomous data extractions.

## Files Changed

### 1. New Migration: `alembic/versions/switchboard/002_extraction_audit_log.py`
- Created `extraction_log` table with the following schema:
  - `id` (UUID, primary key)
  - `source_message_preview` (TEXT) - Truncated to 200 chars
  - `extraction_type` (VARCHAR(100)) - e.g., "contact", "note", "birthday"
  - `tool_name` (VARCHAR(100)) - The tool called on Relationship butler
  - `tool_args` (JSONB) - Full arguments passed to the tool
  - `target_contact_id` (UUID) - Contact affected by the extraction
  - `confidence` (VARCHAR(20)) - Extraction confidence level
  - `dispatched_at` (TIMESTAMPTZ) - When the extraction was logged
  - `source_channel` (VARCHAR(50)) - e.g., "email", "telegram"
- Added indexes on:
  - `target_contact_id` for filtering by contact
  - `extraction_type` for filtering by type
  - `dispatched_at DESC` for time-based queries

### 2. Enhanced: `src/butlers/tools/switchboard.py`
Added three new functions:

#### `log_extraction()`
- Logs every extraction-originated write to the audit log
- Auto-truncates message previews to 200 characters
- Returns the UUID of the created log entry
- Used by the extraction pipeline to record all autonomous operations

#### `extraction_log_list()`
- Lists extraction log entries with flexible filtering
- Supports filtering by:
  - `contact_id` - View extractions for a specific contact
  - `extraction_type` - Filter by type (contact, note, birthday, etc.)
  - `since` - ISO 8601 timestamp for time-range queries
  - `limit` - Max entries to return (default 100, max 500)
- Returns entries ordered by `dispatched_at DESC` (newest first)
- Handles UUID and datetime conversions for asyncpg compatibility

#### `extraction_log_undo()`
- Best-effort reversal of extraction operations
- Maps original tools to corresponding undo operations:
  - `contact_add` → `contact_delete`
  - `note_add` → `note_delete`
  - `birthday_set` → `birthday_remove`
  - `address_add` → `address_delete`
  - `email_add` → `email_delete`
  - `phone_add` → `phone_delete`
- Routes undo calls to the Relationship butler via the `route()` function
- Returns error messages for:
  - Invalid UUID format
  - Non-existent log entries
  - Operations without undo support (e.g., `contact_update`)
  - Missing ID fields in tool arguments

### 3. Enhanced: `tests/test_tools_switchboard.py`
Added 19 comprehensive tests covering:

**Logging Tests (3 tests):**
- Entry creation with full context
- Message preview truncation
- Minimal required fields

**Listing Tests (8 tests):**
- Empty results
- Unfiltered listing
- Filtering by contact ID
- Filtering by extraction type
- Filtering by time range
- Limit enforcement and max limit cap
- Ordering by timestamp (DESC)

**Undo Tests (8 tests):**
- Invalid UUID handling
- Non-existent entry handling
- Operations without undo support
- Successful undo for various tool types (contact_add, note_add, birthday_set)
- Missing ID field error handling
- Routing error propagation

## Design Decisions

### Database Type Choices
- **JSONB for tool_args**: Preserves full tool call context for debugging and potential replay
- **UUID for IDs**: Strong typing, prevents string/UUID confusion
- **VARCHAR limits**: Reasonable bounds for extraction_type (100) and confidence (20)
- **TEXT for preview**: Flexible storage for message snippets

### Type Handling
- Conversion of string UUIDs to UUID objects for asyncpg parameter binding
- Conversion of ISO 8601 strings to datetime objects for TIMESTAMPTZ queries
- Back-conversion to strings in query results for JSON serialization

### Undo Strategy
- Best-effort approach: Returns errors rather than failing silently
- ID extraction logic prioritizes common patterns (id, contact_id, note_id)
- No undo for update operations (irreversible without snapshots)
- Routes through Relationship butler to maintain encapsulation

### Testing Approach
- Isolated test fixture (`pool_with_extraction`) to avoid affecting other tests
- Mock `route_fn` for undo tests to prevent external dependencies
- Time manipulation via direct SQL updates for predictable test behavior

## Integration Points

The extraction pipeline (implemented in task butlers-r1v.2) will call `log_extraction()` after each successful tool dispatch to the Relationship butler. Example usage:

```python
# After dispatching contact_add to Relationship butler
await log_extraction(
    pool=switchboard_pool,
    extraction_type="contact",
    tool_name="contact_add",
    tool_args={"id": contact_id, "name": "Alice", "email": "alice@example.com"},
    target_contact_id=contact_id,
    confidence="high",
    source_message_preview=original_email[:200],
    source_channel="email",
)
```

Users can then review and undo extractions:

```python
# List all extractions for a contact
entries = await extraction_log_list(pool, contact_id="abc-123")

# Undo a specific extraction
result = await extraction_log_undo(pool, log_id="def-456")
```

## Acceptance Criteria Coverage

1. ✅ extraction_log table created via migration
2. ✅ Every auto-dispatched extraction logged with full context
3. ✅ Tools: extraction_log_list, extraction_log_undo
4. ✅ List supports filtering by contact, type, time range
5. ✅ Undo reverses the original tool call on Relationship butler
6. ✅ Tests cover logging, listing, filtering, and undo

## Verification

All 35 tests pass (16 existing + 19 new extraction tests):
```bash
pytest tests/test_tools_switchboard.py -v
# 35 passed in 16.82s
```

Code passes linting and formatting:
```bash
ruff check src/butlers/tools/switchboard.py tests/test_tools_switchboard.py
# All checks passed!
```
