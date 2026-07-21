## MODIFIED Requirements

### Requirement: Inbound message identity resolution

The Switchboard SHALL call `resolve_contact_by_channel(type, value)` on every inbound message before routing. The resolution MUST use the message's source channel type (e.g., `'telegram'`, `'email'`) and source identifier (e.g., Telegram chat ID, email address) to look up the sender in `relationship.entity_facts` via channel-handle predicates (a `has-handle` triple whose value is prefixed `telegram:<id>`, a `has-email` triple, etc.). NOTE: resolution moved off `public.contact_info` to `relationship.entity_facts` per RFC 0004 Amendment 3 (bead bu-akads, epic bu-oluyt); `public.contacts` / `public.contact_info` are vestigial and `public.entity_info` holds only `secured=true` credentials.

#### Scenario: Owner sends a Telegram message

- **WHEN** a Telegram message arrives from chat ID `99999`
- **AND** `resolve_contact_by_channel('telegram', '99999')` returns a contact with `roles = ['owner']`
- **THEN** the Switchboard MUST identify the sender as the owner

#### Scenario: Known non-owner sends a Telegram message

- **WHEN** a Telegram message arrives from chat ID `12345`
- **AND** `resolve_contact_by_channel('telegram', '12345')` returns a contact "Chloe" with `roles = []` and `entity_id = 'abc-123'`
- **THEN** the Switchboard MUST identify the sender as "Chloe" with entity_id `abc-123`

#### Scenario: Unknown sender sends a Telegram message

- **WHEN** a Telegram message arrives from chat ID `55555`
- **AND** `resolve_contact_by_channel('telegram', '55555')` returns `None`
- **THEN** the Switchboard MUST invoke the unknown-sender transitory-entity
  flow defined by `entity-identity`
- **AND** the flow MUST NOT create or require a `public.contacts` or
  `public.contact_info` row
- **AND** owner-notification behavior for a successfully surfaced transitory
  entity MUST follow `entity-identity`'s owner-notification requirement

#### Scenario: Email message identity resolution

- **WHEN** an email arrives from `chloe@example.com`
- **AND** `resolve_contact_by_channel('email', 'chloe@example.com')` returns a contact
- **THEN** the Switchboard MUST identify the sender using the resolved contact
