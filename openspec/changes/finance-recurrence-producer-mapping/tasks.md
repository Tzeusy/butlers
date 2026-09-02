## 1. Trusted Finance provenance

- [ ] 1.1 Reserve server-only provenance on trusted Gmail and owner transaction/subscription entry
  paths; preserve exact Gmail `source_endpoint_identity` and reject or ignore caller attempts to
  assert either producer or endpoint authority.
- [ ] 1.2 Preserve trusted provenance through bulk, deduplication, split, correction, and
  subscription upsert paths without upgrading legacy/defaulted values.
- [ ] 1.3 Derive each recurring group's complete contributing producer/endpoint set and resolve
  exactly one supported pair or `unknown`; two Gmail endpoints are mixed ownership.
- [ ] 1.4 Keep the registered `track_subscription_fact` property-fact writer outside current
  dedicated-table recurrence readers; if later adopted, apply the same reserved attestation or
  classify it unmeasurable.

## 2. RFC 0029 adoption

- [ ] 2.1 Persist `finance:recurrence:{recurring-group-id}` and
  `finance:subscription-renewal:{subscription-id}` through the shared expected-signals helper,
  carrying required `producer_endpoint_identity` for connector sources.
- [ ] 2.2 Extend connector measurability and persistence to require the exact
  `(connector_type, endpoint_identity)` pair; add the schema/API field without weakening
  producer-role RLS.
- [ ] 2.3 Keep SimpleFIN and all unsupported/mixed/unprovable sources unmeasurable until an
  independently approved producer-liveness contract exists.
- [ ] 2.4 Keep declared renewal dates distinct from expected transaction observations and preserve
  the current forward-looking reminder path.

## 3. Consumers and presentation

- [ ] 3.1 Expose Finance recurrence measurability without direct cross-schema reads or inferred
  payment-state fields.
- [ ] 3.2 Ensure APIs, subscription audit, the Finance tab, and proactive output never turn
  unmeasurable or absent-without-policy into missed-renewal, payment, cancellation, paused, or
  stopped wording.

## 4. Verification

- [ ] 4.1 Add migrated-PostgreSQL tests that kill the exact Gmail endpoint after
  `next_expected_date` while a sibling endpoint stays healthy, in both row orders, and prove
  `unmeasurable` with no candidate or owner-behavior wording.
- [ ] 4.2 Test stale, dead/offline, degraded, paused, missing, unreadable, mixed, SimpleFIN,
  manual/import, source-message-only, backfill, split, and legacy provenance.
- [ ] 4.3 Prove healthy/current Gmail and attested owner sources produce the RFC 0029 state while
  no unapproved missed-recurrence candidate is emitted.
- [ ] 4.4 Prove existing forward-looking annual renewal and predicted-bill policies retain their
  current windows, categories, priorities, deduplication, cooldown, expiry, and wording.
- [ ] 4.5 Keep an executable tool-registration guard for `track_subscription_fact` and its
  outside-current-inputs classification so a new reader cannot silently create authority.
