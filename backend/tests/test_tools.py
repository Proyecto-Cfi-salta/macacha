from ingest import repository as repo
from agent import tools


def _fake_embed_fn(texts):
    return [[0.0] * 1536 for _ in texts]


def _fake_rerank_fn(query, candidatos):
    return list(range(len(candidatos)))


def _armar_tramite_de_prueba(conn):
    organismo_id = repo.upsert_organismo(conn, "Registro Civil")
    repo.upsert_tramite(conn, "RC-0001", organismo_id, "Actas", "Actas Regulares")
    snapshot = {
        "id": "RC-0001",
        "nombre_oficial": "Actas Regulares",
        "requisitos": ["DNI"],
        "costo": "$6000",
        "modalidad": "Online",
        "duracion": "10 días",
        "pasos": ["Paso 1"],
        "objetivo": "Objetivo de prueba",
        "descripcion": "Descripción de prueba",
        "enlaces_oficiales": ["https://registrocivilsalta.gob.ar/"],
        "problemas_frecuentes": ["Problema 1"],
    }
    chunks = [
        {"tipo_chunk": "descripcion", "texto": "Actas Regulares de Salta", "fuente_url": "https://x"}
    ]
    embeddings = [[0.0] * 1536]
    repo.insert_version_with_chunks(conn, "RC-0001", 1, "hash-1", snapshot, chunks, embeddings)
    conn.commit()


def test_buscar_tramite_dedupe_por_tramite_id(db_conn, clean_db):
    _armar_tramite_de_prueba(db_conn)

    resultados = tools.buscar_tramite(db_conn, _fake_embed_fn, _fake_rerank_fn, "actas")

    assert resultados == [
        {
            "tramite_id": "RC-0001",
            "nombre_oficial": "Actas Regulares",
            "categoria": "Actas",
            "organismo": "Registro Civil",
        }
    ]


def test_obtener_requisitos(db_conn, clean_db):
    _armar_tramite_de_prueba(db_conn)
    assert tools.obtener_requisitos(db_conn, "RC-0001") == ["DNI"]


def test_obtener_requisitos_tramite_inexistente(db_conn, clean_db):
    assert tools.obtener_requisitos(db_conn, "NO-EXISTE") == []


def test_obtener_costos_modalidad(db_conn, clean_db):
    _armar_tramite_de_prueba(db_conn)
    assert tools.obtener_costos_modalidad(db_conn, "RC-0001") == {
        "costo": "$6000",
        "modalidad": "Online",
        "duracion": "10 días",
    }


def test_obtener_pasos(db_conn, clean_db):
    _armar_tramite_de_prueba(db_conn)
    assert tools.obtener_pasos(db_conn, "RC-0001") == ["Paso 1"]


def test_obtener_normativa(db_conn, clean_db):
    _armar_tramite_de_prueba(db_conn)
    assert tools.obtener_normativa(db_conn, "RC-0001") == {
        "objetivo": "Objetivo de prueba",
        "descripcion": "Descripción de prueba",
    }


def test_obtener_formularios_enlaces(db_conn, clean_db):
    _armar_tramite_de_prueba(db_conn)
    assert tools.obtener_formularios_enlaces(db_conn, "RC-0001") == [
        "https://registrocivilsalta.gob.ar/"
    ]


def test_obtener_problemas_frecuentes(db_conn, clean_db):
    _armar_tramite_de_prueba(db_conn)
    assert tools.obtener_problemas_frecuentes(db_conn, "RC-0001") == ["Problema 1"]


def test_ejecutar_tool_despacha_buscar_tramite(db_conn, clean_db):
    _armar_tramite_de_prueba(db_conn)

    resultado = tools.ejecutar_tool(
        "buscar_tramite", {"query": "actas"}, db_conn, _fake_embed_fn, _fake_rerank_fn
    )

    assert resultado[0]["tramite_id"] == "RC-0001"


def test_ejecutar_tool_despacha_obtener_requisitos(db_conn, clean_db):
    _armar_tramite_de_prueba(db_conn)

    resultado = tools.ejecutar_tool(
        "obtener_requisitos", {"tramite_id": "RC-0001"}, db_conn, _fake_embed_fn, _fake_rerank_fn
    )

    assert resultado == ["DNI"]


def test_tool_schemas_tiene_los_7_nombres_esperados():
    nombres = {schema["function"]["name"] for schema in tools.TOOL_SCHEMAS}
    assert nombres == {
        "buscar_tramite",
        "obtener_requisitos",
        "obtener_costos_modalidad",
        "obtener_pasos",
        "obtener_normativa",
        "obtener_formularios_enlaces",
        "obtener_problemas_frecuentes",
    }
