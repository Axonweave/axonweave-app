# Phase 6 acceptance: Learner Intelligence and Knowledge Graph

Branch `feat/p6-knowledge-extraction`. Spec: `docs/axonweave-phase6-7-specs/PHASE6_SPEC.md`.
Decisions: D-122 to D-133. Repository assessment: `docs/PHASE6_7_REPOSITORY_ASSESSMENT.md`.

## Final acceptance status: NOT PASSED (gate open)

All ten milestones are implemented and were checked by scripted live runs and static checks. The
completion gate (spec section 21) requires the automated backend, frontend and integration suites
and the Phase 1 to 5 regression run. By instruction ("dont do test now") those suites were not
written or run. Phase 7 must not start until this is done and this status is changed.

## Completed milestones

| Milestone | Commit | Scope |
| --- | --- | --- |
| 6.1 / 6.2 | `653aeab` | Concept and relationship extraction, graph schema, provenance |
| 6.3 | `2f6608b` | Graph services and APIs, bounded traversal, merge, duplicate review |
| 6.4 | `3597556` | Knowledge graph UI |
| 6.5 | `2296fad` | Learner evidence from quiz answers and flashcard reviews |
| 6.6 | `db0bb7d` | Explainable mastery engine (`rb-1`) |
| 6.7 | `ebdd547` | Safeguarded misconception detection |
| 6.8 | `9db8116` | Personalised recommendations |
| 6.9 | `fcd7aa2` | Learner Intelligence dashboard |
| 6.10 | this document | Acceptance record (tests deferred) |

## Implemented features

- Knowledge extraction from processed documents with validation and evidence quotes (capped).
- PostgreSQL graph (nodes, aliases, edges, evidence), merge, duplicate review, archive.
- Graph UI with filters, detail panel, list and duplicates views.
- Evidence ingestion, idempotent, one row per event and concept; concept links
  (confirmed, proposed, rejected).
- Mastery `rb-1` with states NOT_ASSESSED, INSUFFICIENT_EVIDENCE, LEARNING, DEVELOPING,
  PROFICIENT, STRONG; each state carries a stored explanation; bulk recalculation in the worker.
- Misconception detection on demand, evidence-cited, with review actions.
- Recommendations: deterministic rules and scores, stored with their evidence, complete and dismiss
  with cooldown.
- Dashboard at `/insights`: overview, subjects, gaps, concepts, concept view.

## Database changes (one Alembic head: 0016)

- 0011 knowledge graph tables. 0012 extraction candidates and usage.
- 0013 `knowledge_concept_links`, `learner_evidence`.
- 0014 `learner_concept_states`.
- 0015 `learner_misconceptions`, `learner_misconception_evidence`; widens the usage-kind check.
- 0016 adds `source`, `knowledge_node_id`, `suggested_action`, `score`, `evidence` to
  `revision_recommendations` and widens its type check. Phase 5 rows are unchanged.

## APIs

- `/knowledge/*`: graph, nodes, relationships, evidence, candidates, extraction jobs.
- `/knowledge/learner/*`: `sync`, `summary`, `evidence`, `links` (+ confirm, reject), `states`,
  `states/{node_id}`, `recalculate`, `dashboard`.
- `/knowledge/learner/misconceptions/*`: `detect`, list, get, evidence, confirm, dismiss, PATCH.
- `/recommendations/learner` (GET), `/{id}/complete`, `/{id}/dismiss`. Phase 5
  `/recommendations/revision` is unchanged.

## Frontend pages

- `/knowledge` (graph, list, duplicates; `?node=<id>` deep link).
- `/insights` Learner Intelligence (sidebar item). `/progress` is unchanged and linked.

## Test results

| Check | Result |
| --- | --- |
| Ruff, ruff format, mypy (292 files) | Pass |
| `tsc --noEmit`, eslint | Pass |
| Prettier | 29 files already failing before this phase; new files clean |
| `alembic heads` | One head (0016) |
| Scripted live runs (not in the repo): graph, evidence, mastery, misconceptions with a scripted provider, ranking (16 checks), recommendation API, dashboard API | Pass |
| Backend pytest suites for Phase 6 | Not written |
| Phase 1 to 5 regression (pytest) | Not run |
| Vitest and Playwright for Phase 6 pages | Not written |
| End to end flow (spec section 20) | Not run as one flow |
| Detection with a real provider | Not run (no provider key configured) |
| UI opened in a browser, mobile layout | Not checked |

## Security checks

Checked by scripted live runs: owner scoping and 404 on another user's ids for nodes, evidence,
links, states, misconceptions, recommendations (including a Phase 5 id on a learner route and the
reverse) and the dashboard. Learner responses omit question and answer text except the owner's own
misconception evidence view. Model output is validated and never trusted for ids (opaque tags).
Not yet covered by automated tests; these remain gate items.

## Known limitations

- Semantic-similarity duplicate candidates are not built (name and alias matches only).
- Descriptive-answer feedback text is not fed into mastery.
- Goals, exam deadlines, subject importance and question-type reattempts do not exist in the
  codebase, so recommendations do not use them.
- No UI to review proposed concept links; no restore button for archived concepts; no
  relationship editing in the graph UI.
- Evidence sync is triggered through the API, not automatically after every quiz or review.
- Subject view has no per-subject recommendations; Progress shows no learner figures inline.
- `alembic check` reports drift on older tables and an extra id index on the new tables.
- Mastery weights and thresholds are reasoned starting values, not fitted to data (D-130).

## Deferred

- Phase 7 (Research Studio), until the gate passes.
- The test suites listed above.

## To close the gate

1. Write backend tests for spec section 18, frontend tests for section 19, and the section 20 flow.
2. Run the full backend suite (one pytest at a time) and the Phase 1 to 5 regression.
3. Run Playwright, including a mobile viewport.
4. Run detection once against a real provider.
5. Update the status above.
