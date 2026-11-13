# RESEARCHMIND AI
# COMPLETE END-TO-END DEVELOPMENT INSTRUCTIONS
## Phase 6: Learner Intelligence and Knowledge Graph
## Phase 7: Research Studio

---

# PART 1 — MASTER EXECUTION INSTRUCTIONS

## 1. Project Context

ResearchMind AI is an academic intelligence workspace designed to help students, independent learners, educators and researchers capture learning materials, understand concepts, generate study resources, assess their knowledge, retain information, identify learning gaps and conduct academic research.

The application already has a foundation consisting of:

- Phase 1: Application Foundation
- Phase 2: AI Foundation and LLM Integration
- Phase 3: Document Intelligence and RAG
- Phase 4: AI-Powered Study Generation
- Phase 5: Assessment, Retention and Revision Intelligence

The next development stages are:

- Phase 6: Learner Intelligence and Knowledge Graph
- Phase 7: Research Studio

The objective is to connect everything developed so far into a more intelligent and integrated academic workspace.

Do not treat Phase 6 or Phase 7 as standalone applications. They must extend the existing ResearchMind AI architecture and reuse existing infrastructure wherever possible.

## 2. Mandatory Initial Repository Assessment

Before modifying any code, inspect the complete existing project.

Read:

1. `CLAUDE.md`
2. All relevant project documentation.
3. Architecture and design decisions.
4. Existing implementation plans.
5. Phase 1–5 acceptance documents.
6. Database schema and Alembic migrations.
7. Backend API conventions.
8. Frontend component and design-system conventions.
9. AI provider abstraction and prompt infrastructure.
10. Document processing and RAG implementation.
11. Study generation implementation.
12. Assessment, FSRS, revision and analytics implementation.
13. Existing tests and CI configuration.

Inspect the actual implementation instead of relying exclusively on documentation.

### 2.1 Backend inspection

Identify:

- Existing SQLAlchemy models.
- Repository implementations.
- Service-layer architecture.
- API routers.
- Pydantic schemas.
- Authentication and session handling.
- Workspace, subject, folder and chapter relationships.
- Document, document-version, chunk and embedding structures.
- AI provider interfaces.
- Prompt management and model selection.
- Celery tasks and worker configuration.
- Existing recommendation infrastructure.
- Quiz attempts and question-level results.
- Flashcard review events and FSRS state.
- Analytics and progress endpoints.
- Alembic migration conventions.

### 2.2 Frontend inspection

Identify:

- Application routing and layouts.
- Dashboard architecture.
- Existing navigation.
- Workspace and subject pages.
- Document viewer and source citation components.
- AI Tutor interface.
- Study Material Library.
- Quiz and assessment interface.
- Revision Centre.
- Progress and analytics pages.
- Shared charts, tables, dialogs and forms.
- Loading, empty, error and success states.
- Mobile-responsive design patterns.

### 2.3 Assessment output

Before implementation, create:

`docs/PHASE6_7_REPOSITORY_ASSESSMENT.md`

Include:

- Existing architecture.
- Existing tables and relationships.
- Existing API endpoints.
- Reusable services.
- Reusable frontend components.
- Existing AI infrastructure.
- Existing task and worker infrastructure.
- Missing functionality.
- Potential conflicts.
- Required schema changes.
- Proposed migrations.
- Dependency relationships.
- Recommended implementation sequence.

Do not create duplicate versions of functionality that already exists.

If a required capability already exists, extend it rather than rebuilding it.

If documentation and implementation disagree, report the discrepancy and base implementation decisions on the actual code.

---

# PART 2 — GLOBAL ARCHITECTURE AND DEVELOPMENT RULES

## 3. Existing Technology Stack

Preserve the existing stack.

### Frontend

- Next.js
- React
- TypeScript
- Tailwind CSS
- shadcn/ui

### Backend

- Python
- FastAPI
- SQLAlchemy
- Alembic
- Pydantic

### Infrastructure

- PostgreSQL
- pgvector
- Redis
- Celery workers and Celery Beat
- S3-compatible object storage
- Docker Compose

### AI infrastructure

- Existing provider-independent LLM abstraction.
- Existing model registry.
- Existing prompt management.
- Existing token and usage tracking.
- Existing document retrieval and RAG services.

Do not introduce new infrastructure simply because a feature could use it.

For example, PostgreSQL should remain the initial knowledge graph database. Do not introduce Neo4j unless the repository assessment demonstrates a concrete requirement that PostgreSQL cannot reasonably satisfy.

## 4. Mandatory Backend Architecture

Follow the existing application layering:

`API Route → Service → Repository → Database Model`

Rules:

- Routes handle HTTP concerns only.
- Services contain business logic.
- Repositories contain database queries.
- SQL must not be written directly inside route handlers.
- Business logic must not be placed inside frontend components.
- Use Pydantic schemas for request and response validation.
- Use Alembic for every database schema change.
- Reuse shared utilities and infrastructure.
- Follow existing naming and folder conventions.

## 5. API Conventions

All endpoints must follow:

`/api/v1/...`

Preserve the existing response envelope:

Success:

`{ "success": true, "data": {} }`

Error:

`{ "success": false, "error": {} }`

Use consistent pagination, filtering, sorting, validation and error handling.

Generate or update frontend TypeScript API types from the backend OpenAPI specification according to the existing project process.

## 6. Security Requirements

These requirements apply to every Phase 6 and Phase 7 feature.

### Authentication and ownership

- Require authentication for protected endpoints.
- Scope every query to the authenticated user.
- Enforce workspace ownership and membership.
- Validate ownership of every related object.
- Do not trust user IDs supplied by the frontend.
- Return 404 for inaccessible resources rather than revealing their existence through 403 responses, following the existing convention.

### AI security

- Treat all model-generated output as untrusted.
- Validate structured AI output against Pydantic schemas.
- Never let an LLM decide authorization or retrieval ownership.
- Never expose API keys or provider credentials to the frontend.
- Never allow a model-generated relationship to bypass application validation.
- Protect document and paper processing against prompt injection.
- Do not log complete private conversations or sensitive document contents.

### Data integrity

- Preserve document and evidence provenance.
- Prevent duplicate processing.
- Use idempotency for retryable operations.
- Maintain audit history for important user changes.
- Make destructive actions explicit.
- Support deletion of derived records when their source is deleted, according to the existing retention policy.

---

