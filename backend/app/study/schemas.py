"""Engine-level request model (spec 4.2). The API layer reuses these; generators add their own
validated settings model (spec 4.2)."""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

SourceType = Literal["document", "documents", "chapter", "subject", "folder", "workspace", "text"]
MAX_DOCUMENT_IDS = 20


def clean_text(value: str) -> str:
    """Drop control characters (keep newline and tab) from model or user text before storing it."""
    return "".join(ch for ch in value if ch in "\n\t" or ch >= " " and ch != "\x7f").strip()


CleanStr = Annotated[str, AfterValidator(clean_text)]


class SourceSpec(BaseModel):
    """What to generate from. Ids are verified in the backend (ScopeResolver); a foreign id is a
    404 exactly like a missing one."""

    model_config = ConfigDict(extra="forbid")

    type: SourceType
    id: uuid.UUID | None = None
    ids: list[uuid.UUID] | None = Field(default=None, max_length=MAX_DOCUMENT_IDS)
    # Only for type="text": a pasted passage. It needs a workspace to live in.
    text: str | None = Field(default=None, min_length=1, max_length=200_000)
    workspace_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _shape(self) -> SourceSpec:
        has = {"id": self.id is not None, "ids": bool(self.ids), "text": self.text is not None}
        want = {
            "document": "id",
            "chapter": "id",
            "subject": "id",
            "folder": "id",
            "workspace": "id",
            "documents": "ids",
            "text": "text",
        }[self.type]
        if not has[want] or any(v for k, v in has.items() if k != want):
            raise ValueError(f"source type {self.type!r} needs exactly '{want}'")
        if self.type == "text" and self.workspace_id is None:
            raise ValueError("a text source needs workspace_id")
        if self.type != "text" and self.workspace_id is not None:
            raise ValueError("workspace_id is only for text sources")
        return self

    def canonical(self) -> dict[str, Any]:
        """Order-independent form used for the request fingerprint. Text is hashed, not stored."""
        out: dict[str, Any] = {"type": self.type}
        if self.id is not None:
            out["id"] = str(self.id)
        if self.ids:
            out["ids"] = sorted({str(i) for i in self.ids})
        if self.text is not None:
            out["text_sha256"] = hashlib.sha256(self.text.encode("utf-8")).hexdigest()
            out["workspace_id"] = str(self.workspace_id)
        return out


class GenerationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    generation_type: str = Field(min_length=1, max_length=32, pattern=r"^[a-z_]+$")
    source: SourceSpec
    settings: dict[str, Any] = Field(default_factory=dict)


def fingerprint(
    user_id: uuid.UUID, generation_type: str, source: SourceSpec, settings: dict[str, Any]
) -> str:
    """Identical requests by one user share a fingerprint, so a second identical request while
    one is active returns the active job instead of paying for another generation (D-87)."""
    payload = {
        "u": str(user_id),
        "t": generation_type,
        "s": source.canonical(),
        "c": settings,
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()
