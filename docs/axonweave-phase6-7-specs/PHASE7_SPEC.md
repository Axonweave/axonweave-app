# PART 4 — PHASE 7
# RESEARCH STUDIO

## 22. Phase 7 Objective

Build a complete research workspace that helps users manage academic research from paper collection to literature analysis, evidence comparison, research-gap exploration, citation management and research writing.

The Research Studio should not be another general-purpose chatbot.

It should be a structured research environment where papers, claims, evidence, comparisons, citations and drafts are connected.

It should answer questions such as:

- What is this paper trying to solve?
- What methodology does it use?
- What dataset and evaluation metrics are used?
- What are its main findings?
- What limitations does it report?
- How do several papers compare?
- Which findings support or contradict one another?
- What research gaps might exist in my selected collection?
- What evidence supports a particular research claim?
- How can I organise and write a literature review?
- Which concepts and methods connect to my existing knowledge graph?

### Critical research accuracy rule

The system must never fabricate:

- Paper metadata.
- Authors.
- Publication years.
- DOI identifiers.
- Datasets.
- Experimental results.
- Research findings.
- Citations.
- Research gaps.

Every extracted research claim must be connected to evidence.

A candidate research gap is not proof that no previous research exists.

---

# MILESTONE 7.1 — RESEARCH PROJECT FOUNDATION

## 23. Objective

Create a dedicated workspace for individual research projects.

### 23.1 Research project fields

Each project should support:

- Title.
- Description.
- Research domain.
- Research problem.
- Research objectives.
- Research questions.
- Keywords.
- Project status.
- Start date.
- Target completion date.
- Created date.
- Updated date.

### 23.2 Project structure

A research project should organise:

- Papers.
- Paper analyses.
- Research notes.
- Research questions.
- Evidence matrices.
- Literature comparisons.
- Research gaps.
- Contradictions.
- Citations.
- Drafts.
- Experiments.
- Datasets.
- Findings.

Use the existing workspace and subject model where appropriate.

Do not introduce duplicate folder or workspace functionality.

### 23.3 Database

Create `research_projects`.

Suggested fields:

- id
- user_id
- workspace_id, nullable where appropriate
- title
- description
- domain
- research_problem
- objectives
- research_questions
- keywords
- status
- start_date
- target_date
- created_at
- updated_at
- archived_at

Use JSONB for flexible structured fields only where appropriate. Prefer relational structures for data that needs filtering, relationships or independent lifecycle management.

### 23.4 APIs

- `GET /api/v1/research/projects`
- `POST /api/v1/research/projects`
- `GET /api/v1/research/projects/{project_id}`
- `PATCH /api/v1/research/projects/{project_id}`
- `DELETE /api/v1/research/projects/{project_id}`

### 23.5 Frontend

Create the Research Studio landing page.

Include:

- Research project cards.
- Project creation.
- Project status.
- Last updated.
- Number of papers.
- Research questions.
- Project overview.

### 23.6 Acceptance criteria

- Users can create and manage projects.
- Project ownership is enforced.
- Project data persists.
- Existing workspace behaviour remains unchanged.

---

# MILESTONE 7.2 — RESEARCH PAPER LIBRARY

## 24. Objective

Create a structured academic paper library.

### 24.1 Supported sources

Initially support:

- PDF uploads.
- Existing documents already stored in ResearchMind AI.
- Manually entered paper metadata.
- DOI entry.
- Metadata retrieved through supported scholarly APIs, where configured.

Potential future scholarly metadata providers:

- Crossref.
- OpenAlex.
- Semantic Scholar.

Use their documented APIs and respect their rate limits and terms.

Do not assume that metadata access means full-text download access.

### 24.2 Paper metadata

Extract or collect:

- Paper title.
- Authors.
- Publication year.
- Journal or conference.
- Abstract.
- DOI.
- Keywords.
- Publisher.
- Volume.
- Issue.
- Pages.
- Publication URL.
- Reference list, when available.

Allow manual correction.

Track metadata provenance:

- User supplied.
- Extracted from PDF.
- Retrieved from external metadata provider.
- Manually verified.

### 24.3 Database

Create `research_papers`.

Suggested fields:

- id
- user_id
- research_project_id
- document_id, nullable
- title
- abstract
- authors
- publication_year
- venue
- publisher
- doi
- url
- keywords
- volume
- issue
- pages
- metadata_source
- metadata_verified
- status
- created_at
- updated_at

Add appropriate uniqueness and indexing rules.

### 24.4 Duplicate detection

Use:

- DOI.
- Normalised title.
- Author information.
- Publication year.

Do not automatically merge papers solely because their titles are similar.

Allow users to review duplicate candidates.

### 24.5 Paper library UI

Include:

- List view.
- Search.
- Filters.
- Sort.
- Paper details.
- Upload PDF.
- Add DOI.
- Add metadata manually.
- Processing status.
- Analysis status.
- Duplicate review.

### 24.6 Acceptance criteria

- Users can add papers.
- PDF uploads reuse Phase 3 ingestion.
- Metadata is editable.
- Duplicate detection works.
- Paper ownership is enforced.
- External metadata failures do not break manual entry.

---

# MILESTONE 7.3 — ACADEMIC PAPER INTELLIGENCE

## 25. Objective

Extract structured academic information from each paper.

Reuse Phase 3 extraction, chunking, embeddings, storage and source retrieval.

Do not implement another independent PDF processing pipeline.

### 25.1 Extract the following information

**Research problem**

- What problem does the paper address?
- Why is it important?
- What existing limitation motivates the work?

**Research objectives**

- Main objective.
- Specific objectives.
- Research questions or hypotheses.

**Methodology**

- Research design.
- Proposed method.
- Model or algorithm.
- Architecture.
- Experimental approach.
- Implementation details.

**Dataset**

- Dataset name.
- Dataset source.
- Sample size.
- Population or domain.
- Data characteristics.
- Preprocessing.
- Train/validation/test split, where reported.

**Evaluation**

- Evaluation metrics.
- Baselines.
- Experimental setup.
- Validation method.

**Results**

- Main findings.
- Quantitative results.
- Reported improvements.
- Comparisons with baselines.

**Contributions**

- Main contributions.
- Novel methods.
- Proposed framework.
- Practical implications.

**Limitations**

- Limitations explicitly reported.
- Limitations suggested by the authors.
- Potential limitations inferred from the methodology, clearly labelled as AI analysis.

**Future work**

- Future research proposed by the authors.
- Further opportunities supported by the paper.

**References**

- Extracted references, where available.
- Verified bibliographic metadata where possible.

### 25.2 Evidence requirements

Every important extracted statement should have:

- Paper ID.
- Document ID.
- Document version.
- Chunk ID.
- Page number.
- Supporting text.
- Extraction type.
- Confidence.

For example:

```json
{
  "category": "methodology",
  "claim": "The study uses a Vision Transformer architecture.",
  "evidence": {
    "paper_id": "paper-id",
    "document_id": "document-id",
    "chunk_id": "chunk-id",
    "page_number": 5,
    "supporting_text": "Actual supporting passage from the paper."
  },
  "confidence": 0.95
}
```

This is an illustrative structure, not sample research data.

### 25.3 Missing information

If a paper does not report a dataset size, result or limitation, return:

"Not reported in the available paper."

Do not fill gaps with assumptions.

### 25.4 Structured schemas

Create validated Pydantic schemas for:

- Paper metadata.
- Research problem.
- Objectives.
- Methodology.
- Dataset.
- Evaluation.
- Results.
- Contributions.
- Limitations.
- Future work.
- References.
- Evidence.

Store extraction version and model identifier.

### 25.5 Database

Create:

`research_paper_extractions`

Suggested fields:

- id
- user_id
- research_paper_id
- extraction_version
- model_identifier
- status
- structured_result
- error_message
- created_at
- updated_at

Create a separate `research_evidence` table to store individual claims and their source references.

Suggested fields:

- id
- user_id
- research_project_id
- research_paper_id
- extraction_id
- claim_type
- claim_text
- document_id
- document_version_id
- chunk_id
- page_number
- supporting_text
- confidence
- evidence_origin
- created_at

### 25.6 Processing

Run extraction as a Celery background task.

Include:

- Queued.
- Processing.
- Completed.
- Failed.
- Retry.
- Reanalyse.
- Version history.

Do not overwrite researcher-edited notes.

### 25.7 Frontend paper analysis

Create a paper detail and analysis page.

Suggested tabs:

- Overview.
- Research Problem.
- Methodology.
- Dataset.
- Evaluation.
- Results.
- Contributions.
- Limitations.
- Future Work.
- References.
- Evidence.

Allow users to open the original paper at the cited page.

### 25.8 Acceptance criteria

- Structured paper analysis works.
- Every supported claim has provenance.
- Missing information is represented honestly.
- Reanalysis is versioned.
- AI output is validated.
- Users can edit their own notes without losing extraction history.

---

# MILESTONE 7.4 — LITERATURE COMPARISON ENGINE

## 26. Objective

Allow users to compare two or more academic papers systematically.

This is a core Research Studio capability.

### 26.1 Comparison dimensions

Compare papers across:

1. Research problem.
2. Objectives.
3. Research questions.
4. Methodology.
5. Models and algorithms.
6. Dataset.
7. Sample size.
8. Evaluation metrics.
9. Experimental setup.
10. Results.
11. Contributions.
12. Limitations.
13. Future work.

### 26.2 Comparison rules

The comparison engine must distinguish:

- Directly comparable studies.
- Related but methodologically different studies.
- Studies using different datasets.
- Studies evaluating different metrics.
- Studies with different experimental conditions.

Do not present numerical results as directly comparable when the conditions differ.

When information is unavailable, show:

"Not reported."

### 26.3 Comparison structure

For each comparison row, show:

- Dimension.
- Paper A.
- Paper B.
- Additional selected papers.
- Similarities.
- Differences.
- Evidence references.
- Comparison notes.

### 26.4 Database

Create `research_comparisons`.

Suggested fields:

- id
- user_id
- research_project_id
- title
- comparison_configuration
- comparison_result
- created_at
- updated_at

Use child records for selected papers and comparison dimensions where useful.

### 26.5 APIs

- `POST /api/v1/research/projects/{project_id}/comparisons`
- `GET /api/v1/research/projects/{project_id}/comparisons`
- `GET /api/v1/research/comparisons/{comparison_id}`
- `DELETE /api/v1/research/comparisons/{comparison_id}`

### 26.6 Frontend

Build a comparison workspace with:

- Paper selector.
- Dimension selector.
- Comparison matrix.
- Similarities.
- Differences.
- Evidence links.
- Export.

Allow users to edit comparison notes without changing extracted source claims.

### 26.7 Acceptance criteria

- Two or more papers can be compared.
- Evidence is attached to comparison claims.
- Missing information is handled correctly.
- Incompatible experimental conditions are clearly identified.
- Comparisons are saved and retrievable.

---

# MILESTONE 7.5 — RESEARCH EVIDENCE MATRIX

## 27. Objective

Provide a structured literature-review matrix.

Researchers must be able to organise and compare the findings of multiple papers in a consistent format.

### 27.1 Default columns

Include:

- Paper title.
- Authors.
- Year.
- Research problem.
- Objectives.
- Methodology.
- Dataset.
- Model or algorithm.
- Evaluation metrics.
- Results.
- Contributions.
- Limitations.
- Future work.

### 27.2 User customisation

Allow:

- Add column.
- Rename column.
- Remove column.
- Reorder columns.
- Edit researcher notes.
- Filter.
- Sort.
- Group.
- Search.
- Export.

### 27.3 Separate information types

Clearly distinguish:

1. Extracted paper information.
2. AI-generated interpretation.
3. Researcher-authored notes.

Do not silently replace researcher-authored content with new AI output.

### 27.4 Database

Create:

- `research_evidence_matrices`
- `research_evidence_matrix_columns`
- `research_evidence_matrix_entries`

Suggested matrix fields:

- id
- user_id
- research_project_id
- title
- description
- created_at
- updated_at

Suggested column fields:

- id
- matrix_id
- column_key
- title
- data_type
- position
- configuration

Suggested entry fields:

- id
- matrix_id
- research_paper_id
- column_id
- value
- value_origin
- evidence_ids
- updated_at

### 27.5 Export

Support existing application export conventions where available.

Potential formats:

- CSV.
- XLSX.
- DOCX.

Do not create a separate export architecture if one already exists.

### 27.6 Acceptance criteria

- Matrices can be created.
- Papers can be added.
- Default columns work.
- Custom columns work.
- Entries can be edited.
- Evidence links remain valid.
- Export preserves the matrix structure.

---

# MILESTONE 7.6 — RESEARCH GAP EXPLORATION

## 28. Objective

Help researchers discover potential research gaps from their selected literature collection.

This must be an evidence-driven analysis feature, not a generic LLM response.

### 28.1 Gap categories

Explore:

**Methodological gaps**

- Existing methods may have limitations.
- Certain methods may not have been evaluated in a particular setting.

**Dataset gaps**

- Limited datasets.
- Lack of diverse data.
- Insufficient dataset size.
- Limited external validation.

**Population or sample gaps**

- Underrepresented populations.
- Narrow sample selection.
- Limited geographical coverage.

**Evaluation gaps**

- Limited evaluation metrics.
- Lack of comparisons.
- Insufficient robustness testing.
- Limited reproducibility.

**Domain gaps**

- Methods may not have been evaluated in a related domain.
- Existing findings may not generalise to another setting.

**Application gaps**

- Research may not address a particular practical use case.

**Generalisation gaps**

- Limited testing across environments or datasets.

**Reproducibility gaps**

- Missing code.
- Incomplete experimental details.
- Unavailable datasets.

**Contradictory findings**

- Different papers may report different findings under different conditions.

### 28.2 Gap generation process

Use this workflow:

1. Identify the selected research papers.
2. Retrieve their validated paper extractions.
3. Collect relevant evidence.
4. Identify repeated methods and limitations.
5. Compare datasets and evaluation conditions.
6. Identify underexplored combinations.
7. Identify conflicting findings.
8. Generate candidate gaps.
9. Attach supporting papers and evidence.
10. Search for counter-evidence within the selected collection.
11. Present candidate gaps for researcher review.

### 28.3 Candidate gap structure

Each candidate should include:

- Title.
- Description.
- Gap category.
- Why it may be a gap.
- Supporting papers.
- Supporting evidence.
- Counter-evidence.
- Confidence.
- Limitations.
- Suggested research direction.
- Researcher validation status.

### 28.4 Confidence labels

Use understandable labels:

- Strong candidate.
- Moderate candidate.
- Preliminary candidate.
- Insufficient evidence.

Do not present confidence as a probability unless the underlying method has been calibrated.

### 28.5 Important safeguards

Never claim:

"No research has been conducted on this topic."

Instead use language such as:

"Within the papers currently included in this research project, relatively limited evidence was found for this combination of methods and evaluation settings."

Make it clear that the finding is limited to the analysed collection.

Do not infer global novelty from a limited paper library.

### 28.6 Database

Create:

- `research_gaps`
- `research_gap_evidence`

Suggested fields:

- id
- user_id
- research_project_id
- title
- description
- category
- rationale
- confidence_label
- limitations
- suggested_direction
- validation_status
- analysis_version
- created_at
- updated_at

Evidence association fields:

- id
- gap_id
- research_paper_id
- research_evidence_id
- evidence_role

Evidence roles can include:

- SUPPORTING
- COUNTER_EVIDENCE
- CONTEXTUAL

### 28.7 Frontend

Create a Research Gaps page.

Include:

- Candidate gaps.
- Category filters.
- Confidence labels.
- Supporting papers.
- Counter-evidence.
- Suggested research directions.
- Researcher validation controls.

Allow users to:

- Accept as a research direction.
- Reject.
- Edit.
- Mark for further investigation.
- Add notes.

### 28.8 Acceptance criteria

- Candidate gaps use selected papers.
- Every supported claim has evidence.
- Counter-evidence is visible.
- Confidence is qualified.
- Users can validate candidates.
- No unsupported novelty claims are generated.

---

# MILESTONE 7.7 — CONTRADICTION AND COUNTER-EVIDENCE DETECTION

## 29. Objective

Identify findings that appear to conflict across selected papers.

A difference in results does not automatically mean that two papers contradict each other.

### 29.1 Detect

- Conflicting reported findings.
- Different conclusions.
- Opposing claims.
- Differences in performance.
- Inconsistent evaluation outcomes.
- Conflicting interpretations.

### 29.2 Analyse conditions

Before classifying a contradiction, examine:

- Dataset.
- Sample size.
- Population.
- Experimental setup.
- Model configuration.
- Evaluation metrics.
- Research conditions.
- Publication context.

Distinguish:

1. Genuine conflicting findings.
2. Different findings under different conditions.
3. Apparent contradictions caused by incompatible metrics.
4. Insufficient evidence to determine whether a contradiction exists.

### 29.3 Structured contradiction record

Store:

- Claim A.
- Claim B.
- Paper A.
- Paper B.
- Supporting evidence A.
- Supporting evidence B.
- Relevant experimental conditions.
- Contradiction category.
- Explanation.
- Confidence.
- Researcher review status.

### 29.4 Database

Create `research_contradictions` and supporting evidence associations.

### 29.5 UI

Display contradictions in a dedicated page.

Allow researchers to:

- Review both claims.
- Open source evidence.
- Compare experimental conditions.
- Mark as genuine contradiction.
- Mark as context-dependent.
- Dismiss.
- Add a researcher explanation.

### 29.6 Acceptance criteria

- Both claims are traceable to paper evidence.
- Conditions are compared.
- Apparent contradictions are distinguished from genuine ones.
- Users can review and correct classifications.

---

# MILESTONE 7.8 — CITATION MANAGEMENT

## 30. Objective

Provide reliable academic reference management.

### 30.1 Supported styles

Support:

- APA.
- IEEE.
- MLA.
- Chicago.
- Harvard.

Use a maintained citation formatting library or a standards-based implementation.

Do not rely on an LLM to invent citation formatting or metadata.

### 30.2 Citation information

Support:

- Authors.
- Title.
- Publication year.
- Journal or conference.
- Publisher.
- DOI.
- Volume.
- Issue.
- Pages.
- URL.
- Access date, where applicable.

### 30.3 Citation operations

Implement:

- Generate citation.
- Copy citation.
- Change citation style.
- Add citation to a draft.
- Insert in-text citation.
- Manage references.
- Detect missing metadata.
- Export bibliography.

### 30.4 Citation validation

Validate:

- Author order.
- Publication year.
- DOI format.
- Title.
- Venue.
- Page information.
- Metadata completeness.

Do not invent missing details.

### 30.5 Database

Create `research_citations`.

Suggested fields:

- id
- user_id
- research_project_id
- research_paper_id
- citation_style
- formatted_citation
- metadata_snapshot
- created_at
- updated_at

Where a paper's metadata changes, retain enough information to regenerate citations accurately.

### 30.6 Acceptance criteria

- Citations can be generated in supported styles.
- Metadata is taken from validated records.
- Missing information is clearly identified.
- Citations can be inserted into drafts.
- Bibliographies can be exported.

---

# MILESTONE 7.9 — RESEARCH WRITING STUDIO

## 31. Objective

Create an evidence-grounded research writing environment.

Users should be able to develop research documents using their selected papers, evidence matrix, research gaps and citations.

### 31.1 Supported sections

Support:

- Research title.
- Abstract.
- Introduction.
- Background.
- Literature review.
- Problem statement.
- Research objectives.
- Research questions.
- Methodology.
- Proposed approach.
- Results.
- Discussion.
- Limitations.
- Conclusion.
- Future work.
- References.

### 31.2 Writing assistance

Support:

- Draft generation.
- Section expansion.
- Rewriting.
- Academic tone improvement.
- Grammar improvement.
- Clarity improvement.
- Literature synthesis.
- Paragraph organisation.
- Citation insertion.
- Evidence checking.
- Claim verification.
- Unsupported claim detection.

### 31.3 Evidence-grounded generation

Before generating a research section:

1. Identify the selected research project.
2. Retrieve relevant paper evidence.
3. Retrieve relevant comparison and matrix entries.
4. Retrieve validated research gaps where appropriate.
5. Retrieve relevant knowledge graph concepts.
6. Generate a structured draft.
7. Validate citations and evidence references.
8. Identify unsupported claims.
9. Present the result for researcher review.

### 31.4 Claim verification

For each research claim, distinguish:

- Directly supported by a paper.
- Supported by multiple papers.
- Researcher interpretation.
- AI-generated synthesis.
- Unsupported by selected sources.

Do not silently convert an interpretation into a reported research finding.

### 31.5 Draft management

Create:

- `research_drafts`
- `research_draft_versions`

Suggested draft fields:

- id
- user_id
- research_project_id
- title
- document_type
- content
- status
- created_at
- updated_at

Suggested version fields:

- id
- draft_id
- version_number
- content_snapshot
- change_summary
- created_at

### 31.6 Editing safeguards

- Never silently overwrite a researcher draft.
- Save versions.
- Allow restoration.
- Clearly distinguish AI suggestions from accepted content.
- Preserve citation references.
- Validate evidence references before export.

### 31.7 Export

Support the existing document export infrastructure for:

- DOCX.
- PDF.
- Markdown.

Preserve headings, references, citations and formatting.

### 31.8 Acceptance criteria

- Users can create and edit research drafts.
- Draft versions persist.
- AI assistance uses selected evidence.
- Citations remain connected.
- Unsupported claims are flagged.
- Export works without corrupting formatting.

---

# MILESTONE 7.10 — KNOWLEDGE GRAPH INTEGRATION

## 32. Objective

Connect Research Studio to Phase 6.

Research papers should enrich the user's existing academic knowledge graph.

### 32.1 Extract research entities

Where supported by paper evidence, identify:

- Concepts.
- Models.
- Algorithms.
- Methods.
- Datasets.
- Evaluation metrics.
- Research domains.
- Applications.
- Theories.

### 32.2 Connect to existing nodes

Match extracted entities against existing knowledge nodes.

Use:

- Normalised names.
- Aliases.
- Context.
- Existing descriptions.
- Semantic similarity for candidate generation.
- User confirmation where needed.

Do not create duplicate concepts unnecessarily.

### 32.3 Research relationships

Support useful relationships such as:

- METHOD_USED_IN.
- MODEL_EVALUATED_ON.
- DATASET_USED_BY.
- METRIC_USED_FOR.
- PAPER_STUDIES.
- PAPER_PROPOSES.
- PAPER_EXTENDS.
- PAPER_COMPARES_WITH.

Extend the existing relationship system carefully.

Do not break Phase 6 relationship validation.

### 32.4 Provenance

Research-derived graph nodes and edges must link to:

- Paper.
- Paper extraction.
- Evidence claim.
- Source document.
- Document version.
- Page or chunk.

### 32.5 Frontend

From a concept page, users should be able to discover:

- Related papers.
- Methods used in research.
- Datasets associated with the concept.
- Metrics used to evaluate related methods.
- Research findings.
- Relevant research gaps.

From a paper page, users should be able to open related knowledge graph concepts.

### 32.6 Acceptance criteria

- Research concepts connect to existing graph nodes.
- Duplicate concepts are controlled.
- Research provenance is retained.
- Paper-to-concept navigation works.
- Existing learner mastery is not incorrectly modified by paper existence.

Important: reading a research paper may add academic knowledge, but it must not automatically increase the learner's demonstrated mastery.

---

# MILESTONE 7.11 — RESEARCH STUDIO DASHBOARD

## 33. Objective

Create a central dashboard for research work.

### 33.1 Dashboard overview

Show:

- Active research projects.
- Total papers.
- Analysed papers.
- Papers awaiting analysis.
- Literature comparisons.
- Evidence matrices.
- Candidate research gaps.
- Contradictions requiring review.
- Drafts in progress.
- Recent research activity.

### 33.2 Project dashboard

Each research project should have:

- Overview.
- Papers.
- Analysis.
- Comparison.
- Evidence Matrix.
- Research Gaps.
- Contradictions.
- Citations.
- Writing Studio.
- Knowledge Graph.

Use project-scoped navigation.

### 33.3 UX requirements

- Consistent design system.
- Clear navigation.
- Search and filters.
- Empty states.
- Processing indicators.
- Error handling.
- Responsive layout.
- Accessible controls.
- No inert buttons.
- No fabricated example metrics presented as real user data.

---

# MILESTONE 7.12 — RESEARCH STUDIO TESTING

## 34. Backend testing

Cover:

- Project CRUD.
- Project ownership.
- Paper upload.
- Paper metadata.
- Duplicate detection.
- Paper extraction.
- Structured validation.
- Evidence provenance.
- Missing information.
- Extraction retries.
- Paper comparisons.
- Evidence matrices.
- Research gap generation.
- Counter-evidence.
- Contradiction detection.
- Citation generation.
- Citation metadata validation.
- Draft creation.
- Draft versioning.
- Evidence-grounded generation.
- Knowledge graph integration.
- Deletion and ownership propagation.

## 35. Frontend testing

Cover:

- Research Studio landing page.
- Project creation.
- Paper library.
- Paper upload.
- Paper detail.
- Analysis tabs.
- Evidence navigation.
- Literature comparison.
- Matrix editing.
- Matrix export.
- Research gap review.
- Contradiction review.
- Citation management.
- Writing Studio.
- Draft restoration.
- Responsive layouts.
- Loading, error and empty states.

## 36. End-to-end testing

Test the following complete journey:

1. Create a research project.
2. Upload three academic papers.
3. Process and extract paper content.
4. Review paper metadata.
5. Inspect each structured paper analysis.
6. Open evidence for methodology and results.
7. Compare the three papers.
8. Create an evidence matrix.
9. Generate candidate research gaps.
10. Review supporting and counter-evidence.
11. Review potential contradictions.
12. Generate citations.
13. Create a literature review draft.
14. Insert citations.
15. Validate claims against paper evidence.
16. Save a new draft version.
17. Restore an earlier version.
18. Open relevant knowledge graph concepts.
19. Export the research document.

Use controlled test fixtures and fake model providers where appropriate.

Also run integration tests against a real provider in an explicitly configured test environment when feasible. Do not make production tests dependent on live provider availability.

---

