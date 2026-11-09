from app.retrieval.evaluation import precision_at_k, recall_at_k, reciprocal_rank, summarise


def test_metrics():
    ranked = ["a", "b", "c", "d"]
    assert recall_at_k(ranked, {"a", "c", "z"}, 3) == 2 / 3
    assert precision_at_k(ranked, {"a", "c"}, 4) == 0.5
    assert reciprocal_rank(ranked, {"c"}) == 1 / 3
    assert reciprocal_rank(ranked, {"zzz"}) == 0.0
    assert recall_at_k(ranked, set(), 3) == 0.0
    s = summarise([(ranked, {"a"}), (ranked, {"b"})], 1)
    assert s["recall@1"] == 0.5 and s["mrr"] == 0.75
