"""Run the academic evaluation set (docs/ai_eval/questions.yaml) against the configured provider.

Purpose (spec 18): collect answers, latency, token usage and estimated cost for human review. This
script does NOT judge answer quality; the scoring columns are left blank for a person.

It sends real requests to the configured provider, so it costs money and uses your key. Two hard
caps stop it: --max-requests (every turn of every question is one request) and --max-total-tokens
(input + output tokens reported by the provider). It makes ONE attempt per request (no retries), so
the cap is a true upper bound on billed calls.

    docker compose exec backend python scripts/run_ai_eval.py --max-requests 15

The container does not mount docs/, so copy the question file in and the results out, e.g.
    docker compose cp docs/ai_eval/questions.yaml backend:/tmp/questions.yaml
    docker compose exec backend python scripts/run_ai_eval.py --questions /tmp/questions.yaml \
        --out /tmp/results.csv --max-requests 15
    docker compose cp backend:/tmp/results.csv docs/ai_eval/results/

The key is never printed. Answers go only to the results file, never to the console or logs.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import sys
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.ai.errors import LLMError, LLMNotConfiguredError  # noqa: E402
from app.ai.model_registry import build_registry  # noqa: E402
from app.ai.prompts.registry import active_prompt  # noqa: E402
from app.ai.providers.base import LLMProvider  # noqa: E402
from app.ai.providers.registry import get_provider  # noqa: E402
from app.ai.types import (  # noqa: E402
    LLMMessage,
    LLMRequest,
    Role,
    StreamDelta,
    StreamEnd,
    TimeoutPolicy,
    Usage,
)
from app.ai.usage.pricing import estimate_cost, find_price  # noqa: E402
from app.core.config import Settings, get_settings  # noqa: E402

DEFAULT_QUESTIONS = Path(__file__).resolve().parent.parent.parent / "docs/ai_eval/questions.yaml"
SCORING_COLUMNS = [
    "correctness",
    "relevance",
    "clarity",
    "hallucination",
    "instruction_following",
    "context_retention",
    "reviewer_notes",
]
COLUMNS = [
    "run_id",
    "run_at_utc",
    "provider",
    "model_id",
    "prompt_key",
    "prompt_version",
    "question_id",
    "subject",
    "kind",
    "turn",
    "turns_in_item",
    "question",
    "answer",
    "status",
    "error_code",
    "finish_reason",
    "time_to_first_token_s",
    "latency_s",
    "input_tokens",
    "output_tokens",
    "usage_source",
    "estimated_cost",
    "currency",
    *SCORING_COLUMNS,
]
UNKNOWN = "unknown"


@dataclass
class Item:
    id: str
    subject: str
    kind: str
    turns: list[str]


@dataclass
class Caps:
    max_requests: int
    max_total_tokens: int
    requests: int = 0
    tokens: int = 0
    stopped_by: str | None = field(default=None)

    def allow(self) -> bool:
        if self.requests >= self.max_requests:
            self.stopped_by = self.stopped_by or "max-requests"
            return False
        if self.tokens >= self.max_total_tokens:
            self.stopped_by = self.stopped_by or "max-total-tokens"
            return False
        return True


def load_items(path: Path) -> list[Item]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    items = [
        Item(
            id=str(q["id"]),
            subject=str(q["subject"]),
            kind=str(q["kind"]),
            turns=[str(t) for t in q["turns"]],
        )
        for q in data["questions"]
    ]
    ids = [i.id for i in items]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate question ids")
    if any(not i.turns for i in items):
        raise ValueError("every question needs at least one turn")
    return items


def select_items(items: list[Item], max_requests: int) -> list[Item]:
    """Pick items to fit the request budget, spreading across kinds then subjects.

    Deterministic: round-robin over question kinds (in file order), taking the next item whose
    subject has been used least, skipping any item whose turns no longer fit. When the budget
    covers everything, all items are returned in file order.
    """
    if sum(len(i.turns) for i in items) <= max_requests:
        return list(items)
    by_kind: dict[str, list[Item]] = defaultdict(list)
    for item in items:
        by_kind[item.kind].append(item)
    subject_use: dict[str, int] = defaultdict(int)
    chosen: list[Item] = []
    remaining = max_requests
    progressed = True
    while remaining > 0 and progressed:
        progressed = False
        for kind in list(by_kind):
            pool = [i for i in by_kind[kind] if len(i.turns) <= remaining]
            if not pool:
                continue
            pick = min(pool, key=lambda i: subject_use[i.subject])
            by_kind[kind].remove(pick)
            subject_use[pick.subject] += 1
            chosen.append(pick)
            remaining -= len(pick.turns)
            progressed = True
            if remaining <= 0:
                break
    order = {i.id: n for n, i in enumerate(items)}
    return sorted(chosen, key=lambda i: order[i.id])


def _timeouts(s: Settings) -> TimeoutPolicy:
    return TimeoutPolicy(
        connect=s.llm_connect_timeout_seconds,
        generation=s.llm_generation_timeout_seconds,
        stream_inactivity=s.llm_stream_inactivity_timeout_seconds,
        overall=s.llm_overall_timeout_seconds,
    )


async def _one_turn(
    provider: LLMProvider, request: LLMRequest
) -> tuple[str, float | None, float, Any, Usage]:
    started = time.monotonic()
    first: float | None = None
    text = ""
    finish: Any = None
    usage = Usage()
    async for event in provider.stream(request):
        if isinstance(event, StreamDelta):
            if first is None:
                first = time.monotonic() - started
            text += event.text
        elif isinstance(event, StreamEnd):
            finish, usage = event.finish_reason, event.usage
    return text, first, time.monotonic() - started, finish, usage


async def run_eval(
    settings: Settings,
    items: list[Item],
    caps: Caps,
    *,
    provider: LLMProvider | None = None,
    progress: Any = print,
) -> list[dict[str, Any]]:
    registry = build_registry(settings)
    if not registry.configured or registry.provider is None:
        raise LLMNotConfiguredError()
    model = registry.default
    prompt = active_prompt("academic_tutor")
    own_provider = provider is None
    provider = provider or get_provider(registry.provider, settings)
    run_id = uuid.uuid4().hex[:12]
    run_at = datetime.now(UTC).isoformat(timespec="seconds")
    price = find_price(registry.provider, model.provider_model_id)
    rows: list[dict[str, Any]] = []
    try:
        for item in items:
            history: list[LLMMessage] = []
            for n, question in enumerate(item.turns, start=1):
                row: dict[str, Any] = dict.fromkeys(COLUMNS, "")
                row.update(
                    run_id=run_id,
                    run_at_utc=run_at,
                    provider=registry.provider,
                    model_id=model.provider_model_id,
                    prompt_key=prompt.prompt_key,
                    prompt_version=prompt.version,
                    question_id=item.id,
                    subject=item.subject,
                    kind=item.kind,
                    turn=n,
                    turns_in_item=len(item.turns),
                    question=question,
                )
                if not caps.allow():
                    row.update(status="skipped_cap", error_code=caps.stopped_by)
                    rows.append(row)
                    break  # later turns would lack their context; skip the rest of this item
                caps.requests += 1
                history.append(LLMMessage(Role.user, question))
                request = LLMRequest(
                    model=model.provider_model_id,
                    system_prompt=prompt.content,
                    messages=list(history),
                    max_output_tokens=settings.llm_max_output_tokens,
                    thinking_budget=settings.llm_thinking_budget,
                    timeouts=_timeouts(settings),
                    request_tag=f"eval-{run_id}-{item.id}-{n}",
                )
                try:
                    text, ttft, total, finish, usage = await _one_turn(provider, request)
                except LLMError as exc:
                    row.update(status="failed", error_code=exc.code)
                    rows.append(row)
                    progress(f"{item.id} turn {n}: FAILED {exc.code}")
                    break  # a failed turn leaves no answer to build the follow-up on
                tokens = (usage.input_tokens or 0) + (usage.output_tokens or 0)
                caps.tokens += tokens
                cost = estimate_cost(price, usage)
                row.update(
                    answer=text,
                    status="ok",
                    finish_reason=str(finish),
                    time_to_first_token_s=f"{ttft:.2f}" if ttft is not None else UNKNOWN,
                    latency_s=f"{total:.2f}",
                    input_tokens=usage.input_tokens if usage.input_tokens is not None else UNKNOWN,
                    output_tokens=(
                        usage.output_tokens if usage.output_tokens is not None else UNKNOWN
                    ),
                    usage_source=str(usage.source),
                    estimated_cost=str(cost) if cost is not None else UNKNOWN,
                    currency=price.currency if price and cost is not None else "",
                )
                rows.append(row)
                history.append(LLMMessage(Role.assistant, text))
                progress(
                    f"{item.id} turn {n}: ok  {total:.1f}s  "
                    f"in={row['input_tokens']} out={row['output_tokens']}"
                )
    finally:
        if own_provider:
            await provider.aclose()
    return rows


def write_results(rows: list[dict[str, Any]], out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8-sig") as f:  # BOM so Excel reads UTF-8
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    mid = len(ordered) // 2
    return ordered[mid] if len(ordered) % 2 else (ordered[mid - 1] + ordered[mid]) / 2


def summarise(rows: list[dict[str, Any]], caps: Caps) -> str:
    ok = [r for r in rows if r["status"] == "ok"]
    failed = [r for r in rows if r["status"] == "failed"]
    skipped = [r for r in rows if r["status"] == "skipped_cap"]
    lat = [float(r["latency_s"]) for r in ok]
    ttft = [float(r["time_to_first_token_s"]) for r in ok if r["time_to_first_token_s"] != UNKNOWN]
    known_tokens = [
        int(r[k]) for r in ok for k in ("input_tokens", "output_tokens") if r[k] != UNKNOWN
    ]
    costs = [r["estimated_cost"] for r in ok]
    lines = [
        f"Requests sent: {caps.requests} (cap {caps.max_requests})",
        f"Succeeded: {len(ok)}   Failed: {len(failed)}   Skipped by cap: {len(skipped)}",
        f"Tokens reported: {caps.tokens} (cap {caps.max_total_tokens}); "
        f"{len(known_tokens)} figures known",
    ]
    if lat:
        lines.append(
            f"Latency: median {_median(lat):.2f}s, max {max(lat):.2f}s, "
            f"mean {sum(lat) / len(lat):.2f}s"
        )
    if ttft:
        lines.append(f"Time to first token: median {_median(ttft):.2f}s, max {max(ttft):.2f}s")
    if ok and all(c == UNKNOWN for c in costs):
        lines.append("Cost: unknown (no verified price for this model in the pricing registry)")
    elif ok:
        known = [c for c in costs if c != UNKNOWN]
        lines.append(f"Cost: {len(known)} of {len(ok)} requests priced")
    if caps.stopped_by:
        lines.append(f"Stopped early by cap: {caps.stopped_by}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--questions", type=Path, default=DEFAULT_QUESTIONS)
    parser.add_argument("--out", type=Path, default=None, help="results CSV path")
    parser.add_argument("--max-requests", type=int, default=15, help="hard cap on provider calls")
    parser.add_argument(
        "--max-total-tokens", type=int, default=60_000, help="hard cap on reported tokens"
    )
    parser.add_argument("--dry-run", action="store_true", help="show the selection, send nothing")
    args = parser.parse_args(argv)
    if args.max_requests < 1 or args.max_total_tokens < 1:
        parser.error("caps must be positive")

    items = load_items(args.questions)
    chosen = select_items(items, args.max_requests)
    requests_planned = sum(len(i.turns) for i in chosen)
    print(
        f"Questions in file: {len(items)}; selected {len(chosen)} "
        f"({requests_planned} requests, cap {args.max_requests})"
    )
    print("Selected: " + ", ".join(i.id for i in chosen))
    if args.dry_run:
        return 0

    settings = get_settings()
    caps = Caps(max_requests=args.max_requests, max_total_tokens=args.max_total_tokens)
    try:
        rows = asyncio.run(run_eval(settings, chosen, caps))
    except LLMNotConfiguredError:
        print(
            "No AI provider is configured. Set LLM_PROVIDER, LLM_DEFAULT_MODEL and the provider "
            "key in your local .env, then restart the backend."
        )
        return 2
    out = args.out or Path(f"ai_eval_{datetime.now(UTC):%Y%m%d_%H%M%S}.csv")
    write_results(rows, out)
    print(summarise(rows, caps))
    print(f"Results written to {out} (scoring columns are blank for the human reviewer)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
