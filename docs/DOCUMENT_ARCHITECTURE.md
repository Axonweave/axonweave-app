# Document architecture (Phase 3, Part B)

Status: **design, not built.** Decisions are D-62 onward in `DECISIONS.md`. Review of the current code: `DOCUMENT_INTELLIGENCE_PLAN.md`.
Same conventions as `AI_ARCHITECTURE.md`: route -> service -> repository -> model; no SQL outside repositories; no vendor SDK outside
its provider package; every constraint on the SQLAlchemy model (D-61).

## 1. Principles

1. **Documents are untrusted input.** Parsed only in the worker, never executed, links never followed.
2. **Filter by owner before content reaches any model.** Retrieval takes a verified set of document ids; there is no global vector search.
3. **Provider independent.** `EmbeddingProvider` mirrors `LLMProvider`; `StorageBackend` hides S3.
4. **Idempotent, versioned processing.** Reruns rebuild one version's artifacts in one transaction; only the active version of a completed document is searchable.
5. **No divergence.** DB and object storage are reconciled through an outbox, never by hoping two deletes both succeed.
6. **Reusable.** Phase 4 (flashcards, quizzes, study guides) reads documents through `ScopeResolver` and `SourceReader`, not through SQL of its own.
7. **Runs without it.** No storage, Redis or embedder configured: Phase 1 and 2 features work; document endpoints answer 503 (`STORAGE_NOT_CONFIGURED`, `PROCESSING_UNAVAILABLE`, `EMBEDDING_NOT_CONFIGURED`).

## 2. Module layout (`backend/app`)

```
modules/documents/     routes.py  service.py  schemas.py          upload, list, get, patch, delete, retry/reprocess, status, download, inline
modules/search/        routes.py  schemas.py                      POST /search (thin; calls retrieval)
modules/citations/     routes.py                                  citation + source passage lookup
repositories/          document_repository.py  document_chunk_repository.py  processing_job_repository.py
                       storage_cleanup_repository.py  citation_repository.py
models/                document.py  document_version.py  document_chunk.py  document_processing_job.py
                       storage_cleanup.py  message_citation.py
storage/               base.py (StorageBackend)  s3_backend.py  memory_backend.py  keys.py
ingestion/             pipeline.py  stages/{validate,extract_pdf,extract_pptx,extract_docx,extract_text,ocr,normalise,chunk,embed,index}.py
                       limits.py  safety.py (magic bytes, zip/image bounds)  scanner.py (Scanner, NullScanner, ClamAVScanner)
                       tasks.py (Celery tasks)  worker.py (celery app)
embeddings/            base.py (EmbeddingProvider)  registry.py  gemini_embedding_provider.py  fake_embedding_provider.py
retrieval/             scope.py (ScopeResolver)  searcher.py  fusion.py (RRF)  reader.py (SourceReader)  types.py
rag/                   context_source.py (DocumentContextSource)  prompt.py  citations.py (parse/validate/strip)  modes.py
ai/prompts/            rag_document_only.py  rag_document_first.py                    versioned like academic_tutor (D-41)
core/rate_limit.py     + RedisRateLimiter                                                same Protocol
```

Layer rules: routes call services; services own transactions, ownership and quotas; `ingestion/` and `retrieval/` receive plain inputs and
repositories; `rag/` plugs into the existing `ContextManager` as a `ContextSource`. Provider SDK imports are allowed only in
`ai/providers/` and `embeddings/gemini_embedding_provider.py`; the import-boundary test is extended to both.

## 3. Data model

All UUID PKs, UTC timestamps, explicit delete behaviour. Names follow the spec; changes from the spec are marked **(changed)** and justified in D-67 to D-69.

**`documents`**: `id`, `user_id` FK users CASCADE, `workspace_id`, `subject_id` null, `folder_id` null, `chapter_id` null, `display_name`,
`original_filename`, `file_type`, `mime_type` (detected, not browser), `file_size`, `checksum` (SHA-256), `processing_status` (denormalised
copy of the latest version, D-68), `active_version` null, `latest_version`, timestamps, `archived_at` null. **(changed)** no `deleted_at`;
no `storage_key` on the document (it is per version). Composite FKs `(workspace_id, user_id)`, `(subject_id, workspace_id)`, `(folder_id,
subject_id)`, `(chapter_id, subject_id)` so the chain is consistent in the database (D-09 style). `UNIQUE (id, user_id)`.
Parent delete: documents attach with `ON DELETE CASCADE` from workspace/subject, and `SET NULL` for folder/chapter (a document survives its
folder or chapter being deleted but stays in the subject). Cascading rows are cleaned from storage by the outbox (D-66).

**`document_versions`**: `id`, `document_id`+`user_id` composite FK CASCADE, `version_number`, `storage_key` (generated, D-64),
`file_size`, `checksum`, `processing_status` (**authoritative**), `extraction_method`, `ocr_used`, `ocr_mean_confidence` null, `page_count`,
`slide_count`, `word_count`, `warnings` JSONB (safe codes only), `pipeline_version`, `index_version`, `created_at`.
`UNIQUE (document_id, version_number)`.

**`document_processing_jobs`**: `id`, `document_version_id` FK CASCADE (+ `document_id`, `user_id` for scoping), `pipeline_version`, `status`
(`queued|running|succeeded|failed|cancelled`), `stage`, `retry_count`, `error_code` (safe), `celery_task_id`, timestamps. **Partial unique
index** on `(document_version_id)` WHERE `status = 'running'` (one running job per version).

**`document_chunks`**: `id`, `user_id`, `document_id`, `document_version_id`, `workspace_id`, `subject_id` null, `folder_id` null, `chapter_id`
null, `chunk_index`, `content`, `content_tsv` (generated `tsvector`, GIN index), `page_number` null, `slide_number` null, `section_heading`
null, `bboxes` JSONB null (PDF block rectangles for highlight), `token_count`, `char_count`, `extraction_confidence` null, `embedding
vector(N)` null (N from config, recorded in the column definition), `embedding_model`, `embedding_dimensions`, `index_version`, `created_at`.
Composite FK `(document_id, user_id)` -> `documents(id, user_id)` CASCADE; FK `document_version_id` CASCADE.
`UNIQUE (document_version_id, chunk_index)`. Indexes: `(user_id, document_id)`, `(user_id, workspace_id, subject_id)`, GIN on `content_tsv`.
The vector ANN index is added only after measurement (D-73). Scope columns are denormalised copies of the document's placement; moving a
document updates its chunks in the same transaction (a service function, tested).

**`storage_cleanup`** (outbox): `id`, `storage_key`, `reason`, `attempts`, `last_error_code`, `created_at`, `done_at` null. **No FK to users.**
Processed by a Celery task (delete object, set `done_at`; retry with backoff; alert after N attempts).

**`message_citations`**: `id`, `message_id`+`user_id` composite FK CASCADE, `rank` (the `[n]` shown), `chunk_id` null (FK SET NULL),
`document_id` null (FK SET NULL), `document_name`, `document_version`, `page_number`, `slide_number`, `section_heading`, `snippet`, `score`,
`available` bool. On document delete: link nulled, `available=false`, `snippet` cleared (D-66).

**Existing tables extended**: `conversations.scope_type` (`general|workspace|subject|folder|chapter|document`) and `scope_id`, with a CHECK
(`general` has no id; every other type has one) and service-level ownership validation; `messages.scope_type`/`scope_id`/`answer_mode`
record what was used for each answer; `ai_usage_records.request_kind` (`chat|embedding|generation`).

## 4. Pipeline

### 4.1 Upload request (API process, synchronous, fast)
1. Authenticate, check active account, resolve the target chain (workspace -> subject -> folder/chapter) scoped by `user_id`; 404 if any link is not the caller's.
2. Quotas: files per request, documents per user, bytes per user (counted in the database inside the transaction), upload rate limit.
3. Stream the multipart body to a **temp file / spooled buffer in chunks**, counting bytes; abort with 413 when the limit is crossed. Never `await file.read()` the whole thing.
4. Validate: extension allow-list, **magic bytes** (not the browser MIME), display name sanitised, cheap structure checks (zip entry count and uncompressed-size ratio for docx/pptx, image dimensions for png/jpg). Optional `Scanner`.
5. One DB transaction: insert `documents` (status `uploaded`), `document_versions` (v1), `document_processing_jobs` (`queued`).
6. Upload to storage under a **generated key** `users/{user_id}/documents/{document_id}/v{n}/original.{ext}` (extension from the validated type, never from the filename).
7. Commit, then enqueue the Celery task (after commit, so the worker always sees the row). If enqueue fails the job stays `queued` and a periodic sweeper re-enqueues it.
8. Return 202 with document id and status. If the storage put fails, the transaction is rolled back; if the commit fails after the put, the object key is written to `storage_cleanup` (best effort) and reconciliation removes it.

### 4.2 Worker stages
`queued -> validating -> extracting -> ocr_processing (only if needed) -> normalising -> chunking -> embedding -> indexing -> completed`
(or `failed` / `cancelled`). The job's `stage` drives progress; the version's `processing_status` is set at each stage change and mirrored to
`documents.processing_status` when the version is the latest.

| Stage | Work |
|---|---|
| validating | Re-read the object, re-check type, size, zip and image bounds (defence in depth: the worker never trusts that the API checked) |
| extracting | PyMuPDF / python-pptx / python-docx / text. Per-page and per-slide units kept. No macros, no external fetches, links recorded as text only |
| ocr | Only pages with too little digital text; render at bounded DPI; Tesseract; confidence recorded; page numbers preserved |
| normalising | Unicode NFC, whitespace, line breaks; keep code, maths, symbols, tables |
| chunking | Structure-aware: headings, paragraphs, sentences; configurable size and overlap; table rows kept with their header; provenance (page/slide/heading/bbox) on every chunk |
| embedding | Batched `EmbeddingProvider.embed_documents`, rate-limit aware, usage recorded with `request_kind = embedding` |
| indexing | One transaction: delete this version's chunks, insert the new ones, set the version `completed`, and (if this is the version being activated) set `documents.active_version` |

Execution limits: per-job wall-clock timeout (Celery soft+hard), memory limit (`ulimit`/container limit, max pages, max extracted characters),
worker container has **no outbound network except Redis, Postgres, the object store and the embedding provider** (D-70), non-root user,
read-only root filesystem with a tmpfs scratch dir, and temp files deleted in `finally`.

### 4.3 Idempotency (D-68)
- `UNIQUE (document_version_id, chunk_index)` makes a duplicate insert fail loudly.
- Every run has a `pipeline_version` and a job id; chunks are written only by the job that holds the running slot (partial unique index).
- The write stage is `DELETE chunks WHERE document_version_id = X` then bulk insert, **in one transaction**. A crash leaves either the old state or the new one.
- A Celery redelivery for an already `succeeded` job is a no-op; for a `running` job whose heartbeat is stale it takes over.
- Expensive stages (embedding) happen before the write transaction and results are held in memory/temp, so a failed run costs money but never leaves partial rows.
- Reprocess creates a **new version row only when the file changes**; reprocess of the same file reuses the version and rebuilds its chunks (or builds a new `index_version`, D-69) and switches the active pointer in one transaction.

### 4.4 Statuses
Spec names are kept: `uploaded, queued, validating, extracting, ocr_processing, normalising, chunking, embedding, indexing, completed, failed,
cancelled`. A document is shown as ready only at `completed`. Searchable means: `documents.active_version = chunk.document_version_id` AND that
version is `completed` AND `chunk.index_version` equals the configured current index.

### 4.5 Failure
Safe error codes only (`UNSUPPORTED_TYPE`, `CORRUPT_FILE`, `PASSWORD_PROTECTED`, `TOO_LARGE`, `EXTRACTION_TIMEOUT`, `NO_TEXT_FOUND`,
`OCR_FAILED`, `EMBEDDING_FAILED`, `INTERNAL`). No stack traces or file paths reach the DB or the client; the original is kept; retry is allowed
for retryable codes. A sweeper marks jobs stuck in `running` past the timeout as `failed` (same idea as D-46).

## 5. Storage

`StorageBackend`: `put(key, stream, content_type)`, `open(key) -> async byte iterator`, `delete(key)`, `exists(key)`. Implementations:
`S3StorageBackend` (boto3/aioboto3 or `aiobotocore`, imported only in `storage/s3_backend.py`, private bucket, SSE enabled where the store
supports it, path-style for the emulator) and `InMemoryStorageBackend` (tests; refuses production like the fake providers). Keys come only
from `storage/keys.py`, built from UUIDs and a validated extension. Downloads are streamed by the backend after the ownership check with
`Content-Disposition: attachment; filename*=UTF-8''...`, `X-Content-Type-Options: nosniff`, `Cache-Control: private, no-store`. Inline PDF
view is a separate endpoint (D-72).

## 6. Embeddings

```python
class EmbeddingProvider(ABC):
    name: str
    dimensions: int | None
    async def embed_documents(self, texts: list[str], *, model: str) -> EmbeddingResult: ...
    async def embed_query(self, text: str, *, model: str) -> EmbeddingResult: ...   # task type may differ
    async def aclose(self) -> None: ...
class EmbeddingResult:  vectors: list[list[float]]; usage: Usage; model: str; dimensions: int
```

Mirrors `LLMProvider`: only `EmbeddingError` subclasses escape (same taxonomy plus `EMBEDDING_NOT_CONFIGURED`), no retries inside adapters,
usage honest (`provider_reported` / `estimated` / `unavailable`), timeouts from config. Registry maps name to factory
(`gemini`, `fake`; `sentence_transformers` is a possible later adapter that needs no key and no network; adding it is one file plus one
registry line). `FakeEmbeddingProvider`: deterministic hash-based vectors of the configured dimension so similar text gets similar vectors;
allowed only when `APP_ENV` is `development` or `testing` with `EMBEDDING_PROVIDER=fake` set explicitly, refuses production, `Settings`
rejects it in production, and the API reports `embedding_kind: "test"`. Dimension, model id and `index_version` are validated on every write; a
mismatch is an error, never a silent mix.

## 7. Retrieval

```
ScopeResolver.resolve(user, scope) -> VerifiedScope(document_ids: frozenset[UUID], label, truncated: bool)
Searcher.search(verified_scope, query, mode, top_k) -> list[Hit]
SourceReader.read(verified_scope|document_id, ...) -> chunks in order, or by similarity
```

- **ScopeResolver** accepts `workspace | subject | folder | chapter | document` ids (and "all my documents"), checks the full ownership chain
  with queries scoped by `user_id`, then returns the ids of the user's **searchable** documents (active version completed, not archived unless
  asked). Unknown or non-owned ids raise 404 (same error as not found). The result type can only be built by the resolver, so a `Searcher`
  cannot be handed an unverified id list. Callers never pass raw ids to repositories.
- **Searcher** runs: embed query (`embed_query`) -> vector top-k with `WHERE user_id = :u AND document_id = ANY(:ids) AND version/index match`
  (exact search first) -> full-text top-k on `content_tsv` with the same filter -> **Reciprocal Rank Fusion** (`k=60`, configurable) -> dedupe
  and token-budgeted selection with source diversity -> minimum-evidence threshold. Scores of different systems are never added raw.
- **SourceReader** (Phase 4): `iter_chunks(scope, order="document")` yields chunks in document order with provenance (for summaries, quizzes,
  study guides) and `similar(scope, text, k)`. Both take a `VerifiedScope`, so Phase 4 gets isolation for free.
- Measure before indexing: build the evaluation set (generated fixtures + `testdata-private/`), record exact-search latency and
  Recall@K/MRR, and add an HNSW index only if needed; test recall **with the filters actually used** and compare `hnsw.iterative_scan`
  settings (pgvector 0.8 added iterative scans for filtered queries; the installed version is verified in M1 and the finding recorded).

## 8. RAG

Modes: `document_only | document_first | general`. Flow, inside the existing send-message path:

1. Auth, ownership, quotas, model resolve (unchanged). Resolve the conversation's scope with `ScopeResolver`.
2. `general` mode or `general` scope: skip retrieval, behave as Phase 2.
3. Build the retrieval query: current question; if it is short (below a configured length), prepend the previous user question (D-75). An LLM query rewrite is a later flag.
4. Retrieve, apply the evidence threshold.
5. `document_only` and nothing passes: store and return a **fixed insufficient-evidence reply without calling the LLM**; usage row records `request_kind = chat`, tokens NULL/0 as unavailable, no provider call.
6. Otherwise build the prompt: system prompt (versioned `rag_*` key) tells the model the material is untrusted data; reference material is wrapped in unambiguous markers with per-answer numbering `[1]..[n]`; any marker-like text inside a chunk is escaped before insertion.
7. Stream. SSE adds `message.citations` (the retrieved sources, before the first delta); `message.completed` carries the validated final text and citations and the client replaces streamed text if different.
8. Validation: parse `[n]` markers; any marker that does not map to a retrieved chunk is stripped; citation rows are written to `message_citations` from retrieved chunks only. Page/slide/title come from the database, never from model text.
9. Persist assistant message, citations and usage in the existing final transaction. Logs: ids, counts, scores summary, durations only; never document text, queries or prompts (D-51).

## 9. Phase 4 reuse

Flashcards, quizzes, study guides and summaries need: (a) a verified set of documents, (b) ordered chunks with provenance, (c) similarity lookup,
(d) citations. They get these from `ScopeResolver` and `SourceReader` and write their own tables; they do not touch `document_chunks`
directly. `message_citations` is not reused for generated study material (that will have its own provenance table), but the chunk id,
document version and index version already carried by every chunk are the stable references they need.

## 10. Security summary (details in `DECISIONS.md` and the Part C table)

Private bucket; generated keys; streamed downloads with attachment and nosniff; uploaded HTML never served; extraction only in a network-restricted
worker with time and memory limits; magic-byte validation; zip/image bomb limits; quotas; scanner interface (fail-closed when enabled); retrieval
always filtered by user before content reaches a model; document text treated as untrusted in prompts; model-generated citations never
trusted; no document content in logs; account deletion removes documents and objects; export lists metadata only.
