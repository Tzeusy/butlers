# Tasks

## 1. Spec landing

- [x] 1.1 Create `openspec/changes/chronicles-editorial-rewrite/{proposal,design,tasks}.md`.
- [x] 1.2 Add modified-capability spec under `openspec/changes/chronicles-editorial-rewrite/specs/dashboard-chronicles/spec.md` covering: editorial archetype landing, briefing endpoint, attention endpoint, KPI endpoint, new episode types and aggregations mapping, drilldown panel preservation.
- [ ] 1.3 Validate via `openspec validate chronicles-editorial-rewrite`.

## 2. Adapters

- [x] 2.1 Extend `src/butlers/chronicler/adapters/google_health.py` with workout / steps / heart-rate projection.
- [x] 2.2 Add `src/butlers/chronicler/adapters/focus.py` with `FocusInferredAdapter`.
- [x] 2.3 Add `src/butlers/chronicler/adapters/reading.py` with `ReadingInferredAdapter`.
- [x] 2.4 Update `src/butlers/chronicler/aggregations.py` with three new mappings (`workout_episode → other`, `focus_block → tasks`, `reading_block → tasks`).
- [x] 2.5 Register the four new adapters in `src/butlers/chronicler/adapters/__init__.py` and `src/butlers/chronicler/jobs.py`.
- [x] 2.6 Tests under `tests/chronicler/`.

## 3. API

- [x] 3.1 Add Pydantic models for `ChroniclesBriefing`, `ChroniclesAttentionItem`, `ChroniclesRecentDay`, `ChroniclesKpi` in `roster/chronicler/api/models.py`.
- [x] 3.2 Add three endpoints to `roster/chronicler/api/router.py`: `/briefing`, `/attention`, `/kpi`. Briefing reads `chronicler.tier2_cache` for the `voice_paragraph`; falls back to a templated paragraph when missing or stale. No new LLM call paths.
- [x] 3.3 Tests under `tests/chronicler/test_briefing_endpoint.py`, `test_attention_endpoint.py`, `test_kpi_endpoint.py`.

## 4. Frontend

- [x] 4.1 Add `'editorial'` to the `<Page archetype>` discriminant; route it to a Display-headline heading block.
- [x] 4.2 Add hooks `use-chronicles-briefing.ts`, `use-chronicles-attention.ts`, `use-chronicles-kpi.ts` under `frontend/src/hooks/`.
- [x] 4.3 Add `RecentDaysIndex.tsx` and `ChroniclesDrilldownPanel.tsx` under `frontend/src/components/chronicles/`.
- [x] 4.4 Rewrite `frontend/src/pages/ChroniclesPage.tsx` as the editorial-archetype consumer. Compose `DateEyebrow`, `BriefingStatus`, `Headline`, `Elaboration`, `KpiStrip`, `AttentionList`, `RecentDaysIndex`, `ChroniclesDrilldownPanel`.
- [x] 4.5 Tests under `frontend/src/pages/ChroniclesPage.test.tsx` and components as needed.

## 5. Verification

- [ ] 5.1 `uv run ruff check src/ tests/ roster/ conftest.py --output-format concise`.
- [ ] 5.2 `uv run ruff format --check src/ tests/ roster/ conftest.py -q`.
- [ ] 5.3 `uv run pytest tests/chronicler --ignore=tests/e2e -q --maxfail=3 --tb=short`.
- [ ] 5.4 `cd frontend && npx tsc --noEmit && npx vitest run`.

## 6. Out of scope

- Lane taxonomy restructure.
- Episode-merging / fragmentation policy changes.
- Per-event LLM invocation paths.
- New database schema.
- Manifesto rewrite.
