# PART 3 — PHASE 6
# LEARNER INTELLIGENCE AND KNOWLEDGE GRAPH

## 7. Phase 6 Objective

Develop an intelligent academic knowledge and learner-understanding system.

The application must understand two different things:

1. What academic knowledge exists in the user's resources.
2. How well the user has demonstrated understanding of that knowledge.

These must remain separate.

For example:

A PDF might contain an explanation of neural networks. The application can identify neural networks as an academic concept and connect them to backpropagation, activation functions and deep learning.

However, the existence of this information in the PDF does not mean the user understands it.

The learner intelligence system must determine understanding using actual evidence from assessments, flashcards, revision activity and other learning interactions.

The final result should be a connected system that can answer:

- What concepts exist in my learning materials?
- How are these concepts connected?
- What should I learn before understanding this concept?
- Which concepts do I understand well?
- Which concepts am I struggling with?
- What misconceptions do I repeatedly demonstrate?
- What should I study next?
- Why is the application recommending a particular topic?

## 8. Phase 6 Architecture

Build Phase 6 in the following order:

1. Academic knowledge extraction.
2. Knowledge graph database.
3. Knowledge graph services and APIs.
4. Knowledge graph user interface.
5. Learner evidence collection.
6. Learner mastery engine.
7. Misconception detection.
8. Personalised recommendation engine.
9. Learner Intelligence dashboard.
10. Integration with existing Progress and Revision features.
11. Testing, security and acceptance verification.

Do not skip this sequence.

---

# MILESTONE 6.1 — ACADEMIC KNOWLEDGE EXTRACTION

## 9. Objective

Extract meaningful academic knowledge from existing learning materials.

Use the existing Phase 3 document processing and Phase 4 study-generation infrastructure.

Do not create another document ingestion pipeline.

### 9.1 Supported source material

Use existing supported sources:

- PDF documents.
- DOCX files.
- PPTX files.
- Extracted text.
- Existing study materials.
- Document chunks.
- Subject and chapter content.

Use other formats only if already supported by the existing ingestion infrastructure.

### 9.2 Extract academic concepts

For each document or selected chapter, identify:

- Concepts.
- Topics.
- Subtopics.
- Definitions.
- Technical terms.
- Algorithms.
- Methods.
- Formulas.
- Models.
- Theories.
- Principles.
- Important entities.
- Examples.
- Applications.

Each extracted concept should contain:

- Concept name.
- Normalised concept name.
- Description.
- Definition.
- Concept type.
- Subject.
- Chapter, where applicable.
- Difficulty estimate, if supported.
- Aliases.
- Supporting source references.
- Extraction confidence.

### 9.3 Extract concept relationships

Identify meaningful relationships between concepts.

Support relationship types such as:

| Relationship | Meaning |
|---|---|
| IS_A | One concept is a type of another |
| PART_OF | A concept belongs to another concept |
| PREREQUISITE_OF | One concept should be understood first |
| DEPENDS_ON | One concept depends on another |
| RELATED_TO | Concepts are related |
| CONTRASTS_WITH | Concepts differ or oppose each other |
| USES | One concept uses another |
| APPLIED_IN | A concept is applied in another domain |
| EXAMPLE_OF | One concept is an example of another |

Every relationship must have supporting evidence.

Do not create relationships merely because two concepts appear in the same document.

### 9.4 Structured AI extraction

Use the existing provider-independent AI service.

Require structured JSON output validated through Pydantic.

Example concept:

```json
{
  "name": "Backpropagation",
  "normalised_name": "backpropagation",
  "type": "algorithm",
  "description": "An algorithm used to calculate gradients in neural networks.",
  "definition": "Backpropagation calculates the gradient of the loss with respect to model parameters.",
  "aliases": ["Backward propagation"],
  "confidence": 0.94,
  "evidence": [
    {
      "document_id": "document-id",
      "document_version_id": "version-id",
      "chunk_id": "chunk-id",
      "page_number": 12,
      "supporting_text": "The extracted supporting passage."
    }
  ]
}
```

The example is illustrative. Generate actual identifiers and evidence from the database.

### 9.5 Extraction rules

- Every concept must have at least one valid source reference.
- Every relationship must have supporting evidence.
- Do not invent definitions absent from the source.
- Distinguish explicitly stated facts from inferred relationships.
- Record confidence.
- Allow users to correct extracted information.
- Do not silently overwrite user-edited concepts.
- Preserve extraction version and model information.

### 9.6 Duplicate detection

Implement concept matching using:

1. Normalised names.
2. Aliases.
3. Subject context.
4. Existing concept descriptions.
5. Semantic similarity as a candidate-generation mechanism.

Do not merge concepts solely because embeddings are similar.

When two concepts might refer to the same thing, create a reviewable duplicate candidate.

Allow the user to:

- Keep both concepts.
- Merge them.
- Mark them as related.
- Ignore the suggestion.

### 9.7 Extraction processing

Use Celery for background processing.

Suggested flow:

`Document → Existing extraction → Chunk retrieval → Concept extraction → Relationship extraction → Validation → Duplicate resolution → Graph persistence`

Requirements:

- Idempotent tasks.
- Retry-safe processing.
- User and workspace ownership.
- Processing status.
- Error reporting.
- Incremental reprocessing.
- No duplicate concepts on retries.

### 9.8 Acceptance criteria

- Concepts can be extracted from existing processed documents.
- Relationships are extracted and validated.
- Every extracted item has provenance.
- Duplicate candidates can be reviewed.
- Reprocessing does not create uncontrolled duplicates.
- Existing Phase 3 processing remains functional.

---

# MILESTONE 6.2 — KNOWLEDGE GRAPH DATABASE

## 10. Objective

Create a persistent graph of academic concepts and their relationships.

Initially implement the graph using PostgreSQL relational tables.

Do not introduce a separate graph database unless justified by measured limitations.

### 10.1 `knowledge_nodes`

Create a table representing academic concepts.

Suggested fields:

- id
- user_id
- workspace_id
- subject_id
- name
- normalised_name
- description
- definition
- node_type
- difficulty
- metadata
- created_at
- updated_at
- archived_at

Use existing UUID and timestamp conventions.

### 10.2 `knowledge_edges`

Create a table representing relationships.

Suggested fields:

- id
- user_id
- workspace_id
- source_node_id
- target_node_id
- relationship_type
- description
- confidence
- created_at
- updated_at

Requirements:

- Source and target nodes must be valid.
- Prevent self-referential relationships unless explicitly supported.
- Validate relationship types.
- Enforce ownership consistency.
- Add appropriate indexes.
- Avoid duplicate equivalent relationships.

### 10.3 `knowledge_evidence`

Store the supporting evidence for nodes and edges.

Suggested fields:

- id
- user_id
- knowledge_node_id
- knowledge_edge_id, nullable
- source_type
- source_id
- source_version_id
- source_chunk_id
- page_number
- slide_number
- supporting_text
- evidence_type
- extraction_method
- confidence
- created_at

Evidence should point back to the actual source material.

### 10.4 `knowledge_extraction_jobs`

Track extraction jobs.

Suggested fields:

- id
- user_id
- workspace_id
- source_document_id
- status
- progress
- extraction_version
- model_identifier
- error_message
- started_at
- completed_at
- created_at

Follow the existing job-tracking conventions where available.

### 10.5 Additional optional tables

Introduce these only when they solve a concrete requirement:

- `knowledge_node_aliases`
- `knowledge_merge_history`
- `knowledge_graph_versions`
- `knowledge_extraction_candidates`

### 10.6 Database constraints

Implement:

- Foreign keys.
- Ownership validation.
- Appropriate uniqueness constraints.
- Indexes on common search and traversal fields.
- Soft deletion or archival where consistent with the application.
- Migration rollback support.

### 10.7 Acceptance criteria

- Database migrations run successfully.
- Nodes, edges and evidence persist correctly.
- Invalid cross-user relationships are rejected.
- Duplicate edges are prevented.
- Existing database functionality remains intact.

---

# MILESTONE 6.3 — KNOWLEDGE GRAPH SERVICES AND APIs

## 11. Backend Services

Create services following the existing architecture.

Suggested services:

- `KnowledgeExtractionService`
- `KnowledgeGraphService`
- `KnowledgeNodeService`
- `KnowledgeRelationshipService`
- `KnowledgeEvidenceService`
- `KnowledgeMergeService`

Create repositories for database access.

Do not put graph traversal SQL in route handlers.

### 11.1 Required operations

Implement:

- Create a concept.
- Retrieve a concept.
- Update a concept.
- Archive a concept.
- Delete a concept where allowed.
- Search concepts.
- List concepts by subject.
- Retrieve related concepts.
- Retrieve prerequisites.
- Retrieve dependent concepts.
- Retrieve supporting evidence.
- Create relationships.
- Update relationships.
- Delete relationships.
- Merge duplicate concepts.
- Expand a graph around a selected concept.

### 11.2 Suggested APIs

Graph:

- `GET /api/v1/knowledge/graph`
- `GET /api/v1/knowledge/graph/overview`
- `GET /api/v1/knowledge/graph/expand`

Nodes:

- `GET /api/v1/knowledge/nodes`
- `POST /api/v1/knowledge/nodes`
- `GET /api/v1/knowledge/nodes/{node_id}`
- `PATCH /api/v1/knowledge/nodes/{node_id}`
- `DELETE /api/v1/knowledge/nodes/{node_id}`

Relationships:

- `POST /api/v1/knowledge/relationships`
- `PATCH /api/v1/knowledge/relationships/{relationship_id}`
- `DELETE /api/v1/knowledge/relationships/{relationship_id}`

Evidence:

- `GET /api/v1/knowledge/nodes/{node_id}/evidence`

Extraction:

- `POST /api/v1/knowledge/extract`
- `GET /api/v1/knowledge/extract/{job_id}`

Merge:

- `POST /api/v1/knowledge/nodes/merge`

Use the actual project naming conventions and avoid duplicating existing routes.

### 11.3 Graph traversal

Support:

- Direct neighbours.
- Prerequisites.
- Dependents.
- Related concepts.
- Concepts within a subject.
- Concepts within a workspace.
- Bounded-depth expansion.

Prevent uncontrolled graph traversal.

Implement pagination or node limits for large graphs.

### 11.4 Acceptance criteria

All graph operations must:

- Enforce authentication.
- Enforce ownership.
- Validate references.
- Return consistent response envelopes.
- Handle missing or archived records.
- Be covered by backend tests.

---

# MILESTONE 6.4 — KNOWLEDGE GRAPH FRONTEND

## 12. Objective

Create an interactive Knowledge Graph experience.

It should help users visually explore the academic concepts in their learning materials.

### 12.1 Main navigation

Add a Knowledge Graph entry in the existing application navigation.

Avoid restructuring the entire navigation if an appropriate location already exists.

### 12.2 Knowledge Graph page

Include:

- Graph visualisation.
- Search.
- Subject filter.
- Workspace filter.
- Relationship filters.
- Node-type filters.
- Expand and collapse.
- Zoom.
- Pan.
- Reset view.
- Node selection.
- Loading states.
- Empty states.
- Error states.

Use an existing graph visualisation library if available.

If introducing a library, assess bundle size, maintenance, accessibility and compatibility first.

### 12.3 Node detail panel

When a user selects a concept, show:

- Concept name.
- Description.
- Definition.
- Subject.
- Related concepts.
- Prerequisites.
- Dependent concepts.
- Difficulty.
- Supporting documents.
- Page or slide references.
- Evidence passages.
- Learner mastery status, when available.

Allow authorised editing.

### 12.4 Evidence navigation

When the user clicks supporting evidence:

- Open the source document.
- Navigate to the relevant page, slide or extracted passage.
- Highlight the relevant evidence where supported.

### 12.5 Graph performance

Do not load an entire large graph by default.

Use:

- Initial bounded graph.
- Progressive expansion.
- Search-driven loading.
- Subject filtering.
- Server-side traversal limits.

### 12.6 Acceptance criteria

- Users can explore their graph.
- Node selection shows correct details.
- Relationships are visually understandable.
- Source evidence opens correctly.
- Graph filters work.
- Large graphs do not freeze the interface.
- Mobile layouts remain usable.

---

# MILESTONE 6.5 — LEARNER EVIDENCE COLLECTION

## 13. Objective

Create the evidence infrastructure that connects actual learner activity to academic concepts.

This is one of the most important parts of Phase 6.

The system must not confuse content coverage with demonstrated mastery.

### 13.1 Evidence sources

Integrate evidence from Phase 5.

Use:

1. Quiz attempts.
2. Individual question results.
3. Question difficulty.
4. Topic-level assessment results.
5. Descriptive answer feedback.
6. Flashcard ratings.
7. FSRS review history.
8. Revision activity.
9. Repeated mistakes.
10. Learning activity where meaningful.

Future integrations can include:

- AI Tutor interactions.
- AI Viva results.
- Coding assessments.
- Interactive simulations.

Do not fabricate evidence for features that do not exist.

### 13.2 Concept mapping

Map existing assessment topics to knowledge graph nodes.

Use:

- Existing subject and chapter associations.
- Existing topic metadata.
- Question tags.
- Explicit concept references.
- Reviewed mappings where automatic matching is uncertain.

Do not map a question to a concept based only on a weak semantic similarity score.

Allow ambiguous mappings to remain unresolved until reviewed.

### 13.3 `learner_evidence`

Create a canonical learner evidence table.

Suggested fields:

- id
- user_id
- workspace_id
- knowledge_node_id
- source_type
- source_id
- source_event_id
- evidence_value
- evidence_metadata
- occurred_at
- created_at

Use appropriate data types and constraints.

### 13.4 `learner_concept_states`

Store the current learner state for each concept.

Suggested fields:

- id
- user_id
- workspace_id
- knowledge_node_id
- mastery_estimate
- confidence
- evidence_count
- state
- last_evidence_at
- next_review_at
- calculation_version
- explanation
- updated_at

Suggested states:

- NOT_ASSESSED
- INSUFFICIENT_EVIDENCE
- LEARNING
- DEVELOPING
- PROFICIENT
- STRONG

The exact thresholds must be defined and documented based on the implemented scoring model.

### 13.5 Evidence deduplication

Avoid counting the same event more than once.

For example:

- A quiz attempt and its analytics aggregate must not become two separate pieces of evidence.
- A flashcard rating and its revision analytics summary must not be counted twice.

Use a canonical source event identity.

Implement idempotent ingestion.

### 13.6 Evidence quality

Store enough information to explain each learner-state calculation.

Where applicable, retain:

- Assessment score.
- Correctness.
- Difficulty.
- Question type.
- Attempt time.
- Previous mistakes.
- Flashcard rating.
- Review interval.
- Lapse history.
- Source event.

Do not store unnecessary sensitive content.

### 13.7 Acceptance criteria

- Phase 5 assessment events can be ingested.
- Flashcard review events can be ingested.
- Evidence maps to the correct user and concept.
- Duplicate events are prevented.
- Unmapped evidence remains available for review or future mapping.
- Learner evidence can be traced to its original event.

---

# MILESTONE 6.6 — LEARNER MASTERY ENGINE

## 14. Objective

Build the initial learner intelligence engine.

It must estimate the user's demonstrated understanding of each academic concept.

Start with an explainable, rule-based model.

Do not introduce an opaque machine-learning model before sufficient labelled data exists.

### 14.1 Mastery inputs

Consider:

- Correctness.
- Incorrect attempts.
- Question difficulty.
- Recency.
- Repeated performance.
- Descriptive feedback.
- Flashcard recall ratings.
- FSRS review history.
- Lapses.
- Evidence quantity.
- Evidence reliability.

### 14.2 Initial scoring approach

Implement a versioned calculation method.

Possible factors include:

- Recent performance.
- Historical performance.
- Difficulty-adjusted performance.
- Repeated errors.
- Successful recall.
- Evidence confidence.

Do not choose arbitrary weights without documenting the rationale.

Use a central, testable calculation service.

Keep the calculation deterministic and reproducible for the same evidence snapshot.

### 14.3 Recency

Recent performance should influence the learner estimate.

However:

- Do not erase historical evidence.
- Do not treat a single recent failure as proof of complete loss of knowledge.
- Do not allow one easy question to create a strong mastery state.

### 14.4 Confidence and insufficient evidence

The system must distinguish:

- A learner who has demonstrated weak understanding.
- A learner who has not yet been assessed.
- A learner with insufficient evidence.
- A learner with consistently strong performance.

Never label an unassessed concept as weak.

### 14.5 Recalculation

Recalculate learner state when:

- New quiz evidence is added.
- A descriptive answer is graded.
- A flashcard review is recorded.
- Existing evidence is corrected or removed.
- A concept mapping changes.
- The mastery calculation version changes.

Use Celery for expensive or bulk recalculation.

### 14.6 Explainability

Every learner state should have an explanation.

Example:

"Your understanding of Backpropagation is developing because you answered two recent questions incorrectly, although your earlier assessment results were stronger."

The explanation must be generated from actual evidence.

Do not fabricate assessment history.

### 14.7 Acceptance criteria

- Mastery is calculated from real evidence.
- The calculation is versioned.
- Evidence is not double counted.
- Weak, unassessed and insufficient-evidence states are distinct.
- State changes are reproducible.
- Every result can be explained.

---

# MILESTONE 6.7 — MISCONCEPTION DETECTION

## 15. Objective

Identify recurring misunderstandings rather than merely identifying incorrect answers.

For example:

A learner might repeatedly confuse supervised and unsupervised learning.

The system should identify the underlying misunderstanding and suggest a targeted correction.

### 15.1 Evidence used

Use:

- Question.
- Expected answer.
- Learner answer.
- Correctness.
- Topic.
- Explanation.
- Previous mistakes.
- Related knowledge graph concepts.

### 15.2 Structured output

Require a structured response such as:

```json
{
  "concept_id": "concept-id",
  "misconception": "Confuses supervised and unsupervised learning.",
  "observed_evidence": [
    {
      "source_type": "quiz_answer",
      "source_id": "answer-id"
    }
  ],
  "related_concepts": [
    "concept-id-1"
  ],
  "explanation": "The learner appears to misunderstand the role of labelled data.",
  "recommended_action": "Review the comparison between supervised and unsupervised learning.",
  "confidence": 0.88
}
```

### 15.3 Detection safeguards

- Do not infer a misconception from one ambiguous answer.
- Require sufficient supporting evidence.
- Distinguish knowledge gaps from careless mistakes.
- Preserve the supporting assessment evidence.
- Record model and prompt versions.
- Allow the user to dismiss a misconception.
- Allow corrections where the system is wrong.
- Do not present low-confidence inferences as facts.

### 15.4 Database

Create a `learner_misconceptions` table if no suitable existing structure exists.

Suggested fields:

- id
- user_id
- workspace_id
- knowledge_node_id
- description
- explanation
- confidence
- status
- evidence_count
- detection_version
- created_at
- updated_at
- dismissed_at

Create a separate evidence association if multiple events need to be linked.

### 15.5 Acceptance criteria

- Misconceptions are grounded in actual learner responses.
- Evidence is retrievable.
- Insufficient evidence does not trigger false conclusions.
- Users can dismiss or correct results.
- Detection is retry-safe.

---

# MILESTONE 6.8 — PERSONALISED RECOMMENDATION ENGINE

## 16. Objective

Extend the recommendation infrastructure from Phase 5.

Do not build a separate recommendation system that duplicates existing Phase 5 functionality.

Recommendations should now use knowledge graph relationships and learner evidence.

### 16.1 Recommendation types

Support:

- Revise a weak concept.
- Study a prerequisite.
- Practise a difficult topic.
- Reattempt a question type.
- Review a misconception.
- Revisit a chapter.
- Study a related concept.
- Review a concept due for revision.
- Complete an unassessed important concept.

### 16.2 Recommendation inputs

Consider:

- Mastery estimate.
- Evidence confidence.
- Repeated mistakes.
- Misconceptions.
- FSRS due dates.
- Prerequisite relationships.
- Subject importance.
- User goals.
- Exam deadlines, where available.

### 16.3 Recommendation ranking

Implement a transparent ranking strategy.

A recommendation should have:

- Recommendation type.
- Target concept or resource.
- Priority.
- Explanation.
- Supporting evidence.
- Suggested action.
- Created time.
- Completion status.

Avoid opaque recommendation scores without documented meaning.

### 16.4 Recommendation examples

Example:

"Review Activation Functions before moving on to Backpropagation because it is a prerequisite and your recent assessment results indicate that you need more practice."

Example:

"Revise Database Normalisation because you have an upcoming revision item and your recent quiz performance was below your previous level."

Only show these recommendations when the supporting conditions actually exist.

### 16.5 Integration

Extend the existing Phase 5 recommendation model and endpoints where possible.

Add recommendation completion and dismissal behaviour without breaking existing clients.

### 16.6 Acceptance criteria

- Recommendations are grounded in learner evidence.
- Graph relationships influence recommendations.
- Existing Phase 5 recommendations remain functional.
- Users can complete or dismiss recommendations.
- Reasons are visible.
- Ranking is testable.

---

# MILESTONE 6.9 — LEARNER INTELLIGENCE DASHBOARD

## 17. Objective

Create a unified view of the learner's academic understanding.

This should complement, not duplicate, the existing Progress page.

### 17.1 Overview

Show:

- Concepts tracked.
- Concepts assessed.
- Concepts with sufficient evidence.
- Strong concepts.
- Developing concepts.
- Weak concepts.
- Unassessed concepts.
- Misconceptions.
- Recommended actions.

Do not present all concepts as assessed.

### 17.2 Subject intelligence

For each subject, show:

- Total concepts.
- Assessed concepts.
- Mastery distribution.
- Weak concepts.
- Strong concepts.
- Unassessed concepts.
- Important prerequisites.
- Recommended next steps.

### 17.3 Concept intelligence

When opening a concept, show:

- Definition.
- Description.
- Knowledge graph relationships.
- Prerequisites.
- Supporting materials.
- Assessment history.
- Flashcard history where available.
- Mastery estimate.
- Confidence.
- Misconceptions.
- Recommended actions.

### 17.4 Learning gaps

Create a dedicated view of:

- Weak concepts.
- Missing prerequisites.
- Repeated misconceptions.
- Unassessed important concepts.
- Topics needing revision.

Clearly distinguish actual demonstrated weakness from lack of evidence.

### 17.5 Progress integration

Integrate the new learner intelligence features with existing Phase 5 Progress.

Do not create two competing analytics dashboards.

The existing Progress page should continue to show historical activity and assessment trends.

Learner Intelligence should focus on conceptual understanding, mastery, knowledge gaps and recommended learning actions.

### 17.6 Acceptance criteria

- Dashboard values match backend data.
- Subject and concept filters work.
- No fake mastery data is displayed.
- Empty states explain what is missing.
- Recommendations navigate to the correct resource or activity.

---

# MILESTONE 6.10 — PHASE 6 TESTING AND ACCEPTANCE

## 18. Backend tests

Cover:

- Concept extraction.
- Structured output validation.
- Relationship extraction.
- Provenance.
- Duplicate detection.
- Concept merging.
- Graph traversal.
- Graph ownership.
- Invalid relationships.
- Evidence ingestion.
- Event deduplication.
- Mastery calculation.
- Insufficient evidence.
- Mastery recalculation.
- Misconception detection.
- Recommendation generation.
- Recommendation completion.
- Recommendation dismissal.

## 19. Frontend tests

Cover:

- Knowledge Graph loading.
- Search and filters.
- Node selection.
- Relationship display.
- Evidence navigation.
- Concept editing.
- Learner dashboard.
- Subject intelligence.
- Concept details.
- Misconception display.
- Recommendation actions.
- Loading, error and empty states.
- Mobile responsiveness.

## 20. Integration tests

Verify the complete flow:

1. Upload or use an existing processed learning document.
2. Extract concepts.
3. Extract relationships.
4. Store graph nodes and edges.
5. Display the graph.
6. Generate a quiz through the existing Phase 4 system.
7. Complete the quiz through Phase 5.
8. Ingest assessment evidence.
9. Map evidence to concepts.
10. Recalculate mastery.
11. Detect supported misconceptions.
12. Generate recommendations.
13. Display the results in Learner Intelligence.

## 21. Phase 6 completion gate

Phase 6 is complete only when:

- Knowledge graph extraction works.
- Graph data persists correctly.
- Graph relationships have provenance.
- Graph UI is functional.
- Phase 5 assessment evidence is integrated.
- Flashcard review evidence is integrated.
- Mastery calculations are explainable.
- Misconceptions are evidence-based.
- Recommendations use graph and learner intelligence.
- Dashboard data is correct.
- Ownership and security tests pass.
- Existing Phase 1–5 functionality remains intact.
- All required migrations and tests pass.

Create:

`docs/PHASE6_ACCEPTANCE.md`

Include:

- Completed milestones.
- Implemented features.
- Database changes.
- APIs.
- Frontend pages.
- Test results.
- Security checks.
- Known limitations.
- Deferred functionality.
- Final acceptance status.

**Do not begin Phase 7 until this completion gate has been passed.**

---

