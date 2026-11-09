"""Retrieval quality metrics (D-73, D-76). Pure functions: no I/O, no document text in results."""

from __future__ import annotations

from collections.abc import Sequence


def recall_at_k(ranked: Sequence[str], relevant: set[str], k: int) -> float:
    if not relevant:
        return 0.0
    return len(set(ranked[:k]) & relevant) / len(relevant)


def precision_at_k(ranked: Sequence[str], relevant: set[str], k: int) -> float:
    top = ranked[:k]
    return len([r for r in top if r in relevant]) / k if k else 0.0


def reciprocal_rank(ranked: Sequence[str], relevant: set[str]) -> float:
    for i, item in enumerate(ranked, start=1):
        if item in relevant:
            return 1.0 / i
    return 0.0


def summarise(runs: Sequence[tuple[Sequence[str], set[str]]], k: int) -> dict[str, float]:
    n = len(runs) or 1
    return {
        f"recall@{k}": sum(recall_at_k(r, rel, k) for r, rel in runs) / n,
        f"precision@{k}": sum(precision_at_k(r, rel, k) for r, rel in runs) / n,
        "mrr": sum(reciprocal_rank(r, rel) for r, rel in runs) / n,
    }
