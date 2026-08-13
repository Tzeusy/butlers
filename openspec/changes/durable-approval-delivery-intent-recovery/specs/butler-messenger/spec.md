## ADDED Requirements

### Requirement: Wired approval egress handoff reconciliation
Messenger SHALL durably own the actual-provider handoff/reconciliation record for a recovery-keyed approval notification, keyed by the immutable `notify.v1` delivery idempotency key, without restoring an unwired generic delivery-tracking module or endpoint.

ID: REQ-butler-messenger-001
Source: RFC-0023
Scope: v1-mandatory

#### Scenario: First approval handoff records the real boundary
- **WHEN** Messenger accepts a valid recovery-keyed `approval_request` for a new action key
- **THEN** it persists the key and a pre-provider handoff record before invoking its owned channel adapter
- **AND** any provider receipt/reference retained is bounded, opaque, non-secret, and unavailable to unrelated tracking surfaces

#### Scenario: Same-key recovery reconciles instead of resending
- **WHEN** Messenger receives the same action key after a source restart or lost response
- **THEN** it returns the stored confirmed result, a proof-bearing safe-retry result, or an ambiguous result for that key
- **AND** it does not invoke the provider again unless its adapter contract proves the same-key retry cannot duplicate delivery

### Requirement: Honest provider uncertainty
Messenger SHALL classify a provider result as ambiguous whenever a provider-start marker exists and neither a receipt nor a provider-supported idempotency/reconciliation result proves completion or safe absence.

ID: REQ-butler-messenger-002
Source: RFC-0023
Scope: v1-mandatory

#### Scenario: Crash after provider start is not a duplicate send
- **WHEN** Messenger restarts after recording provider start for an approval key but before persisting a final provider outcome
- **THEN** recovery returns an ambiguous classification unless the channel adapter reconciles that same key
- **AND** no default retry path sends another Telegram, email, or WhatsApp approval request

#### Scenario: Provider idempotency proves a retry safe
- **WHEN** an adapter supports a stable idempotency key or receipt lookup and proves that a repeated key has no additional provider effect
- **THEN** Messenger may return `safe_retry` or `confirmed` with the same key
- **AND** it records the normalized proof class without exposing the raw provider response
