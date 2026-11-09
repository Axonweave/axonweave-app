# Document security review (Phase 3 M7)

Scope: spec sections 21 and 22.5, decisions D-64 to D-76. Reviewed 2026-11-09 against `main` after PR #26.
Honest scope note: this is a code and test review plus automated scans. It is not a penetration test.

## 1. The ten security cases (spec 22.5)

| # | Case | Evidence (named tests) |
|---|------|------------------------|
| 1 | A cannot download B's document | `tests/documents/test_documents_api.py::test_other_users_document_is_404_on_every_route` (covers download and inline) |
| 2 | A cannot retrieve B's chunks | `tests/retrieval/test_search.py::test_other_users_chunks_never_returned`; `tests/documents/test_processing_api.py::test_extracted_text_is_never_served_to_another_user`; `test_document_schema.py::test_chunk_of_another_users_document_is_rejected` (DB-level) |
| 3 | A cannot search B's embeddings | `test_search.py::test_other_users_chunks_never_returned`, `::test_foreign_scope_ids_are_404`, `::test_resolved_scope_cannot_be_forged` |
| 4 | A cannot use B's document id as RAG context | `tests/ai/test_rag.py::test_foreign_scope_is_404`; `test_search.py::test_foreign_scope_is_404_and_validation` |
| 5 | Deleted documents are not searchable | `test_search.py::test_inactive_documents_excluded`; `tests/ingestion/test_pipeline.py::test_deleted_document_mid_flight_is_not_resurrected`; `test_rag.py::test_deleted_document_keeps_only_name_and_page` |
| 6 | Old versions are not returned after replacement | `test_search.py::test_other_model_or_index_version_excluded`; `test_pipeline.py::test_failed_reprocess_does_not_leave_a_searchable_version`, `::test_reprocessing_rebuilds_chunks_without_duplicates` |
| 7 | Invalid files are rejected | `test_documents_api.py`: `test_spoofed_type_or_empty_is_rejected`, `test_html_hidden_in_text_file_is_rejected`, `test_binary_text_and_bad_utf8_rejected`, `test_zip_bomb_by_ratio_is_rejected`, `test_zip_total_size_and_entry_count_limits`, `test_zip_path_traversal_nested_archive_and_macros_rejected`, `test_corrupt_zip_is_rejected`, `test_image_decompression_bomb_is_rejected`, `test_oversize_body_is_cut_off_by_content_length`; `test_pipeline.py::test_content_that_no_longer_matches_its_type_is_rejected`, `::test_tampered_object_is_rejected_by_checksum` |
| 8 | Malicious content is not executed | `test_documents_api.py::test_inline_is_pdf_or_image_only_and_sandboxed`, `::test_download_streams_attachment_with_safe_headers`; `test_rag.py::test_prompt_injection_inside_a_document_is_escaped`; parsing happens only in the worker (D-70); frontend renders passages as text (`citations.test.tsx` "renders passage text as plain text") |
| 9 | Signed URLs expire | **Not applicable by design (D-64):** the bucket is private and no signed or pre-signed URL is ever issued; downloads are streamed by the API after an ownership check. There is nothing to expire. Key safety: `test_storage.py::test_is_valid_original_key_rejects_foreign_keys`, `test_key_builder_rejects_*`, `test_outbox_never_acts_on_a_key_it_could_not_have_generated` |
| 10 | Unauthorised citation access is rejected | `test_rag.py::test_owner_reads_citation_and_source_others_get_404`; `test_document_schema.py::test_citation_cannot_point_at_another_users_chunk` |

## 2. Other section 21 controls

| Control | Evidence |
|---|---|
| No content in logs | `test_pipeline.py::test_document_text_never_reaches_the_logs`; `test_rag.py::test_no_passage_text_in_logs` |
| Fail closed if a scanner is enabled but unavailable | `test_documents_api.py::test_scanner_enabled_but_unavailable_fails_closed` (no ClamAV adapter exists yet, see open items) |
| Rate limits (upload, search) | `test_documents_api.py::test_upload_rate_limit_returns_429`; `test_search.py::test_rate_limited` |
| Fake providers refuse production | `tests/test_phase3_config.py::test_fake_embedder_is_refused_in_production` |
| Unauthenticated sweep over document routes | `tests/test_spec_security_cases.py` (all-routes sweep) |
| Deleting a source keeps only name and page on citations (D-66) | `test_rag.py::test_deleted_document_keeps_only_name_and_page` |
| Timeouts and memory limits map to safe error codes | `test_pipeline.py::test_timeout_and_memory_errors_map_to_safe_codes` |

## 3. Scans run

| Scan | Result |
|---|---|
| `pip-audit -r backend/requirements.txt` (2026-11-09) | no known vulnerabilities |
| `npm audit --omit=dev` (2026-11-09) | 2 low, 4 moderate, none high. **A high finding was fixed during M6:** `pdfjs-dist` 5.7.284 (GHSA-hq66-cqwq-w95j, code execution on a malicious PDF), upgraded to 6.5.438 |
| Secrets in tracked files (pattern grep for API keys / private keys) | none found |
| Frontend bundle scan (`.next/static`, `.next/server` for key patterns, `GEMINI_API_KEY`, signed-URL markers) | none found |
| CI security job (gitleaks, dependency audit) | passes on PR #26 |

gitleaks was not run locally (not installed); only CI ran it.

## 4. Worker isolation

Verified in `docker-compose.yml`: worker uses the `internal` network (`internal: true`, no route out), non-root,
`read_only: true` with a 512 MB tmpfs scratch, `cap_drop: [ALL]`, `no-new-privileges`, `mem_limit: 1g`. Per-job
timeouts, page/character/OCR caps are enforced in code and tested. The API image does not import parser libraries.

**Gap found:** because the worker has no route out, it **cannot reach the embedding provider** (Gemini) in this
compose file. With `EMBEDDING_PROVIDER` set, indexing in the worker would hit `EMBEDDINGS_UNAVAILABLE` and the document
completes with keyword search only. Live embedding was verified only by running the pipeline from a script in the
API container (`rag_live_check.py`, `eval_retrieval.py`), not through the compose worker. Fix needed before relying on
embeddings in the worker: add a controlled egress (for example an allow-listed forward proxy on a second network for the
embedding host only) and test it. Not done.

## 5. Open items

- No antivirus adapter (ClamAV) is implemented; the interface fails closed if enabled without one.
- The worker memory cap relies on the container `mem_limit` (no in-process rlimit).
- Worker egress to the embedding provider (section 4).
- 6 moderate/low npm advisories in dev-tooling transitive dependencies.
- gitleaks run locally; only CI covers it.
