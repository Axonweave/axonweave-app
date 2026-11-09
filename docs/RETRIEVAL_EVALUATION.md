# Retrieval evaluation (Phase 3 M4)

Reports counts and metrics only; no document text (D-76). The corpus is original text generated in
`backend/scripts/eval_retrieval.py`.

## Embedding model (D-69)

- Verified 2026-11-09 with `scripts/list_embedding_models.py`: the configured key can use
  `gemini-embedding-001` (input limit 2048) and `gemini-embedding-2` (8192).
- Chosen: `gemini-embedding-001` at `output_dimensionality=768` (matches the column). Vectors are
  L2-normalised by the adapter. `gemini-embedding-2` returned a bad-response error in our adapter and
  was not used.
- The API reports no token count for embeddings, so usage rows are estimated (chars / 3) and cost is NULL.

## Real-provider run (`gemini-embedding-001`, 2026-11-09)

10 passages in 5 topics, 10 on-topic queries, 2 off-topic queries.

| Metric | Value |
|---|---|
| Recall@3 | 1.000 |
| Precision@3 | 0.667 (2 relevant passages per topic, so 0.667 is the ceiling) |
| MRR | 1.000 |
| Relevant cosine | 0.582 to 0.768 |
| Best irrelevant cosine (on-topic queries) | 0.468 to 0.610 |
| Best cosine for off-topic queries | 0.509 to 0.512 |

**Threshold:** `retrieval_min_vector_score = 0.55` is kept. It rejects both off-topic queries and
most cross-topic matches but admits a few cross-topic ones (up to 0.61). Hybrid fusion and the
answer prompt (M5) are expected to absorb these. **Limit:** this is a tiny corpus; re-run on
`testdata-private/` material before relying on the number.

## Exact vs ANN (D-73)

Search is exact and filtered by user and verified document ids. No ANN index was added: the
measured corpus is far too small to justify one, and an unmeasured index risks filtered-recall loss.
Re-measure with realistic volumes (tens of thousands of chunks per user) before adding HNSW.

## Fake provider

`FakeEmbeddingProvider` (hashed bag-of-words) is used only in tests; its scores are lower, so tests
lower the threshold explicitly. It says nothing about real quality.
