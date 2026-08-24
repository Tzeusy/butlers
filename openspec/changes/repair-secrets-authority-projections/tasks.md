## 1. Canonical CLI authority projection

- [x] 1.1 Add backend inventory regressions proving canonical CLI state wins
  over same-key stale or failed mirrors in conceptual state and CLI-family KPI
  counts.
- [x] 1.2 Add backend inventory regression proving mirror-only keys remain
  visible and retain most-severe fallback aggregation.
- [x] 1.3 Implement canonical-key precedence in backend inventory aggregation
  without rewriting or deleting raw per-source System rows.
- [x] 1.4 Add matching frontend inventory-adapter regressions for
  canonical-plus-mirror and mirror-only inputs, then implement the same
  canonical-key precedence rule.

## 2. CLI Test query refresh

- [x] 2.1 Add frontend hook regressions proving a completed healthy or failed
  CLI Test invalidates the Secrets inventory and CLI-provider status queries.
- [x] 2.2 Implement both query invalidations after an HTTP success response
  while preserving current transport/API failure behavior.

## 3. Spotify passport presentation

- [x] 3.1 Add frontend regressions for loading, connected, unconfigured,
  authorization-needed, needs-reauth, connector error, and query failure.
- [x] 3.2 Implement the closed connector-status-to-passport mapping, including
  explicit `checking` and `authorization_needed` presentation states, labels,
  and severity ranks.
- [x] 3.3 Verify authorization-needed and failed states enter `needs-hand`,
  checking never enters `stale`, and no generic probe or audit surface is added
  to `u:spotify`.

## 4. Verification and review

- [x] 4.1 Run focused backend inventory tests and frontend inventory, hook, and
  Spotify projection tests.
  - Completed: `uv run pytest tests/api/test_secrets_v2_inventory.py tests/api/test_secrets_v2_probe_live_spotify.py -q` (141 passed) and `npx vitest run src/hooks/use-secrets-inventory.test.ts src/hooks/use-cli-auth.test.ts src/components/secrets/passport/passport.test.tsx --configLoader runner` from `frontend/` (167 passed).
- [ ] 4.2 Run frontend lint, TypeScript build, Knip, and the existing
  content-blind and generic-Spotify-prohibition regression coverage.
  - Blocked: `npm run lint`, `npm run lint:emdash`, `npm run lint:query-coercion`, `npm run knip`, and `npm run build` pass. `npm run test` fails twice only because `src/lib/route-chunk-registry.test.ts` times out at its 20-second limit in the complete concurrent suite (7601 passed, 1 failed); the isolated route-chunk suite passes 5/5 in 9.35s.
- [x] 4.3 Validate this OpenSpec change strictly, run the spec-overwrite ratchet,
  and review the final diff for authority-boundary or browser-visible data
  expansion.
  - Completed: `openspec validate repair-secrets-authority-projections --strict`, `make check-spec-overwrites`, and `git diff --check origin/main...HEAD`; authority-boundary review found no browser-visible credential-data expansion.
