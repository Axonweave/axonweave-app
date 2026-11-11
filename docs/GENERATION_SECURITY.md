# Study generation security review (Phase 4, M8)

Scope: everything under `/api/v1/study`, the worker tasks `study.*`, the study tables (migrations 0004 to 0008) and `frontend/src/features/study`. Requirements: `PHASE4_SPEC.md` section 21 and the ten tests of 22.7. Reviewed against `CLAUDE.md` rules 1 to 15 (13 applies to every source read).
Method: read the code paths, then prove each control with a test that fails if it is removed. Nothing here was verified against a live model; see "Not verified".

## 1. Controls and evidence
| Area (spec) | Control | Evidence |
|---|---|---|
| Authentication (21.1) | Every study route requires a logged-in, active user; state-changing routes need CSRF | `tests/study/test_route_sweep.py` enumerates the routes from the app itself (41 cases): each answers 401 or 403 without a login. A route added later is covered automatically. |
| Source ownership (21.2) | Every document, chapter, subject, folder or workspace id goes through `ScopeResolver`; foreign ids are 404 and nothing is created | `test_generation_flow.py::test_foreign_source_ids_are_404_not_403`, `test_summary.py::test_foreign_document_cannot_be_summarised`; the worker re-verifies the scope when it reads (sources may change after the request) |
| Settings and limits (21.1, 21.6) | Pydantic settings per generator (unknown fields rejected), per-generator maximum items, max 20 documents, max pasted text, max scope tokens, input and output token caps, job timeout and task time limits | `test_unknown_type_and_bad_settings`, `test_large_scope_is_sampled_and_reports_truncation`, `test_too_large_without_sampling_is_refused`, `test_time_limits_must_be_consistent` |
| Cost protection (21.6) | Per user: requests per minute (10), daily generation jobs (20), simultaneous active jobs (2), daily token quota shared with chat, 30 exports per hour. Jobs that never reach the provider do not use quota. | `test_daily_quota`, `test_per_minute_limit_and_token_quota`, `test_active_job_cap`, `test_failed_before_any_provider_call_does_not_use_quota`, export rate limit test |
| Duplicate requests (21.1) | Request fingerprint plus a partial unique index on active statuses | `test_identical_active_request_returns_the_existing_job`, `test_same_request_by_another_user_is_independent` |
| Usage tracking (21.6) | One `ai_usage_records` row per provider attempt, `request_kind='generation'`; unknown tokens and cost stay NULL | usage tests in `tests/ai`, generation flow tests |
| Output validation (21.3) | JSON parsed and validated by a Pydantic model per generator; semantic rules (counts, duplicates, per-type answer rules); one correction call listing field paths and rule names only, then a safe failure | `test_invalid_output_is_corrected_once`, `test_invalid_twice_fails_safely`, `test_invalid_answer_keys_fail_safely` |
| Citations (21.3) | The model returns source numbers; the backend maps them to the units it sent and strips the rest. Numbers are never trusted as ids. | `test_invalid_references_are_stripped`, `test_unsupported_cards_are_dropped` |
| Markdown and HTML (21.3) | The frontend renders model text through `react-markdown` with `rehype-sanitize`, no raw HTML, safe URL schemes only, no images, no `dangerouslySetInnerHTML`. Flashcards, quiz text and glossary entries are plain text. | `features/ai-tutor/markdown.test.tsx` (shared component), `study.test.tsx` |
| Formulas (21.3, D-98) | The backend drops unsafe LaTeX before storage; the browser renders with KaTeX `trust:false`, expansion and size limits, DOM output (no raw HTML). Parse failures are shown as text. | `test_dangerous_expressions_are_rejected`, `test_inequality_is_not_html`, `study.test.tsx` "never turns hostile input into HTML or links", Playwright formula test |
| Code and URLs (21.3) | Nothing generated is executed. Generated URLs are not followed or fetched; links render only for http, https and mailto and open with `noopener noreferrer`. | markdown tests |
| Prompt injection | Source text sits in the user turn inside escaped SOURCE markers as data; a system rule says to ignore instructions inside sources; permissions are enforced in code, never by the prompt | `test_prompt_marks_sources_as_untrusted_data`, `test_instructions_inside_a_document_are_data_not_commands` |
| Quiz answer key (21.4) | Key stored once in `quiz_questions`; no schema used before submission has a key field; results route 409 until submitted | `test_no_response_schema_exposes_the_key_except_the_results_route`, `test_no_get_returns_a_key_value_before_submission`, `test_submit_response_does_not_leak_the_key`, `test_request_models_cannot_set_an_answer_key`; Playwright asserts no response before submit contains a key word |
| Attempt integrity (21.4) | Attempt ownership checked through the quiz; submit idempotent and row-locked; answers frozen after submit; server-side deadline | `test_double_submit_is_idempotent_and_answers_are_frozen`, `test_timer_is_server_side`, `test_an_attempt_cannot_be_used_through_another_quiz` |
| Privacy (21.5) | Materials are private; owner-scoped queries; no source text stored (references only; pasted text removed after reading); deletion cascades; account export and deletion cover study data | `test_no_source_text_is_stored`, `test_account_export_includes_study_data`, `test_account_deletion_removes_study_data_and_queues_export_files` |
| Logging (21.5, rule 12, 13) | Logs carry ids, counts, codes and durations only | `test_no_source_prompt_or_output_text_in_logs` |
| Exports (14) | Private storage, ownership-checked short-lived download, `attachment`, `nosniff`, CSV formula neutralisation, plain-text PDF, escaped Markdown, no keys | `EXPORT_SYSTEM.md` tests |
| Dependencies | `pip-audit`: no known vulnerabilities. `npm audit --omit=dev`: KaTeX advisory GHSA-238p-pmpm-9mq7 (prototype pollution can bypass `trust`, versions before 0.18.2) found on 0.16.22 and fixed by upgrading to 0.19.1. Six findings remain, all in the `shadcn` CLI dependency tree (minimatch, deepmerge) and not in code that serves users; they were present before Phase 4. | commands in `PHASE4_ACCEPTANCE.md` |

## 2. The ten tests of spec 22.7
| # | Test | Where |
|---|---|---|
| 1 | A cannot read B's material | `test_summary.py::test_another_user_gets_404_everywhere`, `test_library_export.py::test_foreign_ids_are_404_on_every_route`, Playwright "a second user cannot see or open any of it" |
| 2 | A cannot modify B's flashcards | `test_flashcards.py::test_a_card_cannot_be_reached_through_another_users_set_or_job`, `test_another_user_gets_404_everywhere` |
| 3 | A cannot submit to B's attempt | `test_quiz.py::test_another_user_gets_404_everywhere`, `test_an_attempt_cannot_be_used_through_another_quiz` |
| 4 | Keys are not exposed | see the answer-key row above |
| 5 | Invalid source ids rejected | `test_bad_source_shapes_are_rejected`, `test_foreign_source_ids_are_404_not_403` |
| 6 | Invalid generation types rejected | `test_unknown_type_and_bad_settings` |
| 7 | Excessive requests rejected | `test_daily_quota`, `test_per_minute_limit_and_token_quota`, `test_active_job_cap` |
| 8 | Unsafe output is not executed | LaTeX, Markdown and `test_card_text_is_stored_as_data_not_markup` |
| 9 | Deleted materials are inaccessible | `test_delete_cascades_versions_and_cards`, Playwright delete |
| 10 | Citations validated | `test_invalid_references_are_stripped` |

## 3. Findings and fixes during M6 to M8
1. **No way to reach a deck or quiz from its material** (functional gap that would have forced the UI to guess ids): `StudyMaterialOut.item_id` added, resolved owner-scoped through the existing repositories; test `test_material_reports_deck_and_quiz_item_ids` includes the foreign-user 404.
2. **KaTeX advisory** on the first installed version, fixed by upgrading (see the dependencies row).
3. **Autosave stale-state bug** in the quiz page (found by a Vitest case; it would have saved empty answers). The page now saves from refs holding the latest values.
4. No cross-user, key-leak or injection defect was found in the backend during the sweep.

## 4. Accepted risks and limits
- A formula that is syntactically valid can still be wrong. The sheet says "Not verified" and a human must check it against the source.
- Short-answer and descriptive questions are self-assessed; there is no model grading (D-96).
- The PDF export shows non-Latin characters as `?`.
- The worker egress allow-list (D-77) includes the provider host; study generation adds no new egress.
- A model can still produce a plausible but unsupported statement inside a section that has a valid reference. References show where the model claims the text came from; they do not prove entailment. Section text marked `additional_explanation` is labelled in the UI.

## 5. Not verified (needs a person, a key or real data)
Prompt-injection resistance against a real model; quality and cost on real lecture material; behaviour under real provider outages; a screen-reader pass and colour-contrast check; PDF and DOCX files opened in real viewers. See `STUDY_GENERATION_TESTING.md`.
