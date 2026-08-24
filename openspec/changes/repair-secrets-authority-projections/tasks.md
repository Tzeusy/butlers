## 1. Canonical CLI authority projection

- [ ] 1.1 Add backend inventory regressions proving canonical CLI state wins
  over same-key stale or failed mirrors in conceptual state and CLI-family KPI
  counts.
- [ ] 1.2 Add backend inventory regression proving mirror-only keys remain
  visible and retain most-severe fallback aggregation.
- [ ] 1.3 Implement canonical-key precedence in backend inventory aggregation
  without rewriting or deleting raw per-source System rows.
- [ ] 1.4 Add matching frontend inventory-adapter regressions for
  canonical-plus-mirror and mirror-only inputs, then implement the same
  canonical-key precedence rule.

## 2. CLI Test query refresh

- [ ] 2.1 Add frontend hook regressions proving a completed healthy or failed
  CLI Test invalidates the Secrets inventory and CLI-provider status queries.
- [ ] 2.2 Implement both query invalidations after an HTTP success response
  while preserving current transport/API failure behavior.

## 3. Spotify passport presentation

- [ ] 3.1 Add frontend regressions for loading, connected, unconfigured,
  authorization-needed, needs-reauth, connector error, and query failure.
- [ ] 3.2 Implement the closed connector-status-to-passport mapping, including
  explicit `checking` and `authorization_needed` presentation states, labels,
  and severity ranks.
- [ ] 3.3 Verify authorization-needed and failed states enter `needs-hand`,
  checking never enters `stale`, and no generic probe or audit surface is added
  to `u:spotify`.

## 4. Verification and review

- [ ] 4.1 Run focused backend inventory tests and frontend inventory, hook, and
  Spotify projection tests.
- [ ] 4.2 Run frontend lint, TypeScript build, Knip, and the existing
  content-blind and generic-Spotify-prohibition regression coverage.
- [ ] 4.3 Validate this OpenSpec change strictly, run the spec-overwrite ratchet,
  and review the final diff for authority-boundary or browser-visible data
  expansion.
