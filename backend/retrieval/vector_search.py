from retrieval.chunk_result import chunk_desde_fila


def buscar_por_similitud(conn, query_embedding: list[float], top_n: int = 20) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT tc.id, t.id, t.nombre_oficial, t.categoria, o.nombre,
                   tc.tipo_chunk, tc.texto, tc.fuente_url
            FROM tramite_chunks tc
            JOIN tramite_versiones tv ON tv.id = tc.version_id AND tv.es_vigente = true
            JOIN tramites t ON t.id = tv.tramite_id
            JOIN organismos o ON o.id = t.organismo_id
            ORDER BY tc.embedding <=> %s::vector
            LIMIT %s
            """,
            (query_embedding, top_n),
        )
        return [chunk_desde_fila(row) for row in cur.fetchall()]
