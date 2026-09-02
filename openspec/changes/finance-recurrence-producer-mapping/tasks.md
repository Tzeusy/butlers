## 1. Trusted Finance provenance

- [ ] 1.1 Reserve server-only provenance on trusted Gmail and owner transaction/subscription entry
  paths; reject or ignore caller attempts to assert that authority.
- [ ] 1.2 Preserve trusted provenance through bulk, deduplication, split, correction, and
  subscription upsert paths without upgrading legacy/defaulted values.
- [ ] 1.3 Derive each recurring group's complete contributing producer set and resolve exactly one
  supported producer or `unknown`.

## 2. RFC 0029 adoption

- [ ] 2.1 Persist `finance:recurrence:{recurring-group-id}` and
  `finance:subscription-renewal:{subscription-id}` through the shared expected-signals helper.
- [ ] 2.2 Keep SimpleFIN and all unsupported/mixed/unprovable sources unmeasurable until an
  independently approved producer-liveness contract exists.
- [ ] 2.3 Keep declared renewal dates distinct from expected transaction observations and preserve
  the current forward-looking reminder path.

## 3. Consumers and presentation

- [ ] 3.1 Expose Finance recurrence measurability without direct cross-schema reads or inferred
  payment-state fields.
- [ ] 3.2 Ensure APIs, subscription audit, the Finance tab, and proactive output never turn
  unmeasurable or absent-without-policy into missed-renewal, payment, cancellation, paused, or
  stopped wording.

## 4. Verification

- [ ] 4.1 Add migrated-PostgreSQL tests that kill Gmail liveness after `next_expected_date` and
  prove `unmeasurable` with no candidate or owner-behavior wording.
- [ ] 4.2 Test stale, dead/offline, degraded, paused, missing, unreadable, mixed, SimpleFIN,
  manual/import, source-message-only, backfill, split, and legacy provenance.
- [ ] 4.3 Prove healthy/current Gmail and attested owner sources produce the RFC 0029 state while
  no unapproved missed-recurrence candidate is emitted.
- [ ] 4.4 Prove existing forward-looking annual renewal and predicted-bill policies retain their
  current windows, categories, priorities, deduplication, cooldown, expiry, and wording.
