from ingest import repository as repo
from retrieval.hybrid_search import buscar_chunks


def _fake_embed_fn(texts):
    return [[0.0] * 1536 for _ in texts]


def test_buscar_chunks_aplica_el_orden_de_rerank_fn_y_recorta_a_top_k(db_conn, clean_db):
    organismo_id = repo.upsert_organismo(db_conn, "Registro Civil")
    repo.upsert_tramite(db_conn, "RC-0001", organismo_id, "Actas", "Actas Regulares")

    chunks = [
        {"tipo_chunk": "descripcion", "texto": "chunk sobre actas uno", "fuente_url": None},
        {"tipo_chunk": "descripcion", "texto": "chunk sobre actas dos", "fuente_url": None},
        {"tipo_chunk": "descripcion", "texto": "chunk sobre actas tres", "fuente_url": None},
    ]
    embeddings = [[0.0] * 1536, [0.0] * 1536, [0.0] * 1536]
    repo.insert_version_with_chunks(
        db_conn, "RC-0001", 1, "hash-1", {"id": "RC-0001"}, chunks, embeddings
    )
    db_conn.commit()

    candidatos_recibidos = []

    def rerank_fn_invierte_orden(query, candidatos):
        candidatos_recibidos.extend(candidatos)
        return list(reversed(range(len(candidatos))))

    resultados = buscar_chunks(
        "actas", db_conn, _fake_embed_fn, rerank_fn_invierte_orden, top_k=2
    )

    esperado = list(reversed(candidatos_recibidos))[:2]
    assert resultados == esperado
    assert len(resultados) == 2


def test_buscar_chunks_ignora_indices_fuera_de_rango_del_rerank_fn(db_conn, clean_db):
    organismo_id = repo.upsert_organismo(db_conn, "Registro Civil")
    repo.upsert_tramite(db_conn, "RC-0001", organismo_id, "Actas", "Actas Regulares")

    chunks = [
        {"tipo_chunk": "descripcion", "texto": "chunk sobre actas uno", "fuente_url": None},
        {"tipo_chunk": "descripcion", "texto": "chunk sobre actas dos", "fuente_url": None},
    ]
    embeddings = [[0.0] * 1536, [0.0] * 1536]
    repo.insert_version_with_chunks(
        db_conn, "RC-0001", 1, "hash-1", {"id": "RC-0001"}, chunks, embeddings
    )
    db_conn.commit()

    def rerank_fn_con_indices_invalidos(query, candidatos):
        return [5, 0, -1, 1]

    resultados = buscar_chunks(
        "actas", db_conn, _fake_embed_fn, rerank_fn_con_indices_invalidos, top_k=5
    )

    assert len(resultados) == 2


def test_buscar_chunks_usa_embed_fn_para_la_query(db_conn, clean_db):
    organismo_id = repo.upsert_organismo(db_conn, "Registro Civil")
    repo.upsert_tramite(db_conn, "RC-0001", organismo_id, "Actas", "Actas Regulares")

    chunks = [{"tipo_chunk": "descripcion", "texto": "chunk sobre actas", "fuente_url": None}]
    embeddings = [[0.0] * 1536]
    repo.insert_version_with_chunks(
        db_conn, "RC-0001", 1, "hash-1", {"id": "RC-0001"}, chunks, embeddings
    )
    db_conn.commit()

    llamadas_embed = []

    def embed_fn_espia(texts):
        llamadas_embed.append(texts)
        return [[0.0] * 1536 for _ in texts]

    def rerank_fn_identidad(query, candidatos):
        return list(range(len(candidatos)))

    buscar_chunks("actas", db_conn, embed_fn_espia, rerank_fn_identidad, top_k=5)

    assert llamadas_embed == [["actas"]]
