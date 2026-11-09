"""Evaluate embedding retrieval on a corpus generated in code (D-76) and print score statistics
for threshold calibration. Prints metrics and score ranges only, never text.

  docker compose exec -e EMBEDDING_PROVIDER=gemini -e EMBEDDING_MODEL=<id> backend \
      python scripts/eval_retrieval.py
"""

import asyncio
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import get_settings  # noqa: E402
from app.embeddings.registry import get_embedding_provider  # noqa: E402
from app.retrieval.evaluation import summarise  # noqa: E402

# topic -> (passages, queries). Original text written for this evaluation.
CORPUS: dict[str, tuple[list[str], list[str]]] = {
    "photosynthesis": (
        [
            "Plants capture sunlight in chloroplasts and turn it into sugar and oxygen.",
            "The light reactions split water and produce ATP and NADPH on thylakoid membranes.",
        ],
        ["How do plants make food from light?", "Where do the light reactions happen?"],
    ),
    "krebs": (
        [
            "The citric acid cycle oxidises acetyl-CoA inside the mitochondrial matrix.",
            "Each turn of the cycle yields NADH, FADH2 and one GTP.",
        ],
        [
            "What happens to acetyl-CoA in mitochondria?",
            "Which carriers does the Krebs cycle make?",
        ],
    ),
    "rome": (
        [
            "Augustus ended the Roman Republic and became the first emperor in 27 BC.",
            "Civil wars between generals weakened the Senate before the empire began.",
        ],
        ["Who was the first Roman emperor?", "Why did the Republic collapse?"],
    ),
    "interest": (
        [
            "Compound interest adds earned interest to the principal so growth accelerates.",
            "Simple interest is calculated only on the original principal amount.",
        ],
        ["How does compounding make savings grow faster?", "What is simple interest?"],
    ),
    "tcp": (
        [
            "TCP uses a three-way handshake to establish a reliable connection.",
            "Congestion control lowers the sending rate when packets are dropped.",
        ],
        ["How does a TCP connection start?", "What does congestion control do?"],
    ),
}
OFF_TOPIC = ["What is the best recipe for sourdough bread?", "Who won the last football world cup?"]
K = 3


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    return dot / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)))


async def main() -> int:
    s = get_settings()
    provider = get_embedding_provider(s)
    passages = [(t, i) for t, (ps, _) in CORPUS.items() for i, _p in enumerate(ps)]
    texts = [CORPUS[t][0][i] for t, i in passages]
    ids = [f"{t}:{i}" for t, i in passages]
    docs = await provider.embed(
        texts,
        task="document",
        model=s.embedding_model,
        dimensions=s.embedding_dimensions,
        timeout=60,
    )
    queries = [(t, q) for t, (_, qs) in CORPUS.items() for q in qs]
    q_text = [q for _, q in queries] + OFF_TOPIC
    qv = await provider.embed(
        q_text, task="query", model=s.embedding_model, dimensions=s.embedding_dimensions, timeout=60
    )
    runs: list[tuple[list[str], set[str]]] = []
    relevant_scores: list[float] = []
    irrelevant_best: list[float] = []
    for (topic, _), vec in zip(queries, qv.vectors, strict=False):
        scored = sorted(
            ((cosine(vec, d), pid) for d, pid in zip(docs.vectors, ids, strict=True)), reverse=True
        )
        rel = {pid for pid in ids if pid.startswith(topic + ":")}
        runs.append(([p for _, p in scored], rel))
        relevant_scores += [sc for sc, p in scored if p in rel]
        irrelevant_best.append(max(sc for sc, p in scored if p not in rel))
    off_best = [max(cosine(vec, d) for d in docs.vectors) for vec in qv.vectors[len(queries) :]]
    print(
        f"model={docs.model} dims={s.embedding_dimensions} "
        f"passages={len(ids)} queries={len(queries)}"
    )
    for k, v in summarise(runs, K).items():
        print(f"{k}: {v:.3f}")
    print(f"relevant score  min={min(relevant_scores):.3f} max={max(relevant_scores):.3f}")
    print(f"best irrelevant min={min(irrelevant_best):.3f} max={max(irrelevant_best):.3f}")
    print(f"off-topic best  min={min(off_best):.3f} max={max(off_best):.3f}")
    print(f"configured retrieval_min_vector_score={s.retrieval_min_vector_score}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
