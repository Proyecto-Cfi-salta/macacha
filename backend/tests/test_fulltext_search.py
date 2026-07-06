from ingest import repository as repo
from retrieval.fulltext_search import buscar_por_texto


def test_buscar_por_texto_encuentra_por_relevancia(db_conn, clean_db):
    organismo_id = repo.upsert_organismo(db_conn, "Registro Civil")
    repo.upsert_tramite(db_conn, "RC-0001", organismo_id, "Actas", "Actas Regulares")

    chunks = [
        {
            "tipo_chunk": "descripcion",
            "texto": "Trámite para solicitar un acta de nacimiento en Salta.",
            "fuente_url": None,
        },
        {
            "tipo_chunk": "descripcion",
            "texto": "Trámite para renovar el pasaporte argentino.",
            "fuente_url": None,
        },
    ]
    embeddings = [[0.0] * 1536, [0.0] * 1536]
    repo.insert_version_with_chunks(
        db_conn, "RC-0001", 1, "hash-1", {"id": "RC-0001"}, chunks, embeddings
    )
    db_conn.commit()

    resultados = buscar_por_texto(db_conn, "acta de nacimiento", top_n=10)

    assert len(resultados) == 1
    assert resultados[0]["texto"] == "Trámite para solicitar un acta de nacimiento en Salta."


def test_sin_coincidencias_devuelve_lista_vacia(db_conn, clean_db):
    organismo_id = repo.upsert_organismo(db_conn, "Registro Civil")
    repo.upsert_tramite(db_conn, "RC-0001", organismo_id, "Actas", "Actas Regulares")

    chunks = [{"tipo_chunk": "descripcion", "texto": "Trámite para renovar el pasaporte.", "fuente_url": None}]
    embeddings = [[0.0] * 1536]
    repo.insert_version_with_chunks(
        db_conn, "RC-0001", 1, "hash-1", {"id": "RC-0001"}, chunks, embeddings
    )
    db_conn.commit()

    resultados = buscar_por_texto(db_conn, "matrimonio civil", top_n=10)

    assert resultados == []
