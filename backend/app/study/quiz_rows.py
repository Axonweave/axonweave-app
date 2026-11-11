"""Turn validated quiz output into `quiz_questions` rows (the only place answer keys are stored)."""

from __future__ import annotations

from typing import Any

from app.study.flashcard_rows import card_references

TRUE_FALSE_OPTIONS = [{"id": "true", "text": "True"}, {"id": "false", "text": "False"}]


def generated_question_rows(
    questions: list[Any], sources: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    return [
        {
            "question": q.question,
            "question_type": q.question_type,
            "difficulty": q.difficulty,
            "options": (
                list(TRUE_FALSE_OPTIONS)
                if q.question_type == "true_false"
                else [{"id": o.id, "text": o.text} for o in q.options]
            ),
            "correct_answers": list(q.correct_answers),
            "rubric": list(q.rubric),
            "explanation": q.explanation or None,
            "source_references": card_references(q.source_refs, sources),
        }
        for q in questions
    ]
