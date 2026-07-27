## ADDED Requirements

### Requirement: Routed Delivery Uses a Canonical Native Command

Messenger `route.execute` MUST materialize a canonical native delivery command before
standing-rule evaluation, inline approval parking, or immediate delivery. Email,
Telegram, and WhatsApp commands MUST name a registered Messenger tool and carry the
exact arguments accepted by that tool's handler.

#### Scenario: Routed email send

- **WHEN** Messenger processes an email `send`
- **THEN** its native command is `email_send_message` with `to`, `subject`, and `body`

#### Scenario: Routed email reply with authoritative thread identity

- **WHEN** Messenger processes an email `reply` whose request context contains `source_thread_identity`
- **THEN** its native command is `email_reply_to_thread` with `to`, `thread_id`, `body`, and optional `subject`

#### Scenario: Routed email reply lacks authoritative thread identity

- **WHEN** Messenger processes an email `reply` without `request_context.source_thread_identity`
- **THEN** it MUST fail before parking or delivery
- **AND** it MUST NOT substitute `request_id` or another internal identifier as `thread_id`

#### Scenario: Routed Telegram delivery

- **WHEN** Messenger processes a Telegram `send` or `reply`
- **THEN** its native command is respectively `telegram_send_message` or `telegram_reply_to_message`
- **AND** its arguments exactly match the registered handler signature

#### Scenario: Routed WhatsApp delivery

- **WHEN** Messenger processes a WhatsApp `send` or the currently supported routed-reply behavior
- **THEN** its native command is `whatsapp_send_message` with `recipient` and `text`
