# Axonweave— Phase 5: Assessment, Retention and Revision Intelligence

Complete Technical and Development Specification

Phase 5 builds the assessment and revision system for Axonweave AI. Its purpose is to help students practise what they have learned, evaluate their understanding, remember concepts over time, and identify topics that need revision.

This phase builds on the work completed in Phases 1–4:

- Phase 1: Application foundation, authentication, subjects, chapters and workspace management.
- Phase 2: LLM integration, AI Tutor and conversations.
- Phase 3: Document intelligence, embeddings, RAG and source citations.
- Phase 4: AI-generated summaries, flashcards, quizzes, study guides and other learning materials.

Phase 5 turns those generated resources into a continuous learning and revision workflow.

## 1. Main objective

Develop an intelligent assessment and retention system that allows users to:

1. Attempt quizzes generated from their academic materials.
2. Evaluate their understanding of individual topics and chapters.
3. Review flashcards using spaced repetition.
4. Schedule revisions based on memory performance.
5. Track quiz performance and learning progress over time.
6. Identify weak topics and concepts that require additional practice.
7. Receive personalised revision recommendations.
8. Maintain a history of assessments, attempts and revision sessions.

Important: This phase should track learning evidence and revision behaviour. It should not yet implement the full Knowledge Graph, prerequisite mapping or advanced learner intelligence. Those belong to Phase 6.

## 2. Features to implement

### 2.1 Quiz assessment system

Extend the quiz generation functionality developed in Phase 4 into a complete assessment experience.

Requirements:

- Allow users to start quizzes from generated quiz materials.
- Support quizzes associated with:
  - Individual documents.
  - Chapters.
  - Subjects.
  - Selected study materials.
- Support different question types:
  - Multiple-choice questions.
  - Multiple-select questions.
  - True/false questions.
  - Fill-in-the-blank questions.
  - Short-answer questions.
  - Descriptive questions.
- Display one question at a time or all questions together.
- Support question navigation.
- Allow users to mark questions for review.
- Allow users to save progress and resume an unfinished attempt.
- Display a confirmation before submitting.
- Prevent accidental duplicate submissions.
- Record the user's answers and submission time.

Quiz evaluation:

For objective questions:

- Evaluate answers using stored answer keys.
- Calculate the total score.
- Calculate the percentage.
- Identify correct and incorrect answers.
- Provide explanations for answers.
- Display the correct answer after submission.

For descriptive questions:

- Use an LLM-based evaluation mechanism.
- Compare responses against a reference answer and evaluation rubric.
- Generate feedback on missing points and incorrect reasoning.
- Provide an indicative score with an explanation.

Do not treat LLM-based descriptive grading as perfectly objective. Clearly communicate that it is an AI-assisted evaluation.

Results page:

Display:

- Total questions.
- Correct answers.
- Incorrect answers.
- Unanswered questions.
- Total score.
- Percentage.
- Time taken.
- Topic-wise performance.
- Question-wise feedback.
- Suggested revision topics.

### 2.2 Quiz attempt history

Users should be able to access their previous quiz attempts.

Requirements:

- Store every submitted attempt.
- Display quiz name, subject and chapter.
- Display attempt date and score.
- Show the time taken.
- Allow users to open previous results.
- Compare multiple attempts of the same quiz.
- Display score improvement or decline.
- Filter attempts by subject, chapter and date.
- Allow users to delete their own attempt history where appropriate.

Example:

| Attempt        | Score | Percentage |
| -------------- | ----- | ---------- |
| First attempt  | 6/10  | 60%        |
| Second attempt | 8/10  | 80%        |
| Third attempt  | 9/10  | 90%        |

The application should show the improvement over time without claiming that a higher score alone proves long-term retention.

### 2.3 Spaced repetition system

This is one of the most important components of Phase 5.

Implement a spaced repetition system for flashcards generated in Phase 4.

Instead of asking users to revise all flashcards every day, schedule reviews according to how well they remember each card.

Review workflow:

1. User opens the Revision Centre.
2. Application displays flashcards due for review.
3. User reads the question.
4. User attempts to recall the answer.
5. User reveals the answer.
6. User evaluates how well they remembered it.
7. Application schedules the next review.

Use four review ratings:

| Rating | Meaning                    |
| ------ | -------------------------- |
| Again  | Forgot the answer          |
| Hard   | Remembered with difficulty |
| Good   | Remembered correctly       |
| Easy   | Remembered very easily     |

Each rating updates the next review date.

Algorithm recommendation: FSRS

Use the Free Spaced Repetition Scheduler (FSRS) algorithm rather than designing an entirely new scheduling algorithm.

FSRS uses memory-state estimates to schedule future reviews. It is more sophisticated than a basic fixed-interval scheduler.

Requirements:

- Store the review history.
- Maintain the scheduling state for every flashcard.
- Calculate the next due date.
- Support missed reviews.
- Support early reviews.
- Allow users to review cards from a specific chapter or subject.
- Allow users to suspend or unsuspend cards.
- Preserve review history when scheduling parameters change.
- Allow users to configure a target retention rate if the selected FSRS implementation supports it.

Do not implement a fake FSRS algorithm using arbitrary intervals. Use a maintained implementation or a properly validated implementation of the algorithm.

### 2.4 Revision Centre

Create a dedicated Revision Centre in the application.

This should become the central location for all revision activities.

Dashboard components:

- Cards due today.
- Overdue cards.
- New cards.
- Cards reviewed today.
- Daily review completion.
- Upcoming revision schedule.
- Recent revision activity.
- Subject-wise revision status.

Example:

Revision Centre — Illustrative interface

# 24

Due today

# 8

Overdue

# 12

Reviewed today

# 15

New cards

Today's revision progress

12 of 24 cards completed

50%

Start revision session — illustrativeIllustrative UI only; values are sample data, not actual user progress.

Revision filters:

- All subjects.
- Specific subject.
- Specific chapter.
- Due today.
- Overdue.
- New flashcards.
- Suspended flashcards.

### 2.5 Revision session

Implement a focused flashcard review session.

Required interface:

- Display the current flashcard question.
- Provide a reveal-answer interaction.
- Display the answer.
- Show source information where available.
- Provide Again, Hard, Good and Easy controls.
- Show session progress.
- Allow users to end the session.
- Save review results automatically.

Example:

Revision session

Example

Card 4 of 20

Chapter: Neural Networks

What is backpropagation in a neural network?

Reveal answer — illustrative

After revealing the answer, rate your recall:

Again

Hard

Good

Easy

Illustrative interface. Review actions are not active in this example.

At the end of the session, display:

- Total cards reviewed.
- Rating distribution.
- Time spent.
- Cards successfully recalled.
- Cards that need additional review.
- Next scheduled reviews.

### 2.6 Topic-wise performance tracking

Use quiz results and assessment data to identify topics where users are struggling.

Requirements:

- Associate questions with topics or concepts.
- Record topic-level scores.
- Calculate average performance for each topic.
- Track the number of attempts.
- Track recent performance.
- Identify consistently weak topics.
- Display topic-wise progress.

Example:

| Topic           | Average score | Status         |
| --------------- | ------------- | -------------- |
| Neural Networks | 85%           | Strong         |
| Backpropagation | 48%           | Needs revision |
| CNN             | 72%           | Developing     |
| RNN             | 55%           | Needs revision |

Use transparent, configurable thresholds for labels such as Strong and Needs revision. Do not label these values as definitive mastery measurements.

### 2.7 Weak-topic identification

Implement a basic weak-topic detection mechanism.

This should use existing assessment evidence rather than introducing a full learner intelligence engine.

Possible signals:

- Low quiz scores.
- Repeated incorrect answers.
- Repeated attempts with little improvement.
- Flashcards repeatedly rated Again or Hard.
- Topics with overdue revision cards.
- Recent performance compared with previous performance.

Output:

The application should identify topics that need attention and explain why.

Example:

> Backpropagation may need revision because your recent quiz accuracy is 48%, and several related flashcards were rated Again.

Avoid presenting a weak-topic prediction as a definitive statement about the user's knowledge.

### 2.8 Personalised revision recommendations

Create a basic recommendation engine using the information available from quiz and revision history.

Examples:

- Revise Backpropagation because of low quiz performance.
- Review 12 flashcards due today.
- Attempt another quiz on CNN.
- Revisit the Neural Networks chapter.
- Practise questions you previously answered incorrectly.

Recommendation priority should consider:

1. Overdue revision cards.
2. Repeatedly incorrect questions.
3. Low topic-wise assessment performance.
4. Upcoming revision dates.
5. Topics that have not been practised recently.

For the initial implementation, use a transparent rule-based recommendation engine. An LLM may generate the natural-language explanation, but it should not invent performance data or scheduling decisions.

## 3. Learning analytics and progress dashboard

Extend the existing dashboard to show meaningful assessment and revision statistics.

### 3.1 Overall learning statistics

Display:

- Total quizzes attempted.
- Average quiz score.
- Total flashcards reviewed.
- Total revision sessions.
- Daily study activity.
- Total time spent on assessments and revision.
- Current revision streak.
- Due and overdue flashcards.
- Topics needing attention.

### 3.2 Visual analytics

Use charts where they provide useful information:

| Chart                         | Purpose                             |
| ----------------------------- | ----------------------------------- |
| Quiz performance over time    | Track score improvement             |
| Subject-wise performance      | Compare performance across subjects |
| Revision activity             | Track daily review activity         |
| Flashcard rating distribution | Understand recall difficulty        |
| Topic-wise accuracy           | Identify weak areas                 |

Provide filters for date range, subject and chapter.

### 3.3 Study activity calendar

Create a calendar showing revision and assessment activity.

- Mark days when the user completed a revision session.
- Mark days when the user attempted a quiz.
- Show the number of activities completed each day.
- Allow users to click a date and inspect its activity.
- Display the current study streak and longest streak.

Do not punish users for missing a day. The purpose is to provide visibility into their study habits, not to create unnecessary pressure.

## 4. Database design

Reuse the existing PostgreSQL database from previous phases. Do not create a separate database for assessment and revision.

The following is the recommended logical schema. Before implementing it, inspect the existing Phase 4 tables and reuse them wherever possible.

### 4.1 `quiz_attempts`

Stores each quiz attempt.

| Column             | Type      | Description                       |
| ------------------ | --------- | --------------------------------- |
| id                 | UUID      | Primary key                       |
| user_id            | UUID      | Attempt owner                     |
| quiz_id            | UUID      | Associated quiz                   |
| started_at         | TIMESTAMP | Start time                        |
| submitted_at       | TIMESTAMP | Submission time                   |
| status             | VARCHAR   | In progress, submitted, abandoned |
| total_questions    | INTEGER   | Number of questions               |
| correct_answers    | INTEGER   | Correct count                     |
| incorrect_answers  | INTEGER   | Incorrect count                   |
| unanswered         | INTEGER   | Unanswered count                  |
| score              | DECIMAL   | Earned score                      |
| max_score          | DECIMAL   | Maximum score                     |
| percentage         | DECIMAL   | Percentage                        |
| time_taken_seconds | INTEGER   | Duration                          |
| created_at         | TIMESTAMP | Creation time                     |

### 4.2 `quiz_attempt_answers`

Stores answers submitted during each attempt.

| Column        | Type      | Description             |
| ------------- | --------- | ----------------------- |
| id            | UUID      | Primary key             |
| attempt_id    | UUID      | Associated attempt      |
| question_id   | UUID      | Associated question     |
| user_answer   | JSONB     | Submitted answer        |
| is_correct    | BOOLEAN   | Evaluation result       |
| marks_awarded | DECIMAL   | Awarded marks           |
| feedback      | TEXT      | Explanation or feedback |
| evaluated_at  | TIMESTAMP | Evaluation time         |

Do not return the correct answer or answer key to the frontend before submission.

### 4.3 `flashcard_scheduling`

Stores the current scheduling state of each user's flashcard.

| Column         | Type      | Description                       |
| -------------- | --------- | --------------------------------- |
| id             | UUID      | Primary key                       |
| user_id        | UUID      | Card owner                        |
| flashcard_id   | UUID      | Associated flashcard              |
| due_at         | TIMESTAMP | Next review date                  |
| stability      | DECIMAL   | FSRS memory stability             |
| difficulty     | DECIMAL   | FSRS difficulty                   |
| elapsed_days   | INTEGER   | Days since previous review        |
| scheduled_days | INTEGER   | Scheduled interval                |
| repetitions    | INTEGER   | Review count                      |
| lapses         | INTEGER   | Number of failed recalls          |
| state          | VARCHAR   | New, learning, review, relearning |
| suspended      | BOOLEAN   | Whether card is suspended         |
| last_review_at | TIMESTAMP | Previous review                   |
| created_at     | TIMESTAMP | Creation time                     |
| updated_at     | TIMESTAMP | Last update                       |

Add a unique constraint on `(user_id, flashcard_id)` so a user cannot accidentally have duplicate scheduling records for the same card.

The exact FSRS state and parameter fields should follow the selected implementation's data model.

### 4.4 `flashcard_reviews`

Stores individual review events.

| Column           | Type      | Description               |
| ---------------- | --------- | ------------------------- |
| id               | UUID      | Primary key               |
| user_id          | UUID      | User                      |
| flashcard_id     | UUID      | Reviewed card             |
| rating           | VARCHAR   | Again, Hard, Good, Easy   |
| reviewed_at      | TIMESTAMP | Review timestamp          |
| elapsed_days     | INTEGER   | Previous elapsed interval |
| scheduled_days   | INTEGER   | New scheduled interval    |
| response_time_ms | INTEGER   | Time taken to recall      |
| previous_state   | JSONB     | Previous scheduler state  |
| resulting_state  | JSONB     | Updated scheduler state   |

Store review events separately from scheduling state. This allows the system to reconstruct history and analyse how a card's scheduling changed.

### 4.5 `revision_sessions`

Stores flashcard review sessions.

| Column           | Type           | Description                  |
| ---------------- | -------------- | ---------------------------- |
| id               | UUID           | Primary key                  |
| user_id          | UUID           | Session owner                |
| subject_id       | UUID, nullable | Selected subject             |
| chapter_id       | UUID, nullable | Selected chapter             |
| started_at       | TIMESTAMP      | Session start                |
| completed_at     | TIMESTAMP      | Session end                  |
| total_cards      | INTEGER        | Cards in session             |
| reviewed_cards   | INTEGER        | Completed cards              |
| duration_seconds | INTEGER        | Session duration             |
| status           | VARCHAR        | Active, completed, abandoned |

### 4.6 `topic_performance`

Stores aggregated topic-level assessment information.

| Column              | Type           | Description         |
| ------------------- | -------------- | ------------------- |
| id                  | UUID           | Primary key         |
| user_id             | UUID           | User                |
| subject_id          | UUID           | Subject             |
| chapter_id          | UUID, nullable | Chapter             |
| topic_name          | VARCHAR        | Topic               |
| questions_attempted | INTEGER        | Attempted questions |
| correct_answers     | INTEGER        | Correct answers     |
| accuracy            | DECIMAL        | Accuracy percentage |
| last_assessed_at    | TIMESTAMP      | Last assessment     |
| updated_at          | TIMESTAMP      | Last update         |

You can also derive these statistics from quiz attempt records. If you store aggregates, ensure they can be recalculated from the original records so that data does not become inconsistent.

### 4.7 `revision_recommendations`

Stores revision recommendations presented to the user.

| Column              | Type                | Description                     |
| ------------------- | ------------------- | ------------------------------- |
| id                  | UUID                | Primary key                     |
| user_id             | UUID                | User                            |
| recommendation_type | VARCHAR             | Quiz, flashcard, topic, chapter |
| target_id           | UUID                | Related resource                |
| reason              | TEXT                | Explanation                     |
| priority            | VARCHAR             | Low, medium, high               |
| status              | VARCHAR             | Pending, completed, dismissed   |
| created_at          | TIMESTAMP           | Creation time                   |
| completed_at        | TIMESTAMP, nullable | Completion time                 |

### Database design rules

- Use UUIDs for identifiers.
- Add indexes on `user_id`, `quiz_id`, `flashcard_id`, `due_at` and timestamps used for filtering.
- Use foreign keys wherever appropriate.
- Use transactions when submitting quiz attempts and updating revision states.
- Apply user ownership checks to every operation.
- Store timestamps consistently in UTC and display them in the user's local timezone.
- Use soft deletion only where it is useful; otherwise follow the deletion behaviour already established in the application.
- Avoid duplicating information already stored in Phase 4 tables.

## 5. Backend API development

Implement the following APIs in the existing FastAPI backend.

These are recommended endpoint contracts. Adjust naming to match your existing API conventions instead of creating duplicate endpoints.

### 5.1 Quiz attempt APIs

| Method | Endpoint                                            | Purpose                 |
| ------ | --------------------------------------------------- | ----------------------- |
| POST   | `/quizzes/{quiz_id}/attempts`                       | Start a quiz attempt    |
| GET    | `/quiz-attempts`                                    | List user's attempts    |
| GET    | `/quiz-attempts/{attempt_id}`                       | Get attempt details     |
| PUT    | `/quiz-attempts/{attempt_id}/answers/{question_id}` | Save an answer          |
| POST   | `/quiz-attempts/{attempt_id}/submit`                | Submit and evaluate     |
| GET    | `/quiz-attempts/{attempt_id}/results`               | Get result and feedback |
| GET    | `/quizzes/{quiz_id}/attempts/history`               | Get attempts for a quiz |

Important implementation requirements:

- Validate quiz ownership and accessibility.
- Only allow attempts for available quizzes.
- Prevent submissions after an attempt is already submitted.
- Prevent users from modifying submitted answers.
- Calculate objective scores on the backend.
- Keep answer keys private.
- Store results transactionally.
- Make submission idempotent so retrying a network request does not create duplicate results.

### 5.2 Flashcard scheduling APIs

| Method | Endpoint                               | Purpose                     |
| ------ | -------------------------------------- | --------------------------- |
| GET    | `/revision/due`                        | Get cards due for review    |
| GET    | `/revision/new`                        | Get new flashcards          |
| GET    | `/revision/overdue`                    | Get overdue cards           |
| GET    | `/revision/summary`                    | Get revision statistics     |
| GET    | `/flashcards/{card_id}/schedule`       | Get card scheduling details |
| POST   | `/flashcards/{card_id}/review`         | Submit a review rating      |
| PATCH  | `/flashcards/{card_id}/suspend`        | Suspend a card              |
| PATCH  | `/flashcards/{card_id}/unsuspend`      | Resume a card               |
| GET    | `/flashcards/{card_id}/review-history` | Get review history          |

The review endpoint should accept a rating and optional response time, then:

1. Validate the user's ownership of the card.
2. Load the current scheduling state.
3. Pass the state and rating to the FSRS scheduler.
4. Calculate the next due date.
5. Update the scheduling state.
6. Save a review event.
7. Return the updated schedule.

Use a database transaction to ensure the event and updated scheduling state stay consistent.

### 5.3 Revision session APIs

| Method | Endpoint                           | Purpose                  |
| ------ | ---------------------------------- | ------------------------ |
| POST   | `/revision/sessions`               | Start a revision session |
| GET    | `/revision/sessions`               | List sessions            |
| GET    | `/revision/sessions/{id}`          | Get session details      |
| POST   | `/revision/sessions/{id}/complete` | Complete session         |
| POST   | `/revision/sessions/{id}/abandon`  | Abandon session          |

### 5.4 Performance and analytics APIs

| Method | Endpoint                         | Purpose                     |
| ------ | -------------------------------- | --------------------------- |
| GET    | `/analytics/overview`            | Overall learning statistics |
| GET    | `/analytics/quiz-performance`    | Quiz performance over time  |
| GET    | `/analytics/subject-performance` | Subject-wise statistics     |
| GET    | `/analytics/topic-performance`   | Topic-wise statistics       |
| GET    | `/analytics/revision-activity`   | Revision activity           |
| GET    | `/analytics/study-calendar`      | Calendar activity           |
| GET    | `/analytics/streaks`             | Study streak information    |

All endpoints should support suitable filters such as `subject_id`, `chapter_id`, `start_date` and `end_date`.

### 5.5 Recommendation APIs

| Method | Endpoint                         | Purpose                        |
| ------ | -------------------------------- | ------------------------------ |
| GET    | `/recommendations/revision`      | Get recommended revision tasks |
| GET    | `/recommendations/weak-topics`   | Get weak-topic recommendations |
| POST   | `/recommendations/{id}/complete` | Mark recommendation complete   |
| POST   | `/recommendations/{id}/dismiss`  | Dismiss recommendation         |

## 6. Frontend implementation

Build on the existing Axonweave AI design system. Do not redesign the entire application or introduce a separate visual identity for Phase 5.

### Required pages

Suggested navigation structure

Dashboard

Assessments

Quiz list

Quiz attempt interface

Quiz results

Attempt history

Revision Centre

Revision dashboard

Due flashcards

Revision session

Review history

Learning Analytics

Performance overview

Subject analytics

Topic performance

Study calendar

### Frontend requirements

Quiz interface

- Responsive layout.
- Question navigation.
- Timer where appropriate.
- Answer selection and saving.
- Review markers.
- Submission confirmation.
- Result visualisation.

Revision interface

- Flashcard flip/reveal interaction.
- Rating controls.
- Session progress indicator.
- Keyboard accessibility where practical.
- Mobile-friendly controls.

Analytics interface

- Reusable chart components.
- Date and subject filters.
- Loading, empty and error states.
- Clear distinction between actual results and estimates.

State management

- Continue using TanStack Query for server data.
- Use existing Zustand stores only for appropriate client-side state.
- Do not store quiz answer keys in frontend state.
- Persist unfinished quiz answers through the backend rather than relying only on browser state.
- Handle network interruptions and duplicate requests.

## 7. System architecture and processing flow

Keep the existing modular monolith architecture.

Next.js frontend

Quiz interface · Revision Centre · Analytics

FastAPI backend

Assessment service · Revision service · Analytics service · Recommendation service

PostgreSQL

Attempts · Reviews · Scheduling · Analytics

FSRS scheduler

Memory-state updates · Due dates

Phase 1–4 services

Authentication · AI Tutor · RAG · Documents · Generated flashcards and quizzes

### Important architectural principles

1. Do not create a separate flashcard generation system. Reuse Phase 4.
2. Do not regenerate quizzes just to record an attempt. Reuse stored quiz questions.
3. Keep FSRS scheduling logic in a dedicated service.
4. Keep analytics calculations in backend services.
5. Use background jobs only where calculations or aggregation are expensive.
6. Use the existing LLM provider abstraction for descriptive evaluation and optional feedback.
7. Do not make an LLM call for basic objective quiz grading or flashcard scheduling.

## 8. Security and data integrity

This phase processes assessment results and personal learning activity, so access control is essential.

Implement:

- User-level ownership checks for quizzes, attempts, flashcards and revision sessions.
- Validation of all request bodies.
- Server-side objective answer evaluation.
- No exposure of correct answers before quiz submission.
- Protection against modifying another user's attempts.
- Rate limits on AI-based descriptive evaluation.
- Limits on quiz submission and review request frequency.
- Safe handling of incomplete and duplicate requests.
- Transactional storage of quiz results and flashcard review events.
- Correct handling of deleted flashcards and associated scheduling records.
- Appropriate retention and deletion behaviour for user activity data.

Never trust quiz scores or answer correctness values submitted by the frontend.

## 9. Testing requirements

Implement unit tests, integration tests and frontend tests.

### Quiz tests

- Start a valid quiz attempt.
- Save an answer.
- Change an answer before submission.
- Submit a quiz.
- Calculate objective question scores.
- Handle unanswered questions.
- Evaluate descriptive answers.
- Reject duplicate submission.
- Reject attempts belonging to another user.
- Prevent access to answer keys before submission.
- Resume an unfinished attempt.

### FSRS tests

- Schedule a new card.
- Submit Again, Hard, Good and Easy ratings.
- Verify updated scheduling states.
- Verify due dates.
- Review overdue cards.
- Review cards early.
- Suspend and unsuspend cards.
- Handle repeated reviews.
- Handle missing or invalid scheduling data.
- Verify timezone handling.

Use deterministic test inputs and compare expected outputs against the selected FSRS implementation.

### Analytics tests

- Calculate quiz accuracy.
- Calculate average performance.
- Calculate subject-wise performance.
- Calculate topic-wise accuracy.
- Calculate revision completion.
- Calculate streaks across dates and timezones.
- Filter statistics by date range.
- Ensure one user's statistics never include another user's data.

### Frontend tests

- Quiz navigation works.
- Answers are saved.
- Submission confirmation works.
- Results display correctly.
- Flashcards reveal answers.
- Review ratings are submitted.
- Revision progress updates.
- Charts display correct backend data.
- Empty and error states work.

## 10. Acceptance criteria

Phase 5 should only be considered complete when all the following conditions are met.

- Users can start and submit quizzes created in Phase 4.
- Quiz attempts are saved and can be reviewed later.
- Objective questions are graded correctly on the backend.
- Descriptive questions can receive AI-assisted feedback.
- Quiz results display scores and topic-wise performance.
- Users can review their quiz history.
- Users can access flashcards generated in Phase 4.
- FSRS schedules reviews based on user ratings.
- Users can complete flashcard revision sessions.
- Due, new and overdue flashcards are displayed correctly.
- Review history is persisted.
- Users can track subject-wise and topic-wise performance.
- The system identifies weak topics based on assessment evidence.
- The system generates basic personalised revision recommendations.
- Learning analytics and the study calendar display correct information.
- All user data is protected by ownership checks.
- The system handles errors, retries and duplicate requests.
- Existing Phase 1–4 functionality continues working.

## 11. Recommended implementation order

Do not attempt to build all Phase 5 features simultaneously. Follow this order to reduce integration problems.

| Step | Development task                                                   | Priority |
| ---- | ------------------------------------------------------------------ | -------- |
| 1    | Inspect and understand existing Phase 4 quiz and flashcard schemas | Critical |
| 2    | Implement quiz attempt backend                                     | Critical |
| 3    | Implement quiz answer submission and evaluation                    | Critical |
| 4    | Build quiz-taking interface and results page                       | Critical |
| 5    | Implement quiz attempt history                                     | High     |
| 6    | Integrate the FSRS scheduling engine                               | Critical |
| 7    | Build flashcard scheduling and review APIs                         | Critical |
| 8    | Build Revision Centre and review session UI                        | Critical |
| 9    | Implement topic-wise performance tracking                          | High     |
| 10   | Implement analytics dashboard                                      | High     |
| 11   | Implement weak-topic identification                                | High     |
| 12   | Implement revision recommendations                                 | Medium   |
| 13   | Complete testing, security checks and integration                  | Critical |

Suggested development milestones:

- Milestone 1: Quiz assessment and attempt history.
- Milestone 2: Spaced repetition and revision sessions.
- Milestone 3: Learning analytics and topic performance.
- Milestone 4: Weak-topic identification and recommendations.
- Milestone 5: Testing, optimisation and release.

## 12. Features explicitly excluded from Phase 5

Do not allow the scope to expand into Phase 6 or later.

| Feature                                             | Planned phase |
| --------------------------------------------------- | ------------- |
| Full Knowledge Graph construction                   | Phase 6       |
| Concept relationship extraction                     | Phase 6       |
| Concept prerequisite mapping                        | Phase 6       |
| Advanced learner knowledge modelling                | Phase 6       |
| Misconception detection using concept relationships | Phase 6       |
| Advanced adaptive learning paths                    | Phase 6       |
| Research-paper comparison                           | Phase 7       |
| Research gap identification                         | Phase 7       |
| Literature review automation                        | Phase 7       |
| AI Viva Examiner                                    | Phase 8       |
| Interactive concept simulations                     | Phase 8       |
| Audio-based revision                                | Phase 8       |
| Advanced multilingual learning                      | Phase 8       |

Phase 5 can use basic topic labels and assessment statistics, but it must not introduce the complete Knowledge Graph architecture.

## 13. Technical stack

Reuse the technologies already established in Axonweave AI.

| Component         | Technology                         |
| ----------------- | ---------------------------------- |
| Frontend          | Next.js, React, TypeScript         |
| Styling           | Tailwind CSS                       |
| Server state      | TanStack Query                     |
| Client state      | Zustand                            |
| Backend           | Python, FastAPI                    |
| Database          | PostgreSQL                         |
| ORM               | Existing project ORM               |
| Spaced repetition | FSRS-compatible library            |
| Charts            | Existing chart library or Recharts |
| AI evaluation     | Existing Gemini integration        |
| Background tasks  | Celery + Redis, where required     |
| Testing           | Pytest, frontend testing framework |
| Deployment        | Existing Docker-based deployment   |

Do not introduce another database, LLM provider or frontend framework just for Phase 5.

## 14. Important development instructions for your coding AI

If you are using Cursor, Claude Code, Gemini or another coding assistant to implement this phase, give it the following instructions.

# Implementation Instructions — Axonweave AI Phase 5

You are working on an existing application called Axonweave AI. Your task is to implement Phase 5: Assessment, Retention and Revision Intelligence.

## First: Inspect the existing project

Before writing or modifying code:

1. Inspect the complete frontend and backend project structure.
2. Understand the existing database schema and migrations.
3. Inspect authentication and authorization.
4. Understand the existing quiz generation and flashcard generation features from Phase 4.
5. Identify existing API conventions, reusable UI components, services, hooks and state management.
6. Identify the existing Gemini/LLM integration and reuse it where needed.
7. Identify existing testing and deployment conventions.

Do not assume that any feature is missing before inspecting the code.

## Core implementation requirements

Implement the following:

1. Complete quiz assessment and attempt management.
2. Secure answer submission and backend-side grading.
3. Quiz results, feedback and attempt history.
4. FSRS-based spaced repetition for existing flashcards.
5. Flashcard scheduling, review history and revision sessions.
6. A Revision Centre dashboard.
7. Topic-wise assessment performance.
8. Learning analytics and study activity calendar.
9. Evidence-based weak-topic identification.
10. Basic personalised revision recommendations.

## Architecture rules

- Preserve the existing application architecture.
- Reuse the existing PostgreSQL database.
- Reuse existing Phase 4 quiz and flashcard data models wherever possible.
- Do not duplicate existing functionality.
- Keep business logic in backend services.
- Keep API endpoints consistent with the existing application.
- Use database transactions for critical assessment and review operations.
- Use the existing LLM abstraction for AI-assisted descriptive evaluation.
- Use an actual FSRS-compatible scheduling implementation.
- Do not use Gemini to calculate objective quiz scores or schedule flashcard reviews.

## Quality and security requirements

- Enforce authentication and user ownership checks.
- Never expose quiz answer keys before submission.
- Validate all inputs on the backend.
- Prevent duplicate quiz submissions.
- Prevent duplicate flashcard review events caused by retries.
- Handle incomplete quiz attempts.
- Handle failed network requests.
- Use UTC for database timestamps.
- Provide proper loading, empty, success and error states.
- Maintain responsive and accessible interfaces.
- Add backend and frontend tests.
- Preserve all existing Phase 1–4 functionality.

## Development process

Implement the work in small, logically separated milestones.

For each milestone:

1. Explain what already exists.
2. Identify what needs to be implemented.
3. Provide the proposed implementation plan.
4. Implement the backend.
5. Implement the frontend.
6. Add database migrations where necessary.
7. Run tests and resolve errors.
8. Verify integration with previous phases.
9. Summarise the files created or modified.

Do not rewrite working application modules unnecessarily. Do not create mock functionality and present it as completed functionality. Do not hardcode analytics or sample user data into production pages.

## Scope restrictions

Do not implement the full Knowledge Graph, advanced learner modelling, prerequisite mapping, research intelligence, AI viva, audio learning or interactive simulations in this phase. These are reserved for later phases.

## Completion requirement

Phase 5 is complete only when quiz assessment, spaced repetition, revision sessions, performance tracking, weak-topic identification and basic revision recommendations work end to end with persistent database storage and proper security.

Start by inspecting the existing project. Do not immediately generate all the code or modify the database without understanding the current implementation.

## 15. Final expected outcome

Phase 5 completion goal

At the end of Phase 5, Axonweave AI should work like this:

1. A student uploads study material and generates flashcards and quizzes using Phase 3 and Phase 4.
2. The student attempts a quiz and receives a score with explanations.
3. Axonweave AI records the student's performance.
4. The student enters the Revision Centre and sees flashcards due for review.
5. The student reviews flashcards and rates their recall.
6. FSRS calculates when each flashcard should be reviewed again.
7. Axonweave AI analyses quiz performance and identifies topics that need attention.
8. The student receives practical revision recommendations.
9. The dashboard displays their assessment history and revision activity.

