from ingest import repository as repo
from retrieval.vector_search import buscar_por_similitud


def _vector_con_uno_en(posicion: int, dimension: int = 1536) -> list[float]:
    vector = [0.0] * dimension
    vector[posicion] = 1.0
    return vector


def test_buscar_por_similitud_ordena_por_cercania_coseno(db_conn, clean_db):
    organismo_id = repo.upsert_organismo(db_conn, "Registro Civil")
    repo.upsert_tramite(db_conn, "RC-0001", organismo_id, "Actas", "Actas Regulares")

    chunks = [
        {"tipo_chunk": "descripcion", "texto": "chunk cercano", "fuente_url": None},
        {"tipo_chunk": "descripcion", "texto": "chunk lejano", "fuente_url": None},
    ]
    embeddings = [_vector_con_uno_en(0), _vector_con_uno_en(1)]
    repo.insert_version_with_chunks(
        db_conn, "RC-0001", 1, "hash-1", {"id": "RC-0001"}, chunks, embeddings
    )
    db_conn.commit()

    query_embedding = _vector_con_uno_en(0)

    resultados = buscar_por_similitud(db_conn, query_embedding, top_n=10)

    assert len(resultados) == 2
    assert resultados[0]["texto"] == "chunk cercano"
    assert resultados[1]["texto"] == "chunk lejano"
    assert resultados[0]["tramite_id"] == "RC-0001"
    assert resultados[0]["organismo"] == "Registro Civil"
    assert resultados[0]["categoria"] == "Actas"
    assert resultados[0]["nombre_oficial"] == "Actas Regulares"
    assert resultados[0]["tipo_chunk"] == "descripcion"


def test_respeta_top_n(db_conn, clean_db):
    organismo_id = repo.upsert_organismo(db_conn, "Registro Civil")
    repo.upsert_tramite(db_conn, "RC-0001", organismo_id, "Actas", "Actas Regulares")

    chunks = [
        {"tipo_chunk": "descripcion", "texto": f"chunk {i}", "fuente_url": None} for i in range(5)
    ]
    embeddings = [_vector_con_uno_en(i % 1536) for i in range(5)]
    repo.insert_version_with_chunks(
        db_conn, "RC-0001", 1, "hash-1", {"id": "RC-0001"}, chunks, embeddings
    )
    db_conn.commit()

    resultados = buscar_por_similitud(db_conn, _vector_con_uno_en(0), top_n=2)

    assert len(resultados) == 2
