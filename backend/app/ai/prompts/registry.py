"""In-code prompt catalogue. The highest version per key is the active one."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from app.ai.prompts import academic_tutor, knowledge, rag, research, study


@dataclass(frozen=True, slots=True)
class PromptDefinition:
    prompt_key: str
    version: int
    content: str

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.content.encode("utf-8")).hexdigest()


PROMPTS: tuple[PromptDefinition, ...] = (
    PromptDefinition(academic_tutor.PROMPT_KEY, academic_tutor.VERSION, academic_tutor.CONTENT),
    PromptDefinition(rag.DOCUMENT_ONLY_KEY, rag.VERSION, rag.DOCUMENT_ONLY),
    PromptDefinition(rag.DOCUMENT_FIRST_KEY, rag.VERSION, rag.DOCUMENT_FIRST),
    PromptDefinition(study.ECHO_KEY, study.ECHO_VERSION, study.ECHO),
    PromptDefinition(study.SUMMARY_KEY, study.SUMMARY_VERSION, study.SUMMARY),
    PromptDefinition(study.FLASHCARDS_KEY, 1, study.FLASHCARDS_V1),
    PromptDefinition(study.FLASHCARDS_KEY, study.FLASHCARDS_VERSION, study.FLASHCARDS),
    PromptDefinition(study.QUIZ_KEY, 1, study.QUIZ_V1),
    PromptDefinition(study.QUIZ_KEY, study.QUIZ_VERSION, study.QUIZ),
    PromptDefinition(study.STUDY_GUIDE_KEY, study.STUDY_GUIDE_VERSION, study.STUDY_GUIDE),
    PromptDefinition(study.GLOSSARY_KEY, study.GLOSSARY_VERSION, study.GLOSSARY),
    PromptDefinition(study.FORMULA_SHEET_KEY, study.FORMULA_SHEET_VERSION, study.FORMULA_SHEET),
    PromptDefinition(study.QUESTION_BANK_KEY, study.QUESTION_BANK_VERSION, study.QUESTION_BANK),
    PromptDefinition(study.QUIZ_GRADING_KEY, study.QUIZ_GRADING_VERSION, study.QUIZ_GRADING),
    PromptDefinition(study.SUMMARY_NOTES_KEY, study.SUMMARY_NOTES_VERSION, study.SUMMARY_NOTES),
    PromptDefinition(research.ANALYSIS_KEY, research.ANALYSIS_VERSION, research.ANALYSIS),
    PromptDefinition(research.WRITING_KEY, research.WRITING_VERSION, research.WRITING),
    PromptDefinition(knowledge.EXTRACT_KEY, knowledge.EXTRACT_VERSION, knowledge.EXTRACT),
    PromptDefinition(
        knowledge.MISCONCEPTION_KEY, knowledge.MISCONCEPTION_VERSION, knowledge.MISCONCEPTION
    ),
)


def active_prompt(prompt_key: str) -> PromptDefinition:
    versions = [p for p in PROMPTS if p.prompt_key == prompt_key]
    if not versions:
        raise KeyError(prompt_key)
    return max(versions, key=lambda p: p.version)
