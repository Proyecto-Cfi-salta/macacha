def chunk_desde_fila(row: tuple) -> dict:
    chunk_id, tramite_id, nombre_oficial, categoria, organismo, tipo_chunk, texto, fuente_url = row
    return {
        "chunk_id": str(chunk_id),
        "tramite_id": tramite_id,
        "nombre_oficial": nombre_oficial,
        "categoria": categoria,
        "organismo": organismo,
        "tipo_chunk": tipo_chunk,
        "texto": texto,
        "fuente_url": fuente_url,
    }
