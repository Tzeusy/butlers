# Switchboard Butler

The Switchboard is the public-facing ingress butler for the Butlers framework. It listens on Telegram (bot) and Email (IMAP/webhook), classifies incoming messages using an ephemeral Claude Code instance, and routes them to the correct specialist butler via MCP. It owns the butler registry and serves as the single entry point for all external communication.

**Modules:** `telegram`, `email`

## Database Schema

The Switchboard butler's dedicated database (`butler_switchboard`) contains the standard core tables (`state`, `scheduled_tasks`, `sessions`) plus two Switchboard-specific tables:

```sql
CREATE TABLE butler_registry (
    name TEXT PRIMARY KEY,
    endpoint_url TEXT NOT NULL,
    description TEXT,
    modules JSONB NOT NULL DEFAULT '[]',
    last_seen_at TIMESTAMPTZ,
    registered_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE routing_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_channel TEXT NOT NULL,       -- 'telegram', 'email', 'mcp'
    source_id TEXT,                     -- chat_id, email address, etc.
    routed_to TEXT NOT NULL,            -- butler name
    prompt_summary TEXT,
    trace_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

## MCP Tools

The Switchboard exposes all core MCP tools (state, scheduler, sessions, trigger, tick, status) plus three Switchboard-specific tools:

- `route(butler_name, tool_name, args)` -- forward a tool call to a target butler via MCP client, propagating trace context
- `list_butlers()` -- return the full butler registry with names, descriptions, modules, and endpoints
- `discover()` -- re-scan butler config directories, update the registry (add new butlers, update changed ones, mark missing ones as stale)

## ADDED Requirements

### Requirement: Switchboard-specific table provisioning

The `butler_registry` and `routing_log` tables SHALL be created during Switchboard database provisioning as Switchboard-specific migrations, applied after core migrations.

#### Scenario: Switchboard starts with a fresh database

WHEN the Switchboard butler starts up against a newly provisioned database
THEN the `butler_registry` table MUST exist with columns `name` (TEXT PRIMARY KEY), `endpoint_url` (TEXT NOT NULL), `description` (TEXT), `modules` (JSONB NOT NULL DEFAULT '[]'), `last_seen_at` (TIMESTAMPTZ), and `registered_at` (TIMESTAMPTZ NOT NULL DEFAULT now())
AND the `routing_log` table MUST exist with columns `id` (UUID PRIMARY KEY), `source_channel` (TEXT NOT NULL), `source_id` (TEXT), `routed_to` (TEXT NOT NULL), `prompt_summary` (TEXT), `trace_id` (TEXT), and `created_at` (TIMESTAMPTZ NOT NULL DEFAULT now())

#### Scenario: Core tables are also present

WHEN the Switchboard butler starts up against a newly provisioned database
THEN the core tables (`state`, `scheduled_tasks`, `sessions`) MUST also be present
AND core migrations MUST have been applied before Switchboard-specific migrations

---

### Requirement: discover populates the butler registry on startup

The Switchboard SHALL call `discover()` on startup to populate the butler registry by scanning butler config directories.

#### Scenario: Startup discovery with multiple butler config directories

WHEN the Switchboard starts up and butler config directories exist for `general`, `relationship`, and `health`
THEN `discover()` MUST be invoked automatically
AND the `butler_registry` table MUST contain one row for each discovered butler with the correct `name`, `endpoint_url`, `description`, and `modules` parsed from each butler's `butler.toml`

#### Scenario: Startup discovery sets registered_at

WHEN `discover()` inserts a new butler into the registry
THEN `registered_at` MUST be set to the current timestamp

---

### Requirement: discover updates existing and detects new butlers at runtime

The `discover()` MCP tool SHALL re-scan butler config directories when called, updating existing entries and adding new ones.

#### Scenario: A new butler config directory appears at runtime

WHEN `discover()` is called and a new butler config directory exists that is not yet in the `butler_registry`
THEN a new row MUST be inserted into `butler_registry` with the butler's `name`, `endpoint_url`, `description`, and `modules` from its `butler.toml`

#### Scenario: An existing butler's config has changed

WHEN `discover()` is called and an existing butler's `butler.toml` has a different `description` or `modules` list than what is stored in the registry
THEN the corresponding row in `butler_registry` MUST be updated to reflect the current config values

#### Scenario: A previously registered butler's config directory no longer exists

WHEN `discover()` is called and a butler in the `butler_registry` no longer has a corresponding config directory
THEN the butler MUST NOT be deleted from the registry
AND the butler's `last_seen_at` SHALL NOT be updated (it retains its previous value, marking it as stale)

---

### Requirement: list_butlers returns the full registry

The `list_butlers()` MCP tool SHALL return the contents of the `butler_registry` table.

#### Scenario: Registry contains multiple butlers

WHEN `list_butlers()` is called and the `butler_registry` contains entries for `general`, `relationship`, and `health`
THEN it MUST return a list containing all three entries
AND each entry MUST include `name`, `endpoint_url`, `description`, `modules`, `last_seen_at`, and `registered_at`

#### Scenario: Registry is empty

WHEN `list_butlers()` is called and the `butler_registry` table is empty
THEN it MUST return an empty list
AND it MUST NOT raise an error

---

### Requirement: route forwards a tool call to a target butler via MCP

The `route(butler_name, tool_name, args)` MCP tool SHALL look up the target butler in the registry, establish an MCP client connection to its endpoint, call the specified tool with the given arguments, and return the result.

#### Scenario: Routing a trigger to an existing butler

WHEN `route("health", "trigger", {"prompt": "Log my weight: 75kg"})` is called
AND `health` exists in the `butler_registry` with a valid `endpoint_url`
THEN the Switchboard MUST establish an MCP client connection to the `health` butler's endpoint
AND it MUST call the `trigger` tool on the `health` butler with the provided args
AND it MUST return the result from the `health` butler

#### Scenario: Routing to a butler not in the registry

WHEN `route("nonexistent", "trigger", {"prompt": "hello"})` is called
AND `nonexistent` does not exist in the `butler_registry`
THEN the tool MUST return an error indicating the butler was not found
AND it MUST NOT attempt an MCP connection

#### Scenario: Target butler is unreachable

WHEN `route("health", "trigger", {"prompt": "hello"})` is called
AND the `health` butler's endpoint is unreachable (connection refused, timeout)
THEN the tool MUST return an error indicating the butler is unreachable
AND the error MUST include the butler name and endpoint URL for diagnostics

---

### Requirement: route propagates W3C trace context

The `route()` tool SHALL propagate the current W3C traceparent context to the target butler by including `_trace_context` in the tool call arguments.

#### Scenario: Trace context is propagated on route

WHEN `route(butler_name, tool_name, args)` is called within an active OpenTelemetry span
THEN the tool call to the target butler MUST include a `_trace_context` field in the args containing the current W3C traceparent string
AND the target butler MUST be able to extract the trace context and create a child span under the same trace

#### Scenario: Route call creates a span

WHEN `route(butler_name, tool_name, args)` is called
THEN a span named `switchboard.route` MUST be created
AND the span MUST have attributes `target` (the butler name) and `tool_name` (the tool being called)

---

### Requirement: route updates last_seen_at on successful response

The Switchboard SHALL update the `last_seen_at` timestamp in the `butler_registry` when a butler responds successfully to a `route()` call.

#### Scenario: Successful route updates last_seen_at

WHEN `route("health", "trigger", {"prompt": "hello"})` is called
AND the `health` butler returns a successful response
THEN the `last_seen_at` column for the `health` row in `butler_registry` MUST be updated to the current timestamp

#### Scenario: Failed route does not update last_seen_at

WHEN `route("health", "trigger", {"prompt": "hello"})` is called
AND the `health` butler is unreachable or returns an error
THEN the `last_seen_at` column for the `health` row in `butler_registry` MUST NOT be updated

---

### Requirement: route logs every routing decision

Every `route()` call SHALL be recorded in the `routing_log` table.

#### Scenario: Successful route is logged

WHEN `route("health", "trigger", {"prompt": "Log my weight"})` is called successfully from a Telegram message
THEN a new row MUST be inserted into `routing_log` with `source_channel` set to the originating channel (e.g., `'telegram'`), `source_id` set to the identifier of the sender (e.g., chat ID), `routed_to` set to `'health'`, `prompt_summary` containing a summary of the routed prompt, and `trace_id` set to the current OpenTelemetry trace ID

#### Scenario: Failed route is still logged

WHEN `route("health", "trigger", {"prompt": "hello"})` is called and the target butler is unreachable
THEN a row MUST still be inserted into `routing_log` recording the attempted routing decision

---

### Requirement: Message classification via CC spawner

When a message arrives via the Telegram or Email module, the Switchboard SHALL spawn an ephemeral Claude Code instance to classify the message and determine which butler should handle it.

#### Scenario: Telegram message triggers classification

WHEN a Telegram message is received by the Switchboard's Telegram module
THEN the Switchboard MUST spawn a CC instance via the CC spawner
AND the CC instance MUST receive a classification prompt containing the list of available butlers (from `list_butlers()`) and the message text
AND the classification prompt MUST follow the format: "Classify this message and route it. Available butlers: [{butler list with descriptions}]. Message: {text}"

#### Scenario: Email message triggers classification

WHEN an email is received by the Switchboard's Email module
THEN the Switchboard MUST spawn a CC instance via the CC spawner
AND the CC instance MUST receive a classification prompt containing the list of available butlers and the email content (subject and body)

#### Scenario: CC decides the target butler and routes

WHEN the CC instance determines that a message should be handled by the `health` butler
THEN CC MUST call `route("health", "trigger", {"prompt": <constructed prompt>})` via the Switchboard's MCP tools
AND the Switchboard MUST forward the call to the `health` butler

---

### Requirement: Default routing to General butler when uncertain

When the CC instance is uncertain which specialist butler should handle a message, it SHALL default to routing to the General butler.

#### Scenario: Ambiguous message is routed to General

WHEN a message arrives that does not clearly match any specialist butler's domain
AND the CC instance cannot determine the correct target with confidence
THEN the CC instance MUST route the message to the `general` butler via `route("general", "trigger", {"prompt": ...})`

#### Scenario: Classification prompt instructs default behavior

WHEN the Switchboard constructs the classification prompt for CC
THEN the prompt MUST include an instruction that if the message does not clearly fit a specialist butler, it SHALL be routed to the `general` butler

---

### Requirement: Response delivery via originating channel

After a routed butler returns a result, the Switchboard SHALL send the response back to the user via the same channel (Telegram or Email) that the original message arrived on.

#### Scenario: Telegram message gets Telegram response

WHEN a message arrives via Telegram, is routed to a specialist butler, and the butler returns a result
THEN the Switchboard MUST send the result back to the originating Telegram chat using the Telegram module's `send_message` tool

#### Scenario: Email message gets email response

WHEN a message arrives via Email, is routed to a specialist butler, and the butler returns a result
THEN the Switchboard MUST send the result back to the originating email address using the Email module's `send_email` tool

---

### Requirement: Inter-butler communication uses MCP-over-SSE

All communication between the Switchboard and target butlers SHALL use MCP over SSE (Server-Sent Events) transport.

#### Scenario: Route call uses SSE transport

WHEN `route(butler_name, tool_name, args)` establishes a connection to a target butler
THEN it MUST use the SSE transport protocol as specified by the butler's `endpoint_url` in the registry
AND the connection MUST be established as an MCP client to the target butler's MCP server

#### Scenario: SSE endpoint URL format

WHEN a butler is registered in the `butler_registry`
THEN its `endpoint_url` MUST be an HTTP(S) URL pointing to the butler's SSE endpoint (e.g., `http://localhost:8103/sse`)

---

### Requirement: Switchboard loads Telegram and Email modules

The Switchboard butler SHALL load the `telegram` and `email` modules as specified in its `butler.toml` configuration.

#### Scenario: Modules are loaded on startup

WHEN the Switchboard butler starts up with `[modules.telegram]` and `[modules.email]` sections in its `butler.toml`
THEN both the Telegram and Email modules MUST be loaded and initialized
AND both modules MUST have their tools registered on the Switchboard's MCP server

#### Scenario: Telegram module provides message intake

WHEN the Telegram module is loaded on the Switchboard
THEN it MUST listen for incoming Telegram messages (via polling or webhook as configured)
AND it MUST invoke the Switchboard's classification flow when a message arrives

#### Scenario: Email module provides message intake

WHEN the Email module is loaded on the Switchboard
THEN it MUST listen for incoming emails (via IMAP polling or webhook as configured)
AND it MUST invoke the Switchboard's classification flow when an email arrives

---

### Requirement: Routing log records source channel and source identifier

Every entry in the `routing_log` SHALL record which channel the message arrived on and the identity of the sender.

#### Scenario: Telegram message source is recorded

WHEN a Telegram message from chat ID `12345` is routed to the `health` butler
THEN the `routing_log` entry MUST have `source_channel` set to `'telegram'` and `source_id` set to `'12345'`

#### Scenario: Email message source is recorded

WHEN an email from `user@example.com` is routed to the `relationship` butler
THEN the `routing_log` entry MUST have `source_channel` set to `'email'` and `source_id` set to `'user@example.com'`

#### Scenario: Direct MCP call source is recorded

WHEN a routing request arrives via a direct MCP call (not via Telegram or Email)
THEN the `routing_log` entry MUST have `source_channel` set to `'mcp'`
AND `source_id` MAY be null

---

### Requirement: Switchboard does not route to itself

The Switchboard SHALL NOT appear in the list of routable butlers presented to the CC classification instance and SHALL NOT accept self-routing.

#### Scenario: Switchboard is excluded from classification prompt

WHEN the Switchboard constructs the classification prompt listing available butlers
THEN the Switchboard itself MUST NOT be included in the list of available butlers

#### Scenario: Route to Switchboard is rejected

WHEN `route("switchboard", tool_name, args)` is called
THEN the tool MUST return an error indicating that routing to the Switchboard is not permitted

---

### Requirement: Concurrent message handling

The Switchboard SHALL handle incoming messages serially in v1 (one CC classification instance at a time), consistent with the framework's serial CC dispatch constraint.

#### Scenario: Two messages arrive in quick succession

WHEN two Telegram messages arrive in quick succession
THEN the Switchboard MUST process the first message's classification and routing to completion before starting the second
AND no messages SHALL be dropped; they MUST be queued for processing

---

### Requirement: Routing log includes trace_id for distributed tracing

Each `routing_log` entry SHALL include the OpenTelemetry trace ID for correlation with traces in Jaeger.

#### Scenario: Trace ID is recorded in routing log

WHEN a message is classified and routed within an active OpenTelemetry trace
THEN the `routing_log` entry's `trace_id` column MUST contain the trace ID of the span encompassing the routing operation

#### Scenario: Trace ID links to end-to-end trace

WHEN a `routing_log` entry has a `trace_id` value
THEN that trace ID MUST correspond to a trace in the telemetry backend (e.g., Jaeger) that includes spans for message receipt, classification, routing, and target butler execution
