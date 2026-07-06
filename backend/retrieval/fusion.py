def fusionar_rrf(ranking_vectorial: list[dict], ranking_textual: list[dict], k: int = 60) -> list[dict]:
    scores: dict[str, float] = {}
    chunks_por_id: dict[str, dict] = {}

    for ranking in (ranking_vectorial, ranking_textual):
        for posicion, chunk in enumerate(ranking, start=1):
            chunk_id = chunk["chunk_id"]
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1 / (k + posicion)
            chunks_por_id[chunk_id] = chunk

    orden = sorted(scores.keys(), key=lambda chunk_id: scores[chunk_id], reverse=True)
    return [chunks_por_id[chunk_id] for chunk_id in orden]
