# Phase 4 acceptance (spec section 23)

Walked line by line on the branch `autopilot/p4-5` after M8. Status values: **Met** (proven by a test or command listed here), **Partly** (the code path is proven on the FakeProvider and generated fixtures, but the claim also needs the live provider, real documents or a person looking at the screen), **Not met**.
Rule applied: a statement about what a model produces, or how something looks, is at best Partly, because no live provider call, real lecture file or manual visual check was run by automation.

## Verification record
| Gate | Command | Result |
|---|---|---|
| Backend tests | `docker compose exec backend pytest` | {{PYTEST}} |
| Backend lint | `docker compose exec backend ruff check . && ruff format --check .` | {{RUFF}} |
| Backend types | `docker compose exec backend mypy app` | {{MYPY}} |
| Migrations | `alembic heads`; `upgrade head`; `downgrade -1`; `upgrade head` | {{ALEMBIC}} |
| Frontend lint, types | `cd frontend && npm run lint && npx tsc --noEmit` | clean |
| Frontend unit | `cd frontend && npm run test` | 22 files, 250 tests passed |
| Frontend build | `docker compose up -d --build frontend` (runs `next build`) | built |
| End to end | `PW_EXTERNAL_STACK=1 npx playwright test e2e/study.spec.ts` | 14 passed, 16 skipped (desktop tests skip on the mobile project and the reverse; the fake-provider-only case skips because this stack runs `LLM_PROVIDER=gemini`) |
| Dependency audit | `pip-audit`; `npm audit --omit=dev` | pip: none. npm: KaTeX advisory fixed by upgrading to 0.19.1; 6 pre-existing findings remain in the `shadcn` CLI tree |
| Live provider, real documents, visual review | not run | see HUMAN-NEEDED in `autopilot/P4-8.md` |

## Summary generation
| Criterion | Status | Evidence |
|---|---|---|
| Quick summary works | Partly | `test_summary.py::test_each_type`, `test_quick_summary_is_capped` (FakeProvider); no live output judged |
| Detailed summary works | Partly | `test_each_type`, map-reduce tests |
| Section-wise summary works | Partly | `test_each_type` |
| Exam-oriented summary works | Partly | `test_each_type`, `test_exam_oriented_does_not_promise_exam_questions` |
| Beginner-friendly summary works | Partly | `test_each_type` |
| Source references are preserved | Met | `test_invalid_references_are_stripped`, `test_references_can_be_switched_off`, `test_coverage_is_reported`; stored as ids and pages, shown as links in the viewer (Vitest `SourceRefs`) |
| Summaries can be edited and saved | Met | `test_edit_creates_a_new_version_and_keeps_the_original`, `test_stale_edit_is_a_conflict`; Playwright "a summary can be edited, versioned and restored" |

## Flashcards
| Criterion | Status | Evidence |
|---|---|---|
| Can be generated | Partly | `test_flashcards.py::test_deck_structure_and_references` (Fake) |
| Different card types | Partly | `test_every_card_type_is_accepted` (validators accept all six; no live variety check) |
| Can be edited | Met | `test_edit_add_delete_favourite`, `test_reorder`; Playwright edits a card |
| Can be deleted | Met | `test_edit_add_delete_favourite`; UI confirmation dialog (Vitest, Playwright delete of a material) |
| Sets can be saved | Met | deck tables persist; `test_deck_structure_and_references`, library list shows decks |
| Source references preserved | Met | `test_deck_structure_and_references`, `test_unsupported_cards_are_dropped` |

## Quizzes
| Criterion | Status | Evidence |
|---|---|---|
| MCQs can be generated | Partly | `test_quiz.py::test_every_type_is_generated_and_keys_are_stored` (Fake) |
| True/false can be generated | Partly | same |
| Multiple-select can be generated | Partly | same |
| Short-answer can be generated | Partly | same (short answer is self-assessed, D-96) |
| Quiz-taking works | Met | Playwright full quiz, refresh-resume, timed auto-submit; Vitest `QuizTaker` |
| Objective scoring works | Met | `test_full_attempt_scores_objective_questions`, `test_wrong_answers_and_exact_match_for_multiple_select`; Playwright shows 100 percent |
| Results are saved | Met | `test_results_are_persisted_per_question`; attempt history in the UI (Playwright) |
| Correct answers remain protected | Met | key-leakage sweep tests; Playwright inspects every response before submit |

## Other study tools
| Criterion | Status | Evidence |
|---|---|---|
| Study guides can be generated | Partly | `test_guides_banks.py::test_guide_hierarchy_objectives_and_sources` (Fake) |
| Glossaries can be generated | Partly | `test_terms_merged_sorted_and_referenced` (Fake); search is Met (`test_search_filter_sort_endpoint`, Playwright) |
| Formula sheets can be generated | Partly | `test_valid_expressions`, `test_variables_flags_and_never_verified` (Fake); safe rendering is Met (Vitest, Playwright) but correctness of live formulas is a human check |
| Question banks can be generated | Partly | `test_organised_by_topic_and_difficulty_without_keys` (Fake) |

## Study library
| Criterion | Status | Evidence |
|---|---|---|
| Resources can be saved | Met | generation saves a material with version 1 (`test_echo_runs_end_to_end`, per-generator tests) |
| Resources can be edited | Met | summary, guide, glossary, formula sheet through `PATCH`; decks through card routes; banks and quizzes are not editable (by design, D-93, D-94, D-99) |
| Resources can be searched | Met | `test_list_filters_search_sort_and_pagination`; Playwright search |
| Resources can be filtered | Met | type, workspace, subject, chapter, status, archived in the API; type and archived in the UI (subject, chapter and workspace filters are API only) |
| Resources can be archived | Met | `test_archive_unarchive_and_default_hides_archived` |
| Resources can be deleted | Met | `test_delete_cascades_versions_and_cards`; Playwright delete |
| Versions are managed | Met | `test_edit_restore_keeps_original_and_numbers`; Playwright versions and restore |

## Export
| Criterion | Status | Evidence |
|---|---|---|
| PDF export works | Partly | `test_each_resource_type_and_format`; the PDF assertions skip in the API image (PyMuPDF is worker-only) and were checked by hand in M5. A person must open real files. |
| CSV export works where applicable | Met | `test_flashcards_csv_neutralises_formulas_and_pdf_works`, `test_glossary_csv_cells_are_all_safe`; Playwright exports a deck through the real worker and downloads it |
| Download access is protected | Met | `test_foreign_export_status_and_download_are_404`, `test_download_headers_and_pending_not_ready`, `test_expired_download_is_refused_and_sweeper_removes_file`; Playwright checks `attachment` and `nosniff` |

## Quality and security
| Criterion | Status | Evidence |
|---|---|---|
| Generated content is source-grounded | Partly | references are validated and unsupported items dropped (tests above); whether live output is actually supported by its source needs the human evaluation in `STUDY_GENERATION_TESTING.md` |
| Citation references are validated | Met | `test_invalid_references_are_stripped`, `test_unsupported_cards_are_dropped` |
| Output schemas are validated | Met | `test_invalid_output_is_corrected_once`, `test_invalid_twice_fails_safely`, per-generator rule tests |
| User ownership is enforced | Met | `test_route_sweep.py` (login on every route), per-feature "another user gets 404 everywhere" tests, Playwright isolation test |
| Generation limits are enforced | Met | `test_daily_quota`, `test_per_minute_limit_and_token_quota`, `test_active_job_cap`, size limits |
| Tests pass | Met | see the verification record |
| Documentation is complete | Met | the nine documents of spec 26 exist: `STUDY_GENERATION_ARCHITECTURE.md`, `SUMMARY_GENERATION.md`, `FLASHCARD_GENERATION.md`, `QUIZ_GENERATION.md`, `STUDY_GUIDES.md`, `STUDY_LIBRARY.md`, `EXPORT_SYSTEM.md`, `GENERATION_SECURITY.md`, `STUDY_GENERATION_TESTING.md`; README and `WORKFLOW.md` updated |

## Section 22.7 security tests
All ten are mapped to tests in `GENERATION_SECURITY.md` section 2.

## Counts
Met: 25. Partly: 17. Not met: 0 (42 criteria).

## What would turn Partly into Met
1. Generate each type from real lecture material with the live provider and score it (`STUDY_GENERATION_TESTING.md` section 4).
2. Open real PDF, DOCX and CSV exports in their viewers.
3. A visual, keyboard and screen-reader pass on the study pages at desktop and phone width.

## Differences from the spec that a reviewer should know
- Whole-material favourites (spec 12.3) are not built; cards can be favourited.
- "Show explanations immediately" (spec 7.3) is not offered: it would need feedback before submission (D-95).
- Short-answer and descriptive questions are self-assessed, not model graded (D-96); optional LLM grading is deferred.
- Quiz and question-bank duplicate is refused (D-100); exports never include answer keys (D-100).
- The Generate dialog's usage hint shows the user's request count for 30 days, not a remaining allowance, because no remaining-quota endpoint exists; a limit hit is reported by name.
- Subject, chapter and workspace library filters exist in the API but not in the library UI; subject and chapter pages instead open the Generate dialog with the source fixed.
- No automated accessibility audit tool (axe) is installed; roles, labels and keyboard use are asserted in tests.
