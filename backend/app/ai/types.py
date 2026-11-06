"""Provider-independent request/response types (Phase 2 spec 5.3, AI_ARCHITECTURE.md section 3).

Provider SDK objects never leave an adapter; everything crossing the boundary is one of these.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class Role(StrEnum):
    system = "system"
    user = "user"
    assistant = "assistant"
    tool = "tool"  # reserved, never produced in Phase 2


class FinishReason(StrEnum):
    stop = "stop"
    length = "length"
    content_filter = "content_filter"
    error = "error"
    other = "other"


class UsageSource(StrEnum):
    provider_reported = "provider_reported"
    estimated = "estimated"
    unavailable = "unavailable"


@dataclass(frozen=True, slots=True)
class Capabilities:
    """What a model supports. Missing features degrade explicitly (AI_ARCHITECTURE.md section 4)."""

    streaming: bool = False
    structured_output: bool = False
    usage_reporting: bool = False
    system_prompt: bool = False
    tool_calling: bool = False  # reserved, always false in Phase 2
    count_tokens: bool = False
    thinking_budget: bool = False

    def to_dict(self) -> dict[str, bool]:
        return {
            "streaming": self.streaming,
            "structured_output": self.structured_output,
            "usage_reporting": self.usage_reporting,
            "system_prompt": self.system_prompt,
            "tool_calling": self.tool_calling,
            "count_tokens": self.count_tokens,
            "thinking_budget": self.thinking_budget,
        }


@dataclass(frozen=True, slots=True)
class TimeoutPolicy:
    connect: float = 10
    generation: float = 60
    stream_inactivity: float = 30
    overall: float = 120


@dataclass(frozen=True, slots=True)
class LLMMessage:
    role: Role
    content: str


@dataclass(frozen=True, slots=True)
class LLMRequest:
    model: str  # provider model id
    messages: list[LLMMessage]  # user/assistant turns only, oldest first
    max_output_tokens: int
    system_prompt: str | None = None  # always separate from messages
    temperature: float | None = None
    timeouts: TimeoutPolicy = field(default_factory=TimeoutPolicy)
    thinking_budget: int | None = None
    request_tag: str = ""  # opaque id for logs; never sent to the provider


@dataclass(frozen=True, slots=True)
class Usage:
    """Token usage. Unknown values are None, never 0 (D-40)."""

    input_tokens: int | None = None
    output_tokens: int | None = None  # includes reasoning tokens when the model reports them
    reasoning_tokens: int | None = None  # the reasoning part of output_tokens
    source: UsageSource = UsageSource.unavailable

    @property
    def total_tokens(self) -> int | None:
        if self.input_tokens is None or self.output_tokens is None:
            return None
        return self.input_tokens + self.output_tokens


@dataclass(frozen=True, slots=True)
class LLMResponse:
    content: str
    model: str
    finish_reason: FinishReason
    usage: Usage = field(default_factory=Usage)
    provider_request_id: str | None = None


@dataclass(frozen=True, slots=True)
class StreamDelta:
    text: str
    # Cumulative usage the provider has reported so far, if any. Lets a cancelled stream keep the
    # figures it really received instead of guessing (D-40).
    usage: Usage | None = None


@dataclass(frozen=True, slots=True)
class StreamEnd:
    finish_reason: FinishReason
    usage: Usage = field(default_factory=Usage)
    provider_request_id: str | None = None


StreamEvent = StreamDelta | StreamEnd


@dataclass(frozen=True, slots=True)
class ProviderModelInfo:
    """One model a provider says the configured credentials can use (for list_llm_models.py)."""

    provider_model_id: str
    display_name: str | None = None
    supported_methods: tuple[str, ...] = ()
    input_token_limit: int | None = None
    output_token_limit: int | None = None
