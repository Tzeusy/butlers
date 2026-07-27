## ADDED Requirements

### Requirement: Pending Actions Store Replayable Executable Commands

An inline approval producer MUST persist the exact registered native tool name and a
`tool_args` object accepted by that tool's handler. Executable arguments MUST NOT
contain routing-only fields, and the same materialized command values MUST be used for
immediate execution when approval is not required.

#### Scenario: Routed delivery is parked

- **WHEN** an outbound routed delivery requires approval
- **THEN** the pending action stores the registered native delivery tool name
- **AND** `tool_args` contains every required handler argument and no routing-only argument

#### Scenario: Immediate and deferred execution are equivalent

- **WHEN** equivalent routed deliveries take the immediate and approval-replay paths
- **THEN** both invoke the same native handler with the same normalized argument values

#### Scenario: Stored command is malformed

- **WHEN** an approved historical action cannot be accepted by its registered handler
- **THEN** dispatch MUST fail without rewriting or guessing its executable arguments
- **AND** the action MUST remain `approved` with `execution_result = null`
- **AND** an immutable `action_execution_failed` event MUST be recorded
