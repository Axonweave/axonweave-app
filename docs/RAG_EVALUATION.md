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
