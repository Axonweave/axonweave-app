# RAG evaluation (Phase 3)

Counts and metrics only; no document or answer text (D-76). M7 adds the human faithfulness spot-check.

## Real-provider run through the API (M5, 2026-11-09)

`backend/scripts/rag_live_check.py`: a throwaway user and a generated 4-paragraph document in the
dev database, indexed with `gemini-embedding-001` (768 dims), then asked through the HTTP API with the
configured Gemini chat model. The user is deleted afterwards (cascade verified).

| Check | Result |
|---|---|
| Indexing (extract, chunk, embed, write) | succeeded |
| Scoped conversation created (document scope) | 201 |
| Grounded question, non-streaming | completed, finish `stop`, 1 citation (`[1]`), 381 in / 43 out tokens, prompt `rag_document_only` |
| Off-topic question in `document_only` mode | fixed insufficient-evidence reply, **no LLM call** (tokens NULL), 0 citations |
| Grounded question, streaming | 7 events, `message.citations` before the first `message.delta`, ended `message.completed` |

**Limits:** one tiny document, three questions. It shows the pipeline works with the real providers,
not answer quality. Faithfulness was not scored here; that is the M7 human spot-check.

## Human faithfulness spot-check (M7): NOT DONE

Faithfulness (does every claim in an answer follow from the cited passage) must be judged by a person, not by the
model alone. Nobody has done this yet, so there is no score. Procedure for the reviewer:

1. Upload a real study document you own to a dev stack with real providers (do not commit it; use `testdata-private/`).
2. Ask 20 questions: 12 answerable from the document, 4 partly answerable, 4 not covered.
3. For each answer record: supported by the cited passage (yes / partly / no), citation opens the right place (yes/no),
   honest refusal when unsupported (yes/no/NA). Record counts only, not text.

| Date | Reviewer | Questions | Supported | Partly | Unsupported | Correct citation location | Honest refusals |
|---|---|---|---|---|---|---|---|
| (pending) | | | | | | | |

Known limits: retrieval metrics come from a small generated corpus (`RETRIEVAL_EVALUATION.md`); the live run covered one
tiny document and three questions.
