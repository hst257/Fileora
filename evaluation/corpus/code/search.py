def reciprocal_rank_fusion(rankings, constant=60):
    """Combine lexical and semantic retrieval by reciprocal ranks."""
    scores = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking, 1):
            scores[item] = scores.get(item, 0) + 1 / (constant + rank)
    return sorted(scores, key=scores.get, reverse=True)
