# Study library, versions, regeneration and preferences (Phase 4)

Requirements: `PHASE4_SPEC.md` sections 12, 13, 16, 19.2. Decisions: D-83, D-92, D-93, D-100. Code: `app/modules/study/library_routes.py`, `library_service.py`, `material_service.py`, `preferences_service.py`; UI `frontend/src/features/study/`.

## Endpoints
| Method and path | Purpose |
|---|---|
| `GET /study/materials` | List. Filters `q` (title and stored payload, LIKE wildcards escaped), `resource_type`, `workspace_id`, `subject_id`, `chapter_id`, `status`, `archived`; sort allow-list `created_at`, `updated_at`, `title`, `resource_type`; `limit` at most 100. List items carry no content. |
| `GET /study/materials/{id}` | One material with content, source list, `unavailable_document_ids` and `item_id` (deck or quiz row). |
| `PATCH /study/materials/{id}` | Edit (`expected_version`, `payload`); a new version. 409 `MATERIAL_VERSION_CONFLICT` if the version moved. |
| `GET /study/materials/{id}/versions`, `/versions/{n}` | History and one snapshot. |
| `POST /study/materials/{id}/restore` | Copy an old version forward as a new version. |
| `POST /study/materials/{id}/regenerate` | Preview job (whole or `section_index`). `GET /study/generations/{job}/preview`, `POST .../preview/apply`, `DELETE .../preview`. |
| `POST /study/materials/{id}/duplicate` | Copy (summaries, guides, glossaries, formula sheets, decks). Quizzes and banks: 422 `DUPLICATE_NOT_SUPPORTED` (the keys would have to be copied). |
| `POST .../archive`, `.../unarchive`, `DELETE /study/materials/{id}` | Archive and delete. Delete cascades versions, deck or quiz rows and queues export files for cleanup. |
| `GET/PUT /study/preferences` | Generation defaults (language, explanation level, summary length, question difficulty, examples, definitions, references). PUT replaces. |

Every route authenticates, checks the account is active and scopes by owner; a foreign or missing id is 404.

## Versioning rules
Version 1 is the generated original (`origin=generated`) and is never changed. Edits, restores and applied regenerations add versions. Regeneration never overwrites an edit: the preview records the version it was based on and applying it after a later edit is 409 `PREVIEW_STALE`. Decks and quizzes keep their live items in their own tables and are edited through `/study/flashcards/*`; the generic edit, restore and regenerate paths refuse them (422).

## Deleted sources
Deleting a source document does not delete materials. They keep their text and report `unavailable_document_ids` and `unavailable_source_count`; the viewer shows a notice and the reference chips say "Source unavailable".

## Preferences as defaults
A preference is applied only where the generator has a matching setting, the value validates, and the request did not set it. Regenerations keep the material's own settings. Nothing is inferred about the user.

## UI
Study materials (`/study`, also linked from the Library page and the sidebar): search, type filter, archived toggle, list with duplicate, archive and delete (with confirmation), running jobs with progress, cancel and failure messages, Generate dialog (source selector, type, only the relevant settings, language, a note on AI usage). Entry points: subject, chapter and document pages open the dialog with the source fixed. Viewer: edit, versions, regenerate review, export, archive, delete. Preferences: Settings, "Study material".

Not built: favouriting whole materials (spec 12.3 lists it; M5 did not include it). Flashcards can be favourited per card.

## Tests
`backend/tests/study/test_library_export.py`, `test_summary.py`, `test_flashcards.py`; `frontend/e2e/study.spec.ts`.
