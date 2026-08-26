# Source-Grounded Education Traceability Evidence

This table records the scoped requirement-to-test mapping for the
`source-grounded-education` change. The cited tests execute the behavior named by each requirement;
the mapping does not claim repository-wide traceability completeness.

| Requirement | Behavior-executing evidence |
| --- | --- |
| `REQ-butler-education-007` | `roster/education/tests/test_manifesto.py::test_manifesto_preserves_source_grounding_commitment_and_boundaries` reads the governing document and pins the source boundary, citation/reading-pathway promise, transparent pedagogy, and preserved exclusions. |
| `REQ-education-source-grounding-001` | `roster/education/tests/test_source_material.py::{test_register_source_persists_metadata_under_generated_uuid,test_list_source_returns_source_ids_and_preserves_metadata,test_remove_source_deletes_only_registry_key_and_leaves_dangling_refs}` executes registry create/list/remove behavior. |
| `REQ-education-source-grounding-002` | `roster/education/tests/test_pedagogy.py::TestTeachingCiteSource` executes citation persistence and provenance rules; `frontend/src/components/education/NodeDetailPanel.test.tsx` executes the user-visible provenance states. |
| `REQ-education-source-grounding-003` | `roster/education/tests/test_pedagogy.py::TestReadingPathways::{test_registered_refs_become_pathways,test_no_pathways_when_no_source_covers_the_concept}` executes the positive and absent-source pathways. |
| `REQ-module-education-curriculum-001` | `roster/education/tests/test_curriculum.py::{TestCurriculumGenerateConceptTypes,TestCurriculumGenerateSourceRefs}` executes classification, graceful omission, and source mapping. |
| `REQ-module-education-teaching-flows-006` | `roster/education/tests/test_teaching_flows.py::TestTechniqueRecording` executes concept-type technique selection, Socratic fallback, and flow-state recording; `roster/education/tests/test_pedagogy.py` pins the named principles, citations, and reading pathways. |
| `REQ-dashboard-education-api-001` | `roster/education/tests/test_api.py::TestListSourceMaterial` executes populated, empty, nullable-field, and unavailable-pool endpoint states. |
| `REQ-dashboard-education-ui-001` | `frontend/src/components/education/NodeDetailPanel.test.tsx` executes referenced, model-recalled, dangling, unchecked, concept-type, and annotation-free rendering states. |

## Archive-safety and collision record

A capability-qualified scan of every unarchived `## MODIFIED Requirements` block found eight
same-named requirement groups across the repository. Two intersect this change:

- `module-education-curriculum :: Topic decomposition into concept graph` also appears in
  `education-mind-map-lifecycle-integrity`.
- `dashboard-education-ui :: Mind map graph visualization in Curriculum tab` also appears in
  `education-mind-map-lifecycle-integrity`.

`MANIFESTO.md Content` and `Teaching Phase — Explain, Question, Evaluate` have no same-capability,
same-name collision in another unarchived change. The `MANIFESTO.md Content` and `Topic
decomposition into concept graph` blocks in this change are rebuilt from their current baseline
bodies: every baseline normative paragraph and scenario is preserved verbatim, then only this
change's source-grounding and pedagogy clauses and scenarios are added.

The two Education changes remain separately unarchived. This rebuild does not combine the
lifecycle change's intended edits into the source-grounding delta and does not make either archive
order independent: after one change is intentionally archived, every colliding block in the other
change must be rebuilt against the refreshed baseline before that second archive. The dashboard UI
collision is recorded here but remains outside this bead's authorized body-rebuild scope.

## Scoped mechanical check

Run the repository trace checker in authoring mode with the relevant backend and co-located
frontend test roots, retain its complete output as the global baseline record, and filter that
record to the six implementation requirement IDs named by `bu-istke.7`. The scoped result is clean
only when that exact-ID filter contains no `ERROR` or `WARN` line. The repository-wide command is
expected to remain non-zero while unrelated baseline findings exist; its final summary must be
reported separately.

```bash
uv run /home/tze/.dotfiles/ai-bootstrap/skills/personal/th-projects/scripts/spec-trace-check.py \
  "$PWD" --tests-dir tests --tests-dir roster/education/tests --tests-dir frontend/src \
  --authoring
```

## Validation record

Recorded on 2026-08-27 from the `bu-istke.7` worktree:

- The exact six-ID filter named by this task returned no `ERROR` or `WARN` lines in both authoring
  and strict modes.
- The unfiltered authoring run exited 1 with `2410 requirements, 113 IDs, 2846 errors, 58 warnings`.
- The unfiltered strict run exited 1 with `2410 requirements, 113 IDs, 2904 errors, 0 warnings`.
- `python3 scripts/check_cited_requirements_resolve.py` exited 0 and listed all six task IDs plus
  `REQ-dashboard-education-api-001` as provisionally resolved by this active change. The repository
  guard does not scan co-located frontend tests; the scoped command above adds `frontend/src` and
  resolves `REQ-dashboard-education-ui-001` to `NodeDetailPanel.test.tsx`.
- `make check-spec-overwrites` exited 0 with no unfrozen baseline losses.

The generic checker also reports that the dashboard UI `MODIFIED` requirement's metadata is not
contiguous with its first normative paragraph. Moving it there would require restructuring the
existing multi-paragraph `MODIFIED` body and makes `make check-spec-overwrites` report four new
unfrozen baseline losses. This change therefore keeps the ID/Source/Scope lines alongside the
requirement while preserving its body and a green overwrite guard. The generic checker does not
recognize those UI lines as structurally valid metadata, so resolving this requires an explicit
decision to relax the no-rewrite boundary or a checker/format design that satisfies both guards.

Recorded on 2026-08-27 from the coherent `bu-istke.8` branch after incorporating `bu-istke.7`:

- `openspec validate source-grounded-education --strict` exited 0.
- `make check-spec-overwrites` exited 0 with no unfrozen baseline losses; the ratchet reported
  four fewer frozen losses for `MANIFESTO.md Content` and seven fewer for `Topic decomposition into
  concept graph`. The overwrite baseline was not replaced or updated.
- The capability-qualified unarchived collision scan found eight duplicate groups repo-wide and
  exactly the two Education collisions recorded above for this change.
- `python3 scripts/check_cited_requirements_resolve.py` exited 0.
- The focused Education evidence suite passed 39 tests, including the manifesto, curriculum,
  pedagogy, source-registry API, and reading-pathway cases cited above.
- `git diff --check` exited 0.

This evidence is scoped. It does not authorize archiving the change, modifying any other
`MODIFIED` requirement body, or claiming the repository-wide baseline is clean.
