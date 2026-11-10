"""In-code prompt catalogue. The highest version per key is the active one."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from app.ai.prompts import academic_tutor, rag, study


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
)


def active_prompt(prompt_key: str) -> PromptDefinition:
    versions = [p for p in PROMPTS if p.prompt_key == prompt_key]
    if not versions:
        raise KeyError(prompt_key)
    return max(versions, key=lambda p: p.version)
