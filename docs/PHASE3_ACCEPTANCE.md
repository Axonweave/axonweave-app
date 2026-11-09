# Phase 3 acceptance (spec section 23)

Assessed 2026-11-09 on `main` after PR #26. Ratings: **Met** = implemented and verified by a named test or a check that was
run; **Partly** = real but incomplete or unverified; **Not met** = not delivered. Evidence: `DOCUMENT_SECURITY.md`,
`RETRIEVAL_EVALUATION.md`, `RAG_EVALUATION.md`, tests named below. CI (backend, frontend, e2e with worker and object
store, security) was green on every PR merged for Phase 3 (#23 to #26); `main` itself was not re-run after the final merge.

## Overall
Phase 3 is **functionally complete and tested on the fake LLM and, through scripts and the API, on the real Gemini
provider**, but **not fully accepted**: the human faithfulness check has not been done, embeddings in the compose worker
are blocked by its no-egress network, and the browser has not been used against real providers. Tally:
**Met 26, Partly 6, Not met 0** (32 items).

## Document management
| Criterion | Rating | Evidence |
|---|---|---|
| PDF upload works | Met | `tests/ingestion/test_extractors.py`, `test_processing_api.py::test_full_flow...`; PDF viewer unit tests. No real PDF through the browser e2e (text file only) |
| PPTX / DOCX upload works | Met | `test_extractors.py` (generated fixtures, D-76) |
| Text and Markdown upload works | Met | `test_documents_api.py`; `e2e/library.spec.ts` (txt end to end through worker) |
| Image OCR works where supported | Partly | extractor and OCR tests exist; PDF OCR shows status `extracting` rather than its own state; no OCR accuracy measurement |
| Documents securely stored | Met | `tests/storage/*`, D-64 private bucket, backend-generated keys |
| Associated with workspaces | Met | `test_foreign_placement_is_404`, move tests; upload links from subject/chapter pages |
| Processing status visible | Met | `test_full_flow_status_details...`; `library.test.tsx`; e2e "Ready" |
| Failed processing can be retried | Met | `library.test.tsx` retry; `test_processing_api.py` |
| Documents can be deleted | Met | `test_delete_removes_row_and_queues_object_cleanup`; e2e delete |

## Extraction and indexing
| Criterion | Rating | Evidence |
|---|---|---|
| Text extraction | Met | `test_extractors.py` |
| Page and slide references preserved | Met | `test_slide_content_filter`; citations carry page/slide |
| Structure retained | Met | chunker tests (headings, bbox) |
| Chunking | Met | `tests/ingestion/test_chunker*.py` |
| Chunk metadata preserved | Met | `test_document_schema.py` |
| Embeddings generated | Partly | real `gemini-embedding-001` verified from the API container (`rag_live_check.py`); the compose worker cannot reach the provider (`DOCUMENT_SECURITY.md` section 4) |
| pgvector indexing | Met | `test_a_vector_of_the_wrong_length_is_rejected_by_the_column`; exact filtered cosine, no ANN by design |
| Versions managed | Met | `test_reprocessing_rebuilds_chunks...`, `test_failed_reprocess_does_not_leave_a_searchable_version`; `scripts/reindex_documents.py` |

## Retrieval
| Criterion | Rating | Evidence |
|---|---|---|
| Semantic search | Met | `test_keyword_semantic_hybrid_find_the_right_chunk`; metrics in `RETRIEVAL_EVALUATION.md` (small generated corpus) |
| Keyword search | Met | same; `test_degrades_to_keyword_when_embedder_fails` |
| Hybrid search | Met | RRF, same test |
| Scope filtering | Met | `test_each_scope_kind` |
| User isolation | Met | `test_other_users_chunks_never_returned`, `test_foreign_scope_ids_are_404` |

## RAG
| Criterion | Rating | Evidence |
|---|---|---|
| Answers use retrieved content | Met | `tests/ai/test_rag.py`; one live run (`RAG_EVALUATION.md`) |
| Document-only / document-first / general modes | Met | `test_rag.py` mode tests |
| Unsupported answers handled honestly | Partly | fixed reply with no LLM call tested; model-side behaviour in `document_first` is unscored by a person |
| Citations reference retrieved content | Met | validated `[n]` mapping tests |
| Citations open the correct location | Partly | link carries page and passage; highlight overlay unit-tested only for region filtering, **not checked on a real PDF in a browser** |

## Security
| Criterion | Rating | Evidence |
|---|---|---|
| File access protected | Met | `DOCUMENT_SECURITY.md` cases 1, 9 |
| Uploaded content untrusted | Met | cases 7, 8 |
| Retrieval enforces ownership | Met | cases 2 to 4 |
| Deleted content out of search | Met | case 5 |
| Sensitive content out of logs | Met | `test_document_text_never_reaches_the_logs`, `test_no_passage_text_in_logs` |

## Quality
| Criterion | Rating | Evidence |
|---|---|---|
| Processing asynchronous | Met | Celery worker; e2e |
| Duplicate processing prevented | Met | `test_duplicate_deliveries_at_the_same_time_run_once`, one running job per version |
| Retrieval tests pass | Met | CI backend job |
| RAG evaluation documented | Partly | documented, but the human faithfulness spot-check is **pending** |
| API and frontend tests pass | Met | CI green on #23 to #26; Vitest 228 passed |

## Failure behaviour (TASKS M7)
| Case | Evidence |
|---|---|
| Worker crash mid-job | `test_sweep_fails_only_jobs_with_no_recent_sign_of_life`, `test_stale_queued_jobs_are_found_for_redispatch` (unit level; no real container kill) |
| Redis down | `test_rate_limit_redis.py` fallback tests (limiter only); job dispatch falls back to the sweeper. Not tested with a real Redis outage |
| Storage down | `test_storage_not_configured_is_503_and_nothing_else_breaks` |
| Embedder failing | `test_degrades_to_keyword_when_embedder_fails`, `test_without_embedder_completes_with_warning` |
| Duplicate delivery | see above |
| Large upload | `test_oversize_body_is_cut_off_by_content_length`, `test_s3_multipart_upload_streams_a_large_object` |
| Many small uploads | `test_too_many_files` (count limit); no load test |

No load or soak test was run; no timing or throughput numbers exist.

## Open items
Human faithfulness check; worker egress for embeddings; ClamAV adapter; real-PDF browser check of highlighting; PDF OCR
status label; `.env.example` retrieval placeholders (human paste, see `PHASE3_ENV_PLACEHOLDERS.md`); 29 `format:check`
warnings; real load test.
