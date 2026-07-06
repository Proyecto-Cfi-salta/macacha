from retrieval.fulltext_search import buscar_por_texto
from retrieval.fusion import fusionar_rrf
from retrieval.vector_search import buscar_por_similitud


def buscar_chunks(query: str, conn, embed_fn, rerank_fn, top_k: int = 5) -> list[dict]:
    query_embedding = embed_fn([query])[0]

    ranking_vectorial = buscar_por_similitud(conn, query_embedding, top_n=20)
    ranking_textual = buscar_por_texto(conn, query, top_n=20)
    fusionados = fusionar_rrf(ranking_vectorial, ranking_textual)

    orden = rerank_fn(query, fusionados)
    reordenados = [fusionados[i] for i in orden]

    return reordenados[:top_k]
