# PART 5 — DATABASE AND INTEGRATION GUIDELINES

## 37. Database design overview

The following are proposed logical entities, not an instruction to create duplicates if equivalent tables already exist.

### Phase 6

- `knowledge_nodes`
- `knowledge_edges`
- `knowledge_evidence`
- `knowledge_extraction_jobs`
- `learner_evidence`
- `learner_concept_states`
- `learner_misconceptions`
- `learner_misconception_evidence`
- `learner_recommendations`, only if existing Phase 5 recommendation storage cannot be extended.

### Phase 7

- `research_projects`
- `research_papers`
- `research_paper_extractions`
- `research_evidence`
- `research_notes`
- `research_comparisons`
- `research_comparison_papers`
- `research_evidence_matrices`
- `research_evidence_matrix_columns`
- `research_evidence_matrix_entries`
- `research_gaps`
- `research_gap_evidence`
- `research_contradictions`
- `research_contradiction_evidence`
- `research_citations`
- `research_drafts`
- `research_draft_versions`
- `research_jobs`

Review every proposed entity against the existing schema before creating it.

## 38. Database migration rules

- Use Alembic.
- Keep migrations small and understandable.
- Add indexes for frequently queried columns.
- Add appropriate foreign keys.
- Preserve user ownership.
- Avoid unnecessary JSONB structures.
- Test migration upgrade.
- Test migration downgrade where supported.
- Test against a clean database.
- Test against a database containing existing Phase 1–5 data.

Do not modify old migrations to accommodate new functionality.

## 39. Background processing

Use the existing Celery infrastructure.

Suggested Phase 6 tasks:

- Extract concepts.
- Extract relationships.
- Resolve duplicate candidates.
- Recalculate learner mastery.
- Detect misconceptions.
- Generate recommendations.
- Rebuild graph summaries.

Suggested Phase 7 tasks:

- Process research paper.
- Extract paper metadata.
- Analyse research paper.
- Generate literature comparison.
- Build evidence matrix.
- Explore research gaps.
- Detect contradictions.
- Generate research writing sections.
- Validate research claims.

All tasks must be:

- Idempotent.
- Retry-safe.
- Ownership-aware.
- Observable.
- Versioned where appropriate.
- Capable of reporting failure.

Do not run expensive document or paper extraction inside normal HTTP request handlers.

---

# PART 6 — FRONTEND INTEGRATION

## 40. Application navigation

Extend the existing navigation with:

**Knowledge and Learning**
- Knowledge Graph.
- Learner Intelligence.

**Research**
- Research Studio.

Do not make the application navigation unnecessarily crowded.

Use the existing layout and design system.

## 41. Phase 6 pages

Suggested routes, adapted to existing conventions:

- `/knowledge`
- `/knowledge/graph`
- `/knowledge/concepts/[id]`
- `/learner`
- `/learner/subjects/[id]`
- `/learner/concepts/[id]`
- `/learner/misconceptions`

## 42. Phase 7 pages

Suggested routes:

- `/research`
- `/research/projects/[id]`
- `/research/projects/[id]/papers`
- `/research/papers/[id]`
- `/research/projects/[id]/comparison`
- `/research/projects/[id]/matrix`
- `/research/projects/[id]/gaps`
- `/research/projects/[id]/contradictions`
- `/research/projects/[id]/citations`
- `/research/projects/[id]/writing`

Use the actual routing conventions already present in the application.

## 43. UI quality requirements

Every page must have:

- Loading state.
- Empty state.
- Error state.
- Success feedback.
- Responsive layout.
- Accessible controls.
- Correct keyboard interaction.
- Consistent spacing and typography.
- Clear hierarchy.
- Functional buttons and actions.

Do not implement static mock screens as completed features.

Do not display fabricated data as actual user data.

Use mock fixtures only inside tests or clearly labelled development previews.

---

# PART 7 — IMPLEMENTATION ORDER AND EXECUTION CONTROL

## 44. Exact execution order

The coding agent must execute the following sequence.

### Stage A — Repository assessment

1. Read project instructions.
2. Inspect the repository.
3. Verify Phase 1–5 implementation.
4. Map existing tables, routes and services.
5. Identify reusable infrastructure.
6. Produce the repository assessment.
7. Identify dependencies and risks.

Do not start implementation until this assessment is complete.

### Stage B — Phase 6 implementation

**6.1:** Academic knowledge extraction.

**6.2:** Knowledge graph schema and migrations.

**6.3:** Graph services, repositories and APIs.

**6.4:** Knowledge Graph frontend.

**6.5:** Learner evidence collection.

**6.6:** Learner mastery engine.

**6.7:** Misconception detection.

**6.8:** Personalised recommendations.

**6.9:** Learner Intelligence dashboard.

**6.10:** Full integration testing and acceptance.

At each milestone:

1. Inspect existing code.
2. Implement backend changes.
3. Add migrations.
4. Implement frontend changes.
5. Add tests.
6. Run tests.
7. Fix regressions.
8. Update documentation.
9. Record completion.

Do not jump to a later milestone when the current one is incomplete.

### Stage C — Phase 6 final verification

Run:

- Backend tests.
- Frontend unit tests.
- Type checks.
- Lint.
- Migration checks.
- Integration tests.
- Playwright tests.
- Security and ownership tests.
- Existing Phase 1–5 regression tests.

Create the Phase 6 acceptance report.

Only proceed after Phase 6 passes its acceptance gate.

### Stage D — Phase 7 implementation

**7.1:** Research project foundation.

**7.2:** Research paper library.

**7.3:** Academic paper intelligence.

**7.4:** Literature comparison engine.

**7.5:** Research evidence matrix.

**7.6:** Research gap exploration.

**7.7:** Contradiction detection.

**7.8:** Citation management.

**7.9:** Research Writing Studio.

**7.10:** Knowledge graph integration.

**7.11:** Research Studio dashboard.

**7.12:** Full integration testing and acceptance.

Follow the same milestone-based development process.

### Stage E — Phase 7 final verification

Run all:

- Backend tests.
- Frontend tests.
- Type checks.
- Lint.
- Migration checks.
- Background task tests.
- AI structured-output tests.
- Provenance tests.
- Ownership and security tests.
- End-to-end tests.
- Phase 1–6 regression tests.

Create the Phase 7 acceptance report.

---

# PART 8 — TESTING AND QUALITY GATES

## 45. Mandatory testing rules

Do not consider implementation complete merely because the code compiles.

For every milestone:

- Write unit tests.
- Write integration tests where appropriate.
- Test invalid input.
- Test unauthorised access.
- Test cross-user access.
- Test duplicate processing.
- Test retries.
- Test missing data.
- Test model failures.
- Test empty states.
- Test frontend loading and error states.

Use existing test frameworks and conventions.

Do not weaken or delete existing tests to make new code pass.

Do not replace meaningful assertions with superficial status-code checks.

## 46. AI evaluation

For AI extraction and generation:

- Maintain representative evaluation fixtures.
- Test structured output validation.
- Test malformed model responses.
- Test hallucinated evidence references.
- Test prompt injection in source documents.
- Test missing source information.
- Test model timeouts.
- Test provider failures.
- Test retry behaviour.
- Track prompt and model versions.

For research claims, verify that cited evidence actually supports the claim.

For learner intelligence, verify that mastery and misconceptions are derived from actual learner events.

---

# PART 9 — PERFORMANCE AND RELIABILITY

## 47. Performance requirements

Avoid loading large datasets into the browser.

Implement:

- Pagination.
- Server-side filtering.
- Appropriate database indexes.
- Bounded graph traversal.
- Background processing.
- Efficient batch queries.
- Caching only where appropriate.
- Database query monitoring.

Avoid N+1 query patterns.

Do not use unbounded joins or graph expansion.

## 48. Reliability requirements

Handle:

- LLM provider unavailable.
- Model timeout.
- Malformed structured output.
- Redis unavailable.
- Worker failure.
- Object storage failure.
- Database transaction failure.
- Partial extraction.
- Duplicate task delivery.
- User cancellation where supported.

Show understandable error messages and allow safe retries.

Do not mark jobs as completed when processing has failed.

---

# PART 10 — DOCUMENTATION REQUIREMENTS

## 49. Update project documentation

Update existing documentation rather than creating competing documents.

Required documentation:

- `docs/PHASE6_7_REPOSITORY_ASSESSMENT.md`
- `docs/PHASE6_IMPLEMENTATION_PLAN.md`
- `docs/PHASE6_ACCEPTANCE.md`
- `docs/PHASE7_IMPLEMENTATION_PLAN.md`
- `docs/PHASE7_ACCEPTANCE.md`

Also update:

- `CLAUDE.md`, if project instructions need changes.
- Architecture decision records.
- Database documentation.
- API documentation.
- Developer setup instructions.
- Background worker documentation.
- Testing instructions.
- Task board.

Document important decisions, particularly:

- Why PostgreSQL is being used for the initial graph.
- How mastery is calculated.
- How evidence is deduplicated.
- How misconceptions are identified.
- How research gaps are qualified.
- How evidence provenance works.
- How paper metadata is verified.
- How AI-generated drafts preserve researcher edits.

---

# PART 11 — MANDATORY DEVELOPMENT REPORTING

## 50. Milestone completion report

After each milestone, provide a report containing:

### 1. Milestone

State the exact milestone completed.

### 2. Implementation

Explain what was implemented.

### 3. Files changed

List the important files created or modified.

### 4. Database

List:

- New tables.
- Modified tables.
- Migrations.
- Indexes.
- Constraints.

### 5. APIs

List new or modified endpoints.

### 6. Frontend

List:

- Pages.
- Components.
- Hooks.
- State changes.
- User interactions.

### 7. Background tasks

List tasks, retries and processing behaviour.

### 8. Testing

Report:

- Test command.
- Number passed.
- Number failed.
- Number skipped.
- Relevant integration results.

Never claim tests passed unless they were actually executed.

### 9. Security

Report ownership, validation and access-control verification.

### 10. Remaining work

List incomplete items, limitations and blockers.

### 11. Completion status

Use one of:

- COMPLETE.
- PARTIALLY COMPLETE.
- BLOCKED.
- NOT STARTED.

Do not mark a milestone complete when acceptance criteria are unmet.

---

# PART 12 — FINAL PRODUCT EXPECTATION

## 51. Expected Phase 6 result

After Phase 6, a user should be able to:

1. Upload academic materials.
2. Extract academic concepts.
3. Explore their interconnected knowledge graph.
4. Open evidence supporting each concept.
5. Take quizzes and review flashcards.
6. Have learning evidence mapped to concepts.
7. See estimated understanding and confidence.
8. Identify recurring misconceptions.
9. Discover missing prerequisites.
10. Receive explainable recommendations.
11. Understand what to study next.

The result must be an evidence-driven learner intelligence system, not a dashboard containing arbitrary mastery percentages.

## 52. Expected Phase 7 result

After Phase 7, a user should be able to:

1. Create a research project.
2. Add academic papers.
3. Extract structured information from papers.
4. Inspect methodology, datasets, results and limitations.
5. Compare multiple papers.
6. Build a literature evidence matrix.
7. Explore candidate research gaps.
8. Identify conflicting findings.
9. Manage academic citations.
10. Write research sections using source evidence.
11. Validate claims against selected papers.
12. Connect research papers to academic concepts.
13. Export research documents.

The result must be a usable research workspace, not a collection of disconnected AI tools.

---

# PART 13 — FINAL MASTER INSTRUCTION TO THE CODING AGENT

Execute Phase 6 and Phase 7 in the exact order defined in this document.

First, inspect the complete repository and produce the assessment document.

Then implement Phase 6 milestone by milestone.

Do not start Phase 7 until Phase 6 has passed its testing and acceptance requirements.

After Phase 6 is verified, implement Phase 7 milestone by milestone.

Follow the existing architecture, database conventions, API standards, security controls, frontend design system and AI provider abstraction.

Reuse Phase 1–5 infrastructure wherever possible.

Do not duplicate existing document processing, RAG, assessment, FSRS, analytics or recommendation functionality.

Do not introduce unnecessary infrastructure.

Do not create static mock implementations and describe them as completed functionality.

Do not fabricate academic knowledge, learner evidence, paper findings, citations or research gaps.

Every important AI-generated academic claim must be traceable to supporting evidence.

Every learner mastery estimate must be based on actual learner evidence.

Every recommendation must have a clear explanation.

Every destructive or researcher-editing operation must preserve data integrity and user control.

At every milestone, run the relevant tests, fix regressions, update documentation and provide the completion report.

**The priority is a complete, reliable and integrated implementation—not simply finishing the milestones quickly.**

Final development sequence:

`REPOSITORY AUDIT → PHASE 6 KNOWLEDGE GRAPH → PHASE 6 LEARNER INTELLIGENCE → PHASE 6 VERIFICATION → PHASE 7 RESEARCH FOUNDATION → PAPER INTELLIGENCE → LITERATURE ANALYSIS → RESEARCH GAPS → CITATIONS → WRITING STUDIO → GRAPH INTEGRATION → PHASE 7 VERIFICATION`

The final outcome should connect academic content, learner understanding and research into one continuous ResearchMind AI ecosystem.