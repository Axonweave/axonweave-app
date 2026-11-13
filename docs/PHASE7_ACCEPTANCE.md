# Phase 7 acceptance: Research Studio

Spec: `docs/axonweave-phase6-7-specs/PHASE7_SPEC.md`. Decisions: D-127 to D-143 in `docs/DECISIONS.md`.
Code: `backend/app/modules/research/`, `backend/app/research/`, `backend/app/repositories/research_*`,
`frontend/src/features/research/`.

This file states what was built, how it was verified, and what was not done. It does not claim more
than the tests show.

## Milestones

| Milestone | Built | Backend tests | Frontend tests |
|---|---|---|---|
| 7.1 Research projects | yes | `test_projects_api.py` | `research-studio.test.tsx` |
| 7.2 Paper library | yes | `test_papers_api.py` | `paper-library.test.tsx` |
| 7.3 Paper analysis (structured extraction, evidence, retries) | yes | `test_paper_analysis.py` | `paper-analysis.test.tsx` |
| 7.4 Comparison | yes | `test_comparisons.py` | `comparison-workspace.test.tsx` |
| 7.5 Evidence matrix | yes | `test_matrices.py` | `matrix-workspace.test.tsx` |
| 7.6 Research gaps | yes | `test_gaps.py` | `gaps-workspace.test.tsx` |
| 7.7 Contradictions | yes | `test_contradictions.py` | `contradictions-workspace.test.tsx` |
| 7.8 Citations | yes | `test_citations.py` | `citations-workspace.test.tsx` |
| 7.9 Writing Studio | yes (Markdown export only) | `test_drafts.py` | `drafts-workspace.test.tsx` |
| 7.10 Knowledge graph integration | yes | `test_concept_links.py` | `concept-links.test.tsx` |
| 7.11 Dashboard and project navigation | yes | `test_dashboard.py` | `research-dashboard.test.tsx`, `research-studio.test.tsx` |
| 7.12 Testing | backend journey, this document | `test_journey.py` | see above |

## Journey (spec section 36)

`backend/tests/research/test_journey.py` runs steps 1 to 19 through the real API on the fake provider:
project, three analysed papers, metadata review, structured analysis, comparison, matrix, gaps with
evidence and review, contradictions, citations, a literature review draft with a citation marker,
claim validation, a new version, restore, knowledge graph links, Markdown export, the dashboard, a
cross-user denial check and project deletion.

## Security and integrity properties (all covered by tests)

- Every research route is owner-scoped; another user gets 404 on every route (each milestone has a
  cross-user test).
- Gaps, contradictions, citations, concept links and the dashboard make no model call. Only the
  Writing Studio assist calls the model, and its output is returned as a suggestion and never saved
  without the user.
- Concept links never create or change knowledge nodes, edges, learner evidence or mastery
  (`test_concept_links.py` compares table counts before and after).
- Draft export refuses unresolved citations (422). Draft saves use optimistic locking (409).
- The dashboard counts only the owner's rows; an empty account shows zeros and no activity.

## Not done, or not verified

- **DOCX and PDF export of drafts.** The API image has no `python-docx` or PDF library. Markdown
  export only (D-142). The spec lists DOCX/PDF as an option; adding them needs a dependency decision.
- **Real provider.** Extraction and the writing assist have only been run on the fake provider. The
  optional live tests are skipped without a key. Output quality on real papers is unmeasured.
- **Browser end to end.** No Playwright run of the research UI. Component tests (Vitest) cover the
  screens with mocked API calls; they do not prove the UI against a running backend.
- **Responsive layout and accessibility** were built with semantic roles (tabs, labelled regions,
  alerts) and tested through roles, but there is no visual or screen reader review.
- **Paper upload through the research UI** reuses the Phase 3 document pipeline; the journey test
  creates papers from seeded documents rather than uploading files.
- **Analysis tab.** Analysis starts from the paper library and the paper page; the project navigation
  has one "Papers and analysis" tab instead of two.
- The dashboard "recent activity" lists papers added, comparisons, matrices and drafts. It does not
  record every change (for example gap or contradiction reviews).
