# Phase 4 — AI-Powered Study Generation

## Complete Technical and Development Specification

**Project:** Axonweave AI\
**Phase:** 4 — AI-Powered Study Generation\
**Prerequisites:** Phase 1, Phase 2 and Phase 3\
**Primary objective:** Transform uploaded academic resources and extracted knowledge into personalised, editable and useful learning materials.

---

# 1. Project Overview

## 1.1 Purpose

Phase 3 enables Axonweave to understand uploaded academic documents.

Phase 4 enables Axonweave to transform that understanding into learning resources.

A user should be able to select a document, subject, chapter or group of resources and generate:

1. Short summaries.
2. Detailed summaries.
3. Section-wise summaries.
4. Exam-oriented notes.
5. Flashcards.
6. Quizzes.
7. Practice questions.
8. Study guides.
9. Glossaries.
10. Formula sheets.
11. Key-concept lists.
12. Revision notes.
13. Question banks.

The generated content must be editable, persistent and connected to its original source material.

## 1.2 Product objective

Axonweave should provide more than a button that sends a prompt to an LLM.

It should provide a complete study-material generation system with:

- User-selected source content.
- Custom generation settings.
- Structured LLM output.
- Content validation.
- Source attribution.
- Editing capabilities.
- Saving and organisation.
- Export capabilities.
- Regeneration.
- Quality evaluation.

## 1.3 Main user journey

```
User Uploads Academic Material
             |
             v
       Document Processing
             |
             v
      Open Subject/Chapter
             |
             v
       Select Study Tools
             |
     +-------+--------+
     |       |        |
     v       v        v
 Summary Flashcards Quiz
     |       |        |
     +-------+--------+
             |
             v
      Validate AI Output
             |
             v
      Display Generated Content
             |
             v
       Edit and Save
             |
             v
       Organise in Library
```

---

# 2. Phase 4 Functional Modules

Implement these modules.

## 2.1 Summary Generator

Generate different forms of summaries from selected academic material.

## 2.2 Flashcard Generator

Create question-and-answer flashcards for active recall and revision.

## 2.3 Quiz Generator

Generate objective and subjective questions based on selected materials.

## 2.4 Study Guide Generator

Create structured learning guides for subjects and chapters.

## 2.5 Glossary Generator

Extract important terminology and definitions.

## 2.6 Formula Sheet Generator

Identify mathematical formulas, variables, definitions and explanations.

## 2.7 Question Bank Generator

Create organised question collections based on topic and difficulty.

## 2.8 Study Material Library

Save, edit, organise and retrieve all generated resources.

These modules should share a common generation infrastructure.

---

# 3. Architecture

## 3.1 High-level architecture

```
                USER
                  |
                  v
           NEXT.JS FRONTEND
                  |
                  v
             FASTAPI
                  |
                  v
        STUDY GENERATION SERVICE
                  |
       +----------+-----------+
       |          |           |
       v          v           v
   Source      Generator    Settings
   Selection   Registry     Validation
       |          |           |
       +----------+-----------+
                  |
                  v
          CONTENT RETRIEVAL
                  |
                  v
         STRUCTURED PROMPT
                  |
                  v
             LLM SERVICE
                  |
                  v
        STRUCTURED OUTPUT
                  |
                  v
        OUTPUT VALIDATION
                  |
                  v
       SOURCE ATTRIBUTION
                  |
                  v
         DATABASE STORAGE
                  |
                  v
          FRONTEND DISPLAY
```

## 3.2 Main backend modules

### A. Source selection service

Identifies the source material selected by the user.

Sources may include:

- One document.
- Multiple documents.
- One subject.
- One chapter.
- A selected collection of chunks.
- A manually selected text passage.

### B. Content retrieval service

Retrieves relevant content using Phase 3 extraction and indexing.

### C. Generation service

Manages the generation workflow.

### D. Generator registry

Maintains the available generation types.

### E. Prompt management

Maintains dedicated prompts for each generation type.

### F. Structured output validation

Validates model responses against predefined schemas.

### G. Source attribution

Associates generated content with source documents and locations.

### H. Study material management

Manages saved, edited, archived and deleted generated resources.

### I. Export service

Exports selected study materials into supported formats.

---

# 4. Common Study Generation Engine

Do not implement each generator as an unrelated feature.

Create a reusable generation engine.

## 4.1 Generation workflow

Every generation request should follow:

1. Authenticate user.
2. Validate access to source materials.
3. Validate generation settings.
4. Retrieve source content.
5. Estimate context size.
6. Construct task-specific prompt.
7. Select an appropriate model.
8. Request structured output.
9. Parse the response.
10. Validate schema.
11. Validate source references.
12. Save generated resource.
13. Return the resource to the frontend.

## 4.2 Generation request model

Example:

```
{
  "source": {
    "type": "chapter",
    "id": "chapter-uuid"
  },
  "generation_type": "summary",
  "settings": {
    "detail_level": "detailed",
    "language": "English",
    "include_examples": true
  }
}
```

This is illustrative. Each generator should have its own validated settings schema.

## 4.3 Generation statuses

Use:

- Pending.
- Retrieving sources.
- Generating.
- Validating.
- Completed.
- Failed.
- Cancelled.

Long-running generation should use background processing where appropriate.

Small generation requests may use synchronous or streamed API responses.

## 4.4 Structured output

Do not rely on unstructured text parsing for every generator.

Use provider-supported structured output where available, with Pydantic schemas as the application-level validation boundary.

Validate:

- Required fields.
- Data types.
- Array lengths.
- Question structure.
- Answer structure.
- Difficulty values.
- Source references.
- Duplicate items.

If the output is invalid, allow a limited correction attempt or return a safe error.

Do not repeatedly call the model without limits.

---

# 5. Summary Generator

## 5.1 Purpose

Allow users to convert academic materials into summaries suited to different learning needs.

## 5.2 Summary types

Implement the following.

### A. Quick summary

A short overview of the main ideas.

Useful for:

- Quick revision.
- Understanding the topic.
- Getting an overview before studying.

### B. Detailed summary

A structured and comprehensive summary covering the important concepts.

Useful for:

- Learning a chapter.
- Preparing notes.
- Understanding relationships between concepts.

### C. Section-wise summary

Organises the summary around document headings and sections.

Useful for:

- Following the original syllabus.
- Revising one section at a time.
- Preserving document organisation.

### D. Exam-oriented summary

Focuses on:

- Important definitions.
- Key concepts.
- Important comparisons.
- Processes.
- Formulas.
- Likely examination topics.

Do not claim that generated questions or important topics will definitely appear in an examination.

### E. Beginner-friendly summary

Explains concepts using simple language and examples.

### F. Key-point summary

Provides important concepts in a concise bullet-point format.

## 5.3 Summary settings

Allow users to configure:

- Source.
- Summary type.
- Detail level.
- Language.
- Include examples.
- Include definitions.
- Include important terms.
- Include formulas.
- Preserve headings.
- Include source references.

## 5.4 Summary structure

A detailed summary may include:

1. Topic introduction.
2. Main concepts.
3. Important definitions.
4. Explanation of each concept.
5. Processes and mechanisms.
6. Comparisons.
7. Examples.
8. Important formulas.
9. Key takeaways.
10. Source references.

The structure should adapt to the actual subject matter.

Do not force mathematical formulas into a chapter where they do not exist.

## 5.5 Summary quality requirements

- Preserve the source's meaning.
- Avoid unsupported information.
- Avoid excessive repetition.
- Preserve technical terminology.
- Maintain logical structure.
- Include citations where supported.
- Distinguish additional explanations from source-derived material.

---

# 6. Flashcard Generator

## 6.1 Purpose

Generate flashcards that help users actively retrieve and remember academic information.

## 6.2 Flashcard types

Support:

### A. Basic question-and-answer cards

Example:

Front:

"What is backpropagation?"

Back:

"Backpropagation is an algorithm used to calculate gradients of the loss function with respect to neural network parameters."

### B. Definition cards

Front:

"Define overfitting."

Back:

"Overfitting occurs when a model learns the training data too closely, including noise, and performs poorly on unseen data."

### C. Concept explanation cards

Front:

"Why is a learning rate important?"

Back:

"Learning rate controls the step size used when updating model parameters during optimisation."

### D. Comparison cards

Front:

"Differentiate supervised and unsupervised learning."

Back:

A concise comparison of the two concepts.

### E. Fill-in-the-blank cards

Example:

"Backpropagation uses the \_\_\_\_\_\_ rule to calculate gradients through a computational graph."

Answer:

"Chain"

### F. Application cards

Ask the learner to apply a concept to a practical situation.

## 6.3 Flashcard generation settings

Allow users to select:

- Source document or chapter.
- Number of cards.
- Card type.
- Difficulty.
- Language.
- Include examples.
- Include explanations.
- Include source references.

Suggested quantity options:

-


  10.

- 20.

- 30.

- Custom.

Enforce configurable limits to control generation cost.

## 6.4 Flashcard schema

Example:

```
{
  "front": "What is gradient descent?",
  "back": "An optimisation algorithm...",
  "card_type": "definition",
  "difficulty": "easy",
  "explanation": "It updates model parameters...",
  "source_references": [
    {
      "document_id": "document-uuid",
      "page_number": 12,
      "chunk_id": "chunk-uuid"
    }
  ]
}
```

## 6.5 Flashcard quality requirements

Cards should:

- Test one main concept at a time.
- Avoid unnecessarily long answers.
- Avoid ambiguous questions.
- Avoid duplicate cards.
- Use precise terminology.
- Provide meaningful explanations.
- Include source references.
- Avoid testing unsupported content.

## 6.6 Flashcard editing

Users should be able to:

- Edit the front.
- Edit the back.
- Edit explanations.
- Change difficulty.
- Delete cards.
- Add cards manually.
- Regenerate selected cards.
- Favourite cards.

Do not overwrite user edits when regeneration occurs.

---

# 7. Quiz Generator

## 7.1 Purpose

Generate assessment questions from the user's academic materials.

Phase 4 provides quiz creation and basic quiz-taking functionality.

Advanced assessment intelligence, mastery estimation and adaptive testing can be implemented in a later phase.

## 7.2 Question types

Support:

### A. Multiple-choice questions

- One correct answer.
- Multiple distractors.
- Explanation for the correct answer.

### B. Multiple-select questions

- More than one correct answer.
- Explicit instruction to select all applicable answers.

### C. True/false questions

Statements that require the user to evaluate correctness.

### D. Fill-in-the-blank questions

Require the user to supply a missing term or value.

### E. Short-answer questions

Require concise written responses.

### F. Descriptive questions

Require longer explanations.

For Phase 4, automatically grade objective questions. Descriptive answers can use a rubric-based LLM evaluation as an optional feature, with clear indications that AI grading is an estimate.

## 7.3 Quiz configuration

Allow users to choose:

- Source.
- Number of questions.
- Question types.
- Difficulty.
- Time limit.
- Randomised order.
- Show explanations immediately or after submission.
- Language.

## 7.4 Difficulty levels

Use:

- Easy.
- Medium.
- Hard.

Difficulty should reflect the cognitive demand of the question, not just the length of the question.

## 7.5 Question schema

Example:

```
{
  "question": "Which algorithm is used to update neural network weights?",
  "question_type": "multiple_choice",
  "difficulty": "medium",
  "options": [
    {
      "id": "A",
      "text": "Gradient descent"
    },
    {
      "id": "B",
      "text": "K-Means"
    },
    {
      "id": "C",
      "text": "PCA"
    },
    {
      "id": "D",
      "text": "Apriori"
    }
  ],
  "correct_answers": ["A"],
  "explanation": "Gradient descent updates model parameters...",
  "source_references": []
}
```

The correct answer must never be included in the user-facing question response before the quiz is submitted.

Keep answer keys on the backend.

## 7.6 Quiz-taking interface

Implement:

- Question navigation.
- Previous and next buttons.
- Answer selection.
- Question numbering.
- Progress indicator.
- Timer when enabled.
- Submit confirmation.
- Results page.

## 7.7 Scoring

For objective questions:

- Compare submitted answers with the correct answers.
- Calculate score.
- Calculate percentage.
- Show correct and incorrect answers.
- Display explanations.

For multiple-select questions, define the scoring policy explicitly. Initially, use exact-match scoring to avoid ambiguous partial-credit rules.

## 7.8 Quiz result page

Display:

- Total questions.
- Correct answers.
- Incorrect answers.
- Unanswered questions.
- Score.
- Percentage.
- Time taken.
- Explanations.
- Source references.

Do not present a single quiz score as a definitive measurement of overall subject mastery.

---

# 8. Study Guide Generator

## 8.1 Purpose

Create a structured learning guide for a selected chapter, subject or document collection.

## 8.2 Study guide structure

A study guide may include:

1. Topic overview.
2. Learning objectives.
3. Prerequisite concepts.
4. Main topics.
5. Detailed explanations.
6. Important definitions.
7. Examples.
8. Important comparisons.
9. Formulas where applicable.
10. Practice questions.
11. Key takeaways.
12. Source references.

## 8.3 Generation settings

Allow:

- Beginner level.
- Intermediate level.
- Advanced level.
- Exam preparation.
- Conceptual understanding.
- Practical application.

## 8.4 Study guide requirements

- Preserve academic accuracy.
- Avoid inventing learning objectives unsupported by the source unless clearly marked as generated recommendations.
- Maintain topic hierarchy.
- Include source references.
- Support editing.
- Support export.

---

# 9. Glossary Generator

## 9.1 Purpose

Extract and explain important technical terms from selected academic materials.

## 9.2 Glossary structure

Each term should include:

- Term.
- Definition.
- Explanation.
- Example where appropriate.
- Related concepts.
- Source reference.

Example:

```
{
  "term": "Gradient Descent",
  "definition": "An optimisation algorithm used to minimise a function.",
  "explanation": "It iteratively adjusts parameters...",
  "related_terms": [
    "Learning Rate",
    "Loss Function"
  ],
  "source_references": []
}
```

## 9.3 Glossary features

Users should be able to:

- Search terms.
- Sort alphabetically.
- Filter by topic.
- Edit definitions.
- Add custom terms.
- Export the glossary.

---

# 10. Formula Sheet Generator

## 10.1 Purpose

Identify and organise important formulas from mathematical, scientific and technical materials.

## 10.2 Formula structure

Each entry should contain:

- Formula name.
- Mathematical expression.
- Explanation.
- Variables.
- Units where applicable.
- Conditions of use.
- Example.
- Source reference.

## 10.3 Mathematical rendering

Use a safe mathematical rendering system such as KaTeX or MathJax.

Do not treat arbitrary generated HTML as trusted content.

## 10.4 Formula validation

LLMs can produce incorrect mathematical expressions.

Where possible:

- Validate mathematical syntax.
- Check variable definitions.
- Compare against the source.
- Display the original source reference.
- Flag uncertain formulas.

Do not claim mathematical correctness solely because a model generated valid LaTeX.

---

# 11. Question Bank Generator

## 11.1 Purpose

Generate and organise a reusable collection of academic questions.

A question bank differs from a single quiz because it stores questions for repeated practice and later assessment generation.

## 11.2 Question bank features

- Generate questions by subject.
- Generate questions by chapter.
- Generate questions by difficulty.
- Generate questions by type.
- Save questions.
- Edit questions.
- Delete questions.
- Search questions.
- Filter questions.
- Create quizzes from saved questions.

## 11.3 Question bank organisation

```
Workspace
    |
    Subject
        |
        Chapter
            |
            +-- Easy Questions
            +-- Medium Questions
            +-- Hard Questions
            +-- Application Questions
            +-- Descriptive Questions
```

## 11.4 Question bank requirements

- Avoid duplicate questions.
- Preserve source references.
- Maintain answer keys.
- Support question versioning.
- Preserve user edits.
- Track whether a question is generated or manually created.

---

# 12. Study Material Library

All generated resources must be stored in one central study-material system.

## 12.1 Supported resource types

- Summary.
- Flashcard set.
- Quiz.
- Study guide.
- Glossary.
- Formula sheet.
- Question bank.

## 12.2 Library interface

Display:

- Resource title.
- Resource type.
- Source document.
- Subject.
- Chapter.
- Created date.
- Last updated date.
- Generation status.

## 12.3 Library operations

Users should be able to:

- View resources.
- Search resources.
- Filter by type.
- Filter by subject.
- Edit resources.
- Rename resources.
- Duplicate resources.
- Archive resources.
- Delete resources.
- Favourite resources.
- Export resources.

## 12.4 Resource organisation

Generated content should be associated with the appropriate academic hierarchy.

For example:

```
Workspace: University
    |
    Subject: Machine Learning
        |
        Chapter: Neural Networks
            |
            +-- Detailed Summary
            +-- Flashcards
            +-- Quiz
            +-- Glossary
            +-- Study Guide
```

---

# 13. Editing and Version Management

AI-generated content should never be treated as immutable.

Users must be able to correct and personalise it.

## 13.1 Editing features

Allow users to:

- Edit titles.
- Edit text.
- Edit questions.
- Edit answers.
- Edit explanations.
- Add sections.
- Remove sections.
- Reorder content.
- Add manual content.

## 13.2 Versioning

Store:

- Original generated version.
- Current edited version.
- Version number.
- Modification timestamp.
- User who modified the resource.

Do not silently replace edited resources when regenerating.

## 13.3 Regeneration

Support:

- Regenerate entire resource.
- Regenerate selected section.
- Regenerate selected flashcards.
- Regenerate selected questions.

Always provide a preview before replacing existing content.

---

# 14. Export Functionality

Allow users to export generated resources.

Initial formats:

| Resource      | Export format       |
| ------------- | ------------------- |
| Summary       | PDF, DOCX, Markdown |
| Study guide   | PDF, DOCX           |
| Flashcards    | CSV, PDF            |
| Quiz          | PDF                 |
| Glossary      | CSV, PDF            |
| Formula sheet | PDF                 |
| Question bank | CSV, PDF            |

For Phase 4, prioritise PDF and CSV export. Add DOCX and other formats incrementally.

Generated files must be stored securely or delivered through short-lived download links.

Validate export requests against resource ownership.

---

# 15. AI Generation Quality and Accuracy

Generation quality is more important than the number of generated items.

## 15.1 Source grounding

All generation should be grounded in selected materials when document-based generation is selected.

The application should distinguish:

- Directly source-supported content.
- AI-generated explanatory additions.
- General background knowledge.

## 15.2 Content validation

Validate:

- Required fields.
- Correct output format.
- Duplicate content.
- Empty answers.
- Invalid options.
- Missing correct answers.
- Incorrect question structure.
- Source reference validity.
- Content length.

## 15.3 Flashcard quality

Evaluate:

- One concept per card.
- Clear questions.
- Concise answers.
- Correct terminology.
- Useful explanations.
- Appropriate difficulty.

## 15.4 Quiz quality

Evaluate:

- One clearly correct answer where required.
- Plausible distractors.
- No ambiguous wording.
- No duplicate questions.
- No accidental answer leakage.
- Source support.
- Appropriate difficulty.

## 15.5 Summary quality

Evaluate:

- Coverage of important concepts.
- Correctness.
- Completeness.
- Clarity.
- Structure.
- Faithfulness to source.
- Citation validity.

## 15.6 Human review

Provide editing and feedback controls.

Do not claim generated educational content is guaranteed to be correct.

---

# 16. Personalisation Settings

Phase 4 should introduce basic user-controlled generation preferences.

Allow users to choose:

- Preferred language.
- Explanation level.
- Preferred summary length.
- Preferred question difficulty.
- Include examples.
- Include definitions.
- Include source references.

Store these preferences in the user profile or a dedicated preferences table.

Do not automatically infer sensitive personal characteristics.

Do not build advanced learner adaptation yet.

---

# 17. Background Processing

Some generation tasks may take longer than a normal API request.

Use the existing background task infrastructure.

## 17.1 Background tasks

Suitable tasks include:

- Large study guides.
- Large flashcard sets.
- Large question banks.
- Bulk summaries.
- Multi-document study material generation.
- Export generation.

## 17.2 Generation job statuses

- Pending.
- Retrieving sources.
- Generating.
- Validating.
- Saving.
- Completed.
- Failed.
- Cancelled.

## 17.3 Job reliability

Implement:

- Retry limits.
- Timeout handling.
- Duplicate-job prevention.
- Generation IDs.
- Progress tracking.
- Failure reporting.
- Cancellation.

Avoid restarting expensive generations automatically when the outcome of the previous request is uncertain.

---

# 18. Database Schema Extensions

Extend the existing database.

Do not recreate previous tables.

## 18.1 study_materials

| Column              | Type      | Purpose             |
| ------------------- | --------- | ------------------- |
| id                  | UUID      | Primary key         |
| user_id             | UUID      | Owner               |
| workspace_id        | UUID      | Workspace           |
| subject_id          | UUID      | Optional subject    |
| chapter_id          | UUID      | Optional chapter    |
| title               | VARCHAR   | Resource title      |
| resource_type       | VARCHAR   | Summary, quiz, etc. |
| status              | VARCHAR   | Generation status   |
| content             | JSONB     | Structured resource |
| generation_settings | JSONB     | Settings            |
| source_metadata     | JSONB     | Source information  |
| created_at          | TIMESTAMP | Creation            |
| updated_at          | TIMESTAMP | Update              |
| archived_at         | TIMESTAMP | Archive             |

## 18.2 study_material_versions

| Column            | Type      | Purpose           |
| ----------------- | --------- | ----------------- |
| id                | UUID      | Primary key       |
| study_material_id | UUID      | Resource          |
| version_number    | INTEGER   | Version           |
| content           | JSONB     | Resource snapshot |
| created_by        | UUID      | User or system    |
| created_at        | TIMESTAMP | Creation          |

## 18.3 generation_jobs

| Column            | Type      | Purpose         |
| ----------------- | --------- | --------------- |
| id                | UUID      | Job ID          |
| user_id           | UUID      | Owner           |
| study_material_id | UUID      | Result resource |
| generation_type   | VARCHAR   | Task            |
| status            | VARCHAR   | Job status      |
| progress          | INTEGER   | Progress        |
| model_id          | VARCHAR   | Model           |
| prompt_version    | VARCHAR   | Prompt          |
| error_code        | VARCHAR   | Safe error      |
| created_at        | TIMESTAMP | Creation        |
| completed_at      | TIMESTAMP | Completion      |

## 18.4 flashcard_sets

This can initially be represented through `study_materials` with a structured resource type.

A separate table is justified if flashcard review functionality requires more specialised relationships.

## 18.5 flashcards

| Column            | Type      | Purpose     |
| ----------------- | --------- | ----------- |
| id                | UUID      | Card ID     |
| study_material_id | UUID      | Parent set  |
| front             | TEXT      | Question    |
| back              | TEXT      | Answer      |
| explanation       | TEXT      | Explanation |
| card_type         | VARCHAR   | Card type   |
| difficulty        | VARCHAR   | Difficulty  |
| source_references | JSONB     | Citations   |
| display_order     | INTEGER   | Order       |
| created_at        | TIMESTAMP | Creation    |
| updated_at        | TIMESTAMP | Update      |

## 18.6 quizzes

| Column            | Type      | Purpose         |
| ----------------- | --------- | --------------- |
| id                | UUID      | Quiz ID         |
| study_material_id | UUID      | Parent resource |
| title             | VARCHAR   | Title           |
| description       | TEXT      | Description     |
| time_limit        | INTEGER   | Optional limit  |
| settings          | JSONB     | Configuration   |
| created_at        | TIMESTAMP | Creation        |

## 18.7 quiz_questions

| Column            | Type    | Purpose     |
| ----------------- | ------- | ----------- |
| id                | UUID    | Question ID |
| quiz_id           | UUID    | Parent quiz |
| question          | TEXT    | Question    |
| question_type     | VARCHAR | Type        |
| difficulty        | VARCHAR | Difficulty  |
| options           | JSONB   | Options     |
| correct_answers   | JSONB   | Answer key  |
| explanation       | TEXT    | Explanation |
| source_references | JSONB   | Citations   |
| display_order     | INTEGER | Order       |

Correct answers must remain server-side and must not be returned to the user before submission.

## 18.8 quiz_attempts

| Column          | Type      | Purpose           |
| --------------- | --------- | ----------------- |
| id              | UUID      | Attempt ID        |
| quiz_id         | UUID      | Quiz              |
| user_id         | UUID      | Participant       |
| answers         | JSONB     | Submitted answers |
| score           | NUMERIC   | Score             |
| total_questions | INTEGER   | Count             |
| percentage      | NUMERIC   | Percentage        |
| started_at      | TIMESTAMP | Start             |
| submitted_at    | TIMESTAMP | Submission        |

## 18.9 quiz_attempt_answers

For detailed answer-level history, use a separate table containing:

- Attempt ID.
- Question ID.
- Submitted answer.
- Is correct.
- Awarded score.
- Feedback.
- Submitted timestamp.

This is preferable to a single JSON object if detailed assessment analytics are expected.

---

# 19. Backend API Design

Base path:

`/api/v1`

All operations must enforce user authentication and ownership.

## 19.1 Generation endpoints

| Method | Endpoint                      | Purpose                |
| ------ | ----------------------------- | ---------------------- |
| POST   | /study/generate/summary       | Generate summary       |
| POST   | /study/generate/flashcards    | Generate flashcards    |
| POST   | /study/generate/quiz          | Generate quiz          |
| POST   | /study/generate/study-guide   | Generate study guide   |
| POST   | /study/generate/glossary      | Generate glossary      |
| POST   | /study/generate/formula-sheet | Generate formula sheet |
| POST   | /study/generate/question-bank | Generate question bank |

## 19.2 Study material endpoints

| Method | Endpoint                         | Purpose           |
| ------ | -------------------------------- | ----------------- |
| GET    | /study/materials                 | List materials    |
| GET    | /study/materials/{id}            | Retrieve material |
| PATCH  | /study/materials/{id}            | Edit material     |
| DELETE | /study/materials/{id}            | Delete material   |
| POST   | /study/materials/{id}/duplicate  | Duplicate         |
| POST   | /study/materials/{id}/archive    | Archive           |
| POST   | /study/materials/{id}/regenerate | Regenerate        |

## 19.3 Flashcard endpoints

| Method | Endpoint                         | Purpose      |
| ------ | -------------------------------- | ------------ |
| GET    | /study/flashcards/{set_id}       | Retrieve set |
| POST   | /study/flashcards/{set_id}/cards | Add card     |
| PATCH  | /study/flashcards/cards/{id}     | Edit card    |
| DELETE | /study/flashcards/cards/{id}     | Delete card  |

## 19.4 Quiz endpoints

| Method | Endpoint                                         | Purpose          |
| ------ | ------------------------------------------------ | ---------------- |
| POST   | /study/quizzes/{id}/attempts                     | Start attempt    |
| GET    | /study/quizzes/{id}/attempts/{attempt_id}        | Retrieve attempt |
| POST   | /study/quizzes/{id}/attempts/{attempt_id}/submit | Submit answers   |
| GET    | /study/quizzes/{id}/results/{attempt_id}         | Retrieve results |

Never expose answer keys through the question retrieval endpoint.

## 19.5 Export endpoints

| Method | Endpoint                     | Purpose       |
| ------ | ---------------------------- | ------------- |
| POST   | /study/materials/{id}/export | Create export |
| GET    | /study/exports/{id}          | Export status |
| GET    | /study/exports/{id}/download | Download file |

---

# 20. Frontend Structure

Extend the existing Next.js project.

Suggested structure:

```
frontend/
|
+-- src/
    |
    +-- app/
    |   +-- (dashboard)/
    |       +-- study/
    |       |   +-- page.tsx
    |       |   +-- summaries/
    |       |   +-- flashcards/
    |       |   +-- quizzes/
    |       |   +-- study-guides/
    |       |   +-- glossary/
    |       |   +-- formula-sheets/
    |       |
    |       +-- library/
    |
    +-- components/
    |   +-- study/
    |       +-- generation-dialog.tsx
    |       +-- summary-viewer.tsx
    |       +-- flashcard-viewer.tsx
    |       +-- quiz-builder.tsx
    |       +-- quiz-player.tsx
    |       +-- quiz-results.tsx
    |       +-- study-guide-viewer.tsx
    |       +-- glossary-viewer.tsx
    |       +-- formula-viewer.tsx
    |
    +-- features/
        +-- study-generation/
        +-- flashcards/
        +-- quizzes/
        +-- study-library/
        +-- exports/
```

## 20.1 Study dashboard

Display:

- Generate study material.
- Recent summaries.
- Flashcard sets.
- Recent quizzes.
- Study guides.
- Recent activity.

## 20.2 Generation interface

Provide:

- Source selector.
- Generation type.
- Detail settings.
- Difficulty settings.
- Language settings.
- Quantity.
- Generate button.

Only show settings relevant to the selected generator.

## 20.3 Generation results

Display the generated resource in an editable format.

Include:

- Save.
- Edit.
- Regenerate.
- Export.
- View sources.
- Delete.

## 20.4 Flashcard interface

Provide:

- Front/back card flipping.
- Next and previous cards.
- Progress indicator.
- Shuffle.
- Edit.
- Save.
- Source references.

Do not introduce spaced-repetition scheduling in Phase 4 unless explicitly included as a later extension.

## 20.5 Quiz interface

Provide:

- Question navigation.
- Answer selection.
- Timer.
- Progress.
- Submit.
- Results.
- Explanations.

Ensure correct answers are not exposed through frontend state or API responses before submission.

---

# 21. Security and Data Protection

## 21.1 Generation security

- Require authentication.
- Validate source ownership.
- Validate generation settings.
- Enforce request limits.
- Restrict output sizes.
- Protect provider credentials.
- Prevent duplicate generation requests.

## 21.2 Source access

The generation service must verify that every document or chapter supplied in a request belongs to the user's permitted academic resources.

Never trust source IDs from the frontend without backend verification.

## 21.3 Output safety

- Validate generated JSON.
- Sanitise Markdown and HTML.
- Safely render formulas.
- Never execute generated code.
- Never trust generated URLs.
- Validate citation IDs.
- Validate answer keys.

## 21.4 Quiz security

- Keep correct answers on the backend.
- Do not expose answer keys before submission.
- Verify attempt ownership.
- Prevent unauthorised answer modification after submission.
- Define retake behaviour.
- Prevent duplicate submission.

## 21.5 User privacy

- Treat generated study materials as private user content.
- Enforce ownership.
- Restrict database access.
- Avoid logging full generated content.
- Provide deletion.
- Retain source provenance.
- Respect provider data policies.

## 21.6 Cost protection

Implement:

- Maximum generation requests.
- Maximum flashcard count.
- Maximum quiz questions.
- Maximum output tokens.
- Per-user limits.
- Request timeouts.
- Background job quotas.
- Usage tracking.

---

# 22. Testing and Quality Evaluation

## 22.1 Summary tests

Test:

- Quick summary.
- Detailed summary.
- Section-wise summary.
- Exam-oriented summary.
- Beginner-friendly summary.
- Source attribution.
- Content coverage.

## 22.2 Flashcard tests

Test:

- Correct question-and-answer structure.
- Duplicate detection.
- Clear wording.
- Source references.
- User editing.
- Saving and retrieval.

## 22.3 Quiz tests

Test:

- MCQ generation.
- Multiple-select generation.
- True/false generation.
- Short-answer generation.
- Correct answer validation.
- Scoring.
- Result persistence.
- Answer-key protection.

## 22.4 Study guide tests

Test:

- Heading hierarchy.
- Learning objectives.
- Topic coverage.
- Source attribution.
- Editing.

## 22.5 Glossary tests

Test:

- Term extraction.
- Definition accuracy.
- Duplicate terms.
- Source references.
- Search.

## 22.6 Formula sheet tests

Test:

- LaTeX syntax.
- Variable definitions.
- Source references.
- Mathematical rendering.
- Invalid formula handling.

## 22.7 Security tests

1. User A cannot access User B's generated material.
2. User A cannot modify User B's flashcards.
3. User A cannot submit answers to User B's quiz attempt.
4. Quiz answer keys are not exposed.
5. Invalid source IDs are rejected.
6. Invalid generation types are rejected.
7. Excessive generation requests are rejected.
8. Unsafe output is not executed.
9. Deleted materials are inaccessible.
10. Generated citations are validated.

---

# 23. Phase 4 Acceptance Criteria

Phase 4 is complete when:

## Summary generation

- Quick summary works.
- Detailed summary works.
- Section-wise summary works.
- Exam-oriented summary works.
- Beginner-friendly summary works.
- Source references are preserved.
- Generated summaries can be edited and saved.

## Flashcards

- Flashcards can be generated.
- Different card types are supported.
- Flashcards can be edited.
- Flashcards can be deleted.
- Flashcard sets can be saved.
- Source references are preserved.

## Quizzes

- MCQs can be generated.
- True/false questions can be generated.
- Multiple-select questions can be generated.
- Short-answer questions can be generated.
- Quiz-taking works.
- Objective scoring works.
- Results are saved.
- Correct answers remain protected.

## Other study tools

- Study guides can be generated.
- Glossaries can be generated.
- Formula sheets can be generated.
- Question banks can be generated.

## Study library

- Resources can be saved.
- Resources can be edited.
- Resources can be searched.
- Resources can be filtered.
- Resources can be archived.
- Resources can be deleted.
- Versions are managed.

## Export

- PDF export works.
- CSV export works where applicable.
- Download access is protected.

## Quality and security

- Generated content is source-grounded.
- Citation references are validated.
- Output schemas are validated.
- User ownership is enforced.
- Generation limits are enforced.
- Tests pass.
- Documentation is complete.

---

# 24. Features Outside Phase 4

Do not implement these yet:

- Advanced spaced repetition.
- FSRS scheduling.
- Retention prediction.
- Adaptive quiz difficulty.
- Learner mastery modelling.
- Misconception detection.
- Knowledge graph generation.
- AI viva examination.
- Audio summaries.
- Podcast generation.
- Interactive simulations.
- Research-paper comparison.
- Research gap detection.
- Advanced collaboration.

These will be implemented in later phases.

---

# 25. Implementation Order

Follow this order.

## Step 1 — Review Phase 3

Inspect:

- Document records.
- Document extraction.
- Chunk metadata.
- Retrieval APIs.
- Citation representation.
- RAG integration.
- Ownership validation.

Do not rebuild the document intelligence pipeline.

**Deliverable:** Reusable source retrieval interface.

## Step 2 — Design the common generation engine

Implement:

- Generation request schemas.
- Generator registry.
- Source selection.
- Context retrieval.
- Model selection.
- Prompt management.
- Structured output validation.

**Deliverable:** A common framework for all study-generation tasks.

## Step 3 — Implement summary generation

Implement all initial summary types.

Add editing and saving.

**Deliverable:** Working summary generator.

## Step 4 — Implement flashcards

Build generation, editing, persistence and card viewing.

**Deliverable:** Working flashcard generator.

## Step 5 — Implement quiz generation

Build question generation, quiz-taking, objective scoring and results.

**Deliverable:** Working quiz system.

## Step 6 — Implement study guides and reference tools

Add:

- Study guides.
- Glossaries.
- Formula sheets.
- Question banks.

**Deliverable:** Expanded study generation toolkit.

## Step 7 — Implement the study library

Add resource organisation, search, filters, editing, versioning and deletion.

**Deliverable:** Central study-material library.

## Step 8 — Implement export

Add PDF and CSV export.

**Deliverable:** Downloadable study resources.

## Step 9 — Implement usage controls and security

Add:

- Usage tracking.
- Request quotas.
- Source ownership.
- Output validation.
- Quiz security.
- Cost controls.

**Deliverable:** Secure and measurable generation system.

## Step 10 — Testing and evaluation

Test all generators using representative academic materials.

Evaluate quality, correctness, source attribution and cost.

**Deliverable:** Phase 4 ready for subsequent learning-intelligence features.

---

# 26. Documentation Requirements

Create:

- `docs/STUDY_GENERATION_ARCHITECTURE.md`
- `docs/SUMMARY_GENERATION.md`
- `docs/FLASHCARD_GENERATION.md`
- `docs/QUIZ_GENERATION.md`
- `docs/STUDY_GUIDES.md`
- `docs/STUDY_LIBRARY.md`
- `docs/EXPORT_SYSTEM.md`
- `docs/GENERATION_SECURITY.md`
- `docs/STUDY_GENERATION_TESTING.md`

Document all generation schemas, endpoints, prompts, validation rules and usage limits.

---

# 27. Final Development Instructions

Build Phase 4 on top of the existing Axonweave AI codebase.

Reuse:

- Authentication.
- User management.
- Workspaces.
- Subjects.
- Chapters.
- LLM provider infrastructure.
- Conversation management.
- Document storage.
- Document extraction.
- Embeddings.
- Retrieval.
- RAG.
- Citation management.

Do not create a separate document processing pipeline for summaries, quizzes and flashcards.

Do not duplicate source content unnecessarily.

Do not generate study resources without validating source ownership.

Do not trust model-generated answers, options or citations without validation.

Do not expose quiz answers before submission.

Do not overwrite user edits during regeneration.

Do not hardcode AI-generated demonstration data in production.

Do not leave non-functional buttons or incomplete security controls.

Implement each generator incrementally, with database migrations, schemas, backend services, APIs, frontend components, automated tests and documentation.

**Final outcome:** Axonweave AI will transform academic resources into editable summaries, flashcards, quizzes, study guides, glossaries, formula sheets and question banks, all organised within the user's academic workspace and connected to their original learning materials.

This will establish the foundation for the next stages of Axonweave AI: assessment intelligence, spaced repetition, learner modelling, knowledge graphs and adaptive learning.

# How the phases connect

This is the overall progression we should maintain:

## Axonweave AI development roadmap

1. Phase 1 — Application Foundation

   Completed

   Authentication, dashboard, workspaces, subjects, folders and chapters.
2. Phase 2 — AI Foundation

   Completed

   LLM providers, AI Tutor, conversations, streaming and orchestration.
3. Phase 3 — Document Intelligence

   Next

   Uploads, extraction, chunking, embeddings, retrieval, RAG and citations.
4. Phase 4 — Study Generation

   After Phase 3

   Summaries, flashcards, quizzes, study guides, glossaries and formula sheets.
5. Phase 5 — Assessment and Retention

   Quiz history, spaced repetition, FSRS, revision scheduling and performance tracking.
6. Phase 6 — Learner Intelligence and Knowledge Graph

   Concept relationships, learner evidence, misconceptions, prerequisites and adaptive learning.
7. Phase 7 — Research Studio

   Research-paper extraction, literature comparison, evidence matrices, citation management and research synthesis.
8. Phase 8 — Advanced Intelligence

   Audio learning, AI viva, interactive simulators, multilingual tutoring and collaboration.

## Three important architectural corrections

Before implementation, keep these in mind:

1\. Phase 3 must preserve provenance. Every extracted chunk should retain its original document, version, page or slide, and section. Without this, reliable citations in Phase 4 become difficult.

2\. Phase 4 should use structured generation. A flashcard should be stored as a question, answer, explanation and source reference—not as one long block of generated text. A quiz should have separately protected answer keys.

3\. Phase 4 must not be confused with adaptive learning. Generating a quiz and calculating a score is not the same as measuring whether a student has mastered a concept. That intelligence belongs in later phases.

My recommendation: Complete Phase 3 first and evaluate retrieval quality using real lecture PDFs and presentations. Then build Phase 4 on top of the tested retrieval system. Poor retrieval produces poor summaries, flashcards and quizzes, regardless of how powerful the LLM is.

