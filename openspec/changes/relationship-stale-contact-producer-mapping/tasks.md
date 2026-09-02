## 1. Trusted producer evidence

- [ ] 1.1 Reserve a server-only `metadata.expected_signal_source` attestation and prevent public
  API/MCP metadata from setting or overriding it.
- [ ] 1.2 Stamp Gmail email, Telegram user-client, WhatsApp user-client, and server-authenticated
  owner-manual observations with the exact producer values in the design matrix.
- [ ] 1.3 Resolve each contact to exactly one corroborated producer; classify missing,
  unsupported, legacy, mixed, conflicting, or unreadable evidence as unmeasurable without
  backfilling old rows.

## 2. RFC 0029 Relationship adoption in PR #3965

- [ ] 2.1 After this prerequisite merges, rebase PR #3965 onto the resulting `main` and extend RFC
  0029's Relationship adoption section by reference to this mapping.
- [ ] 2.2 Persist `relationship:stale-contact:{contact-id}` through the shared expected-signals
  helper before any stale-contact output is authorized.
- [ ] 2.3 Gate `insight-scan`, `contacts_overdue`, scheduled relationship maintenance, and
  on-demand reconnect planning so only `absent` may produce owner-facing output.

## 3. Dashboard honesty

- [ ] 3.1 Expose aggregate stale-contact measurability to the Relationship Contacts tab and Plex
  attention rail without adding a cross-schema read.
- [ ] 3.2 Render instrumentation/provenance unavailability and suppress false "Cadence all clear"
  copy whenever the requested aggregate is incomplete.

## 4. Verification and rollout

- [ ] 4.1 Convert the planning matrix contract into migrated-PostgreSQL tests that kill Gmail,
  Telegram user-client, and WhatsApp user-client liveness after cadence elapsed and prove
  unmeasurable with no candidate, overdue result, or nudge.
- [ ] 4.2 Test owner-attestation removal, every unsupported source, mixed ownership, missing and
  unreadable evidence, and tied latest observations from different producers.
- [ ] 4.3 Prove a healthy current producer with elapsed cadence still follows the existing moderate
  and severe stale-contact priority boundaries and tier exclusions.
- [ ] 4.4 Add API/frontend tests proving both Relationship overdue surfaces distinguish incomplete
  measurability from a complete empty/all-clear result.
