# State Store

The state store is a key-value JSONB persistence layer in each butler's PostgreSQL database. It provides arbitrary structured data storage via four MCP tools: `state_get`, `state_set`, `state_delete`, and `state_list`. Every butler instance has its own isolated state store backed by the `state` table in its dedicated database.

## Database Schema

```sql
CREATE TABLE state (
    key TEXT PRIMARY KEY,
    value JSONB NOT NULL DEFAULT '{}',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

## ADDED Requirements

### Requirement: State table provisioning

The `state` table SHALL be created during butler database provisioning as part of the core Alembic migration chain, before any butler-specific or module Alembic migrations run.

#### Scenario: Butler starts with a fresh database

WHEN a butler starts up against a newly provisioned database
THEN the `state` table MUST exist with columns `key` (TEXT PRIMARY KEY), `value` (JSONB NOT NULL DEFAULT '{}'), and `updated_at` (TIMESTAMPTZ NOT NULL DEFAULT now())

---

### Requirement: state_get returns the value for an existing key

The `state_get` MCP tool SHALL accept a `key` parameter and return the corresponding JSONB value from the `state` table.

#### Scenario: Key exists in the state table

WHEN `state_get(key)` is called with a key that exists in the `state` table
THEN it MUST return the JSONB `value` associated with that key

#### Scenario: Key does not exist in the state table

WHEN `state_get(key)` is called with a key that does not exist in the `state` table
THEN it MUST return null
AND it MUST NOT raise an error

---

### Requirement: state_set upserts a key-value pair

The `state_set` MCP tool SHALL accept `key` and `value` parameters and persist them to the `state` table using upsert semantics (INSERT ... ON CONFLICT UPDATE).

#### Scenario: Setting a new key

WHEN `state_set(key, value)` is called with a key that does not yet exist
THEN a new row MUST be inserted into the `state` table with the given key and JSONB value
AND `updated_at` MUST be set to the current timestamp

#### Scenario: Updating an existing key

WHEN `state_set(key, value)` is called with a key that already exists
THEN the existing row's `value` MUST be replaced with the new JSONB value
AND `updated_at` MUST be updated to the current timestamp

#### Scenario: Value is arbitrary JSONB

WHEN `state_set(key, value)` is called with any valid JSONB value (object, array, string, number, boolean, null)
THEN the value MUST be stored without schema validation or transformation

---

### Requirement: state_delete removes a key

The `state_delete` MCP tool SHALL accept a `key` parameter and remove the corresponding row from the `state` table.

#### Scenario: Deleting an existing key

WHEN `state_delete(key)` is called with a key that exists in the `state` table
THEN the row MUST be removed from the `state` table

#### Scenario: Deleting a nonexistent key

WHEN `state_delete(key)` is called with a key that does not exist in the `state` table
THEN the operation MUST be a no-op
AND it MUST NOT raise an error

---

### Requirement: state_list returns keys with optional prefix filtering

The `state_list` MCP tool SHALL accept an optional `prefix` parameter and return a list of keys from the `state` table.

#### Scenario: Listing all keys with no prefix

WHEN `state_list()` is called without a prefix argument
THEN it MUST return all keys present in the `state` table

#### Scenario: Listing keys filtered by prefix

WHEN `state_list(prefix)` is called with a prefix string
THEN it MUST return only keys that start with the given prefix

#### Scenario: No keys match the prefix

WHEN `state_list(prefix)` is called with a prefix that matches no keys
THEN it MUST return an empty list
AND it MUST NOT raise an error

#### Scenario: Listing keys when the state table is empty

WHEN `state_list()` is called on an empty `state` table
THEN it MUST return an empty list

---

### Requirement: All state operations are atomic

Every state store operation SHALL execute as a single atomic SQL statement.

#### Scenario: state_set executes atomically

WHEN `state_set(key, value)` is called
THEN the upsert MUST be performed as a single SQL statement (INSERT ... ON CONFLICT ... DO UPDATE)
AND no partial writes SHALL be observable by concurrent readers

#### Scenario: state_delete executes atomically

WHEN `state_delete(key)` is called
THEN the deletion MUST be performed as a single SQL statement

#### Scenario: state_get executes atomically

WHEN `state_get(key)` is called
THEN the read MUST be performed as a single SQL statement

#### Scenario: state_list executes atomically

WHEN `state_list(prefix?)` is called
THEN the key listing MUST be performed as a single SQL statement

---

### Requirement: state_set updates the updated_at timestamp

The `updated_at` column SHALL always reflect the time of the most recent write to a given key.

#### Scenario: Timestamp set on insert

WHEN `state_set(key, value)` inserts a new row
THEN `updated_at` MUST be set to the current timestamp at the time of the insert

#### Scenario: Timestamp updated on upsert

WHEN `state_set(key, value)` updates an existing row
THEN `updated_at` MUST be updated to the current timestamp at the time of the update
AND the previous `updated_at` value MUST be overwritten

---

### Requirement: Values have no schema enforcement

The state store SHALL NOT impose any schema constraints on JSONB values beyond PostgreSQL's native JSONB validity.

#### Scenario: Storing a nested JSON object

WHEN `state_set("config", {"notifications": {"email": true, "sms": false}})` is called
THEN the nested object MUST be stored and retrievable exactly as provided

#### Scenario: Storing a JSON array

WHEN `state_set("tags", ["urgent", "personal"])` is called
THEN the array MUST be stored and retrievable exactly as provided

#### Scenario: Storing a scalar JSON value

WHEN `state_set("counter", 42)` is called
THEN the scalar value MUST be stored and retrievable exactly as provided

#### Scenario: Overwriting with a different JSON type

WHEN `state_set("data", {"a": 1})` is called followed by `state_set("data", [1, 2, 3])`
THEN the final stored value MUST be `[1, 2, 3]`
AND no type-mismatch error SHALL be raised
