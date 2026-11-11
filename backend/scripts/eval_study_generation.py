"""Measure the structure of the study materials one user already has (Phase 4 M8, spec 22).

READ ONLY: this script makes NO model call and costs nothing. Generate the materials first, either
on the FakeProvider (development, a pipeline check) or through the app on a real lecture with the
live provider (a person does that, within the app's own quotas), then run this to get the numbers:

  per material  items, share with a valid source reference, invalid references, duplicate rate,
                formulas flagged for review (counts only, never any content)
  per job type  jobs by outcome, safe error codes, average provider calls and duration

and a CSV with EMPTY columns for a person to score correctness, coverage and clarity. A script
cannot judge whether a summary is right; the blank columns are for a human.

  docker compose exec -T backend python scripts/eval_study_generation.py user@example.com \
      --out /tmp/study_eval.csv
  docker compose cp backend:/tmp/study_eval.csv docs/ai_eval/results/

Dollar cost is not computed here: read it from the usage page (`/ai/usage/summary`), which prices
each provider call. Output contains ids, types and counts only.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import func, select  # noqa: E402

from app.database.connection import AsyncSessionLocal  # noqa: E402
from app.models.flashcard import Flashcard, FlashcardSet  # noqa: E402
from app.models.generation_job import GenerationJob  # noqa: E402
from app.models.quiz import Quiz, QuizQuestion  # noqa: E402
from app.models.study_material import StudyMaterial  # noqa: E402
from app.models.user import User  # noqa: E402
from app.study.validation import find_duplicates  # noqa: E402

SCORING_COLUMNS = ["correctness", "coverage", "clarity", "usefulness", "reviewer_notes"]
COLUMNS = [
    "material_id",
    "resource_type",
    "version",
    "items",
    "items_with_refs",
    "ref_coverage",
    "invalid_refs",
    "duplicates",
    "duplicate_rate",
    "flagged",
    *SCORING_COLUMNS,
]

# resource type -> (payload list key, field used to find duplicates, field holding references)
PAYLOAD_ITEMS = {
    "summary": ("sections", "heading", "source_refs"),
    "study_guide": ("sections", "heading", "source_refs"),
    "glossary": ("terms", "term", "source_refs"),
    "formula_sheet": ("formulas", "expression", "source_refs"),
}


def measure(
    items: list[tuple[str, list[int]]], source_count: int, flagged: int = 0
) -> dict[str, Any]:
    """Counts only. A reference is valid when it names one of the material's own sources."""
    with_refs = sum(1 for _, refs in items if any(1 <= r <= source_count for r in refs))
    invalid = sum(1 for _, refs in items for r in refs if not 1 <= r <= source_count)
    dupes = len(find_duplicates([text for text, _ in items]))
    n = len(items)
    return {
        "items": n,
        "items_with_refs": with_refs,
        "ref_coverage": round(with_refs / n, 3) if n else "",
        "invalid_refs": invalid,
        "duplicates": dupes,
        "duplicate_rate": round(dupes / n, 3) if n else "",
        "flagged": flagged,
    }


async def material_items(db: Any, m: StudyMaterial) -> tuple[list[tuple[str, list[int]]], int]:
    """(text, refs) per item, and the number of items flagged for review."""
    payload = m.content.get("payload") or {}
    if m.resource_type in PAYLOAD_ITEMS:
        key, text_key, refs_key = PAYLOAD_ITEMS[m.resource_type]
        raw = payload.get(key) or []
        items = [(str(i.get(text_key, "")), list(i.get(refs_key) or [])) for i in raw]
        return items, sum(1 for i in raw if i.get("needs_review"))
    if m.resource_type == "question_bank":
        raw = payload.get("questions") or []
        return [(str(q.get("question", "")), list(q.get("source_refs") or [])) for q in raw], 0
    if m.resource_type == "flashcards":
        deck = (
            await db.execute(select(FlashcardSet).where(FlashcardSet.study_material_id == m.id))
        ).scalar_one_or_none()
        if deck is None:
            return [], 0
        cards = (
            (await db.execute(select(Flashcard).where(Flashcard.flashcard_set_id == deck.id)))
            .scalars()
            .all()
        )
        return [
            (c.front, [int(r.get("rank", 0)) for r in (c.source_references or [])]) for c in cards
        ], 0
    if m.resource_type == "quiz":
        quiz = (
            await db.execute(select(Quiz).where(Quiz.study_material_id == m.id))
        ).scalar_one_or_none()
        if quiz is None:
            return [], 0
        rows = (
            (await db.execute(select(QuizQuestion).where(QuizQuestion.quiz_id == quiz.id)))
            .scalars()
            .all()
        )
        return [
            (q.question, [int(r.get("rank", 0)) for r in (q.source_references or [])]) for q in rows
        ], 0
    return [], 0


async def main(email: str, out: Path) -> int:
    async with AsyncSessionLocal() as db:
        user = (
            await db.execute(select(User).where(func.lower(User.email) == email.lower()))
        ).scalar_one_or_none()
        if user is None:
            print("No such user.")
            return 1
        materials = (
            (
                await db.execute(
                    select(StudyMaterial)
                    .where(StudyMaterial.user_id == user.id)
                    .order_by(StudyMaterial.resource_type, StudyMaterial.created_at)
                )
            )
            .scalars()
            .all()
        )
        rows: list[dict[str, Any]] = []
        for m in materials:
            items, flagged = await material_items(db, m)
            sources = m.content.get("sources") or []
            rows.append(
                {
                    "material_id": str(m.id),
                    "resource_type": m.resource_type,
                    "version": m.current_version,
                    **measure(items, len(sources), flagged),
                    **{c: "" for c in SCORING_COLUMNS},
                }
            )
        jobs = (
            (await db.execute(select(GenerationJob).where(GenerationJob.user_id == user.id)))
            .scalars()
            .all()
        )
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    print(f"materials measured: {len(rows)}  ->  {out}")
    by_type: dict[str, list[GenerationJob]] = defaultdict(list)
    for j in jobs:
        by_type[j.generation_type].append(j)
    print("\njobs by type (validity = completed / finished):")
    for kind, group in sorted(by_type.items()):
        done = [j for j in group if j.status in ("completed", "failed")]
        ok = [j for j in group if j.status == "completed"]
        codes: dict[str, int] = defaultdict(int)
        for j in group:
            if j.error_code:
                codes[j.error_code] += 1
        secs = [
            (j.completed_at - j.started_at).total_seconds()
            for j in ok
            if j.completed_at and j.started_at
        ]
        validity = f"{len(ok) / len(done):.2f}" if done else "n/a"
        avg_calls = sum(j.provider_calls for j in group) / len(group)
        avg_secs = f"{sum(secs) / len(secs):.1f}s" if secs else "n/a"
        print(
            f"  {kind:14} jobs={len(group):3} validity={validity} "
            f"avg_provider_calls={avg_calls:.2f} avg_duration={avg_secs} errors={dict(codes)}"
        )
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("email")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args.email, args.out)))
