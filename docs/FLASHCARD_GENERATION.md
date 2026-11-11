# Flashcard generation (Phase 4)

Requirements: `PHASE4_SPEC.md` section 6. Decisions: D-93. Code: `app/study/generators/flashcards.py`, `app/modules/study/flashcard_service.py` and `flashcard_routes.py`, prompt `study_flashcards`.

## Settings
`generation_type: "flashcards"`

| Setting | Values | Default |
|---|---|---|
| `count` | 1 to 50 | 10 |
| `card_type` | `mixed`, `basic`, `definition`, `concept`, `comparison`, `fill_in_the_blank`, `application` | `mixed` |
| `difficulty` | `easy`, `medium`, `hard`, `mixed` | `mixed` |
| `include_examples`, `include_explanations`, `include_source_references` | bool | false, true, true |

## Storage
A deck is a `flashcard_sets` row (one per flashcard material) plus `flashcards` rows (front, back, explanation, type, difficulty, `source_references`, `display_order`, `is_favourite`, `origin` generated or manual, `revision`). The cards are the live, editable state; the material keeps the original generated snapshot as version 1. Because of that the generic material edit, restore and regenerate paths refuse decks (422). `GET /study/materials/{id}` returns `item_id`, the deck id.

## Quality rules (generated and typed cards)
One concept per card; front 5 to 400 characters; back at most 1200; explanation at most 1200; front and back not identical; a fill-in-the-blank card needs a `___` blank and a short answer (at most 120 characters). Word-set similarity of 0.8 or more is a near-duplicate: a generated near-duplicate fails validation (one correction call); a typed one is 409 `FLASHCARD_DUPLICATE`. A generated card whose source numbers do not map to a real source is dropped as unsupported. Card text is stored as data, never as markup.

## Endpoints
`GET /study/flashcards/{set_id}`; `POST /study/flashcards/{set_id}/cards` (max 200 cards per deck); `PATCH` and `DELETE /study/flashcards/cards/{card_id}`; `PUT /study/flashcards/{set_id}/order`; `POST /study/flashcards/{set_id}/regenerate` (selected cards, at most 30) and `POST .../regenerate/{job_id}/apply`. Regeneration is a preview: applying replaces the selected cards in place, answers 409 `PREVIEW_STALE` if one of them was edited or deleted meanwhile, and keeps the user's card where the replacement would duplicate another.

## UI
Deck page with Study mode (flip, previous, next, shuffle, progress, left and right arrow keys) and Edit mode (add, edit, delete, favourite, move up or down, select cards to regenerate with a side-by-side preview). No spaced-repetition scheduling (spec 20.4, section 24).

## Tests
`backend/tests/study/test_flashcards.py`; `frontend/src/features/study/study.test.tsx` (study mode, shuffle); `frontend/e2e/study.spec.ts` (keyboard flip, edit a card).
