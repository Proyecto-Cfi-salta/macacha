from ingest import repository as repo
from agent.admin import tramites_repository


def test_listar_tramites_devuelve_resumen(db_conn, clean_db):
    organismo_id = repo.upsert_organismo(db_conn, "Registro Civil")
    repo.upsert_tramite(db_conn, "RC-0001", organismo_id, "Actas", "Actas Regulares")
    snapshot = {
        "id": "RC-0001",
        "organismo": "Registro Civil",
        "categoria": "Actas",
        "nombre_oficial": "Actas Regulares",
        "requisitos": ["DNI"],
        "telefono_contacto": "",
        "email_contacto": "",
    }
    chunks = [{"tipo_chunk": "descripcion", "texto": "texto", "fuente_url": None}]
    embeddings = [[0.0] * 1536]
    repo.insert_version_with_chunks(db_conn, "RC-0001", 1, "hash-1", snapshot, chunks, embeddings)
    db_conn.commit()

    tramites = tramites_repository.listar_tramites(db_conn)

    assert tramites == [
        {
            "id": "RC-0001",
            "nombre_oficial": "Actas Regulares",
            "organismo": "Registro Civil",
            "categoria": "Actas",
            "veces_consultado": 0,
            "numero_version": 1,
        }
    ]


def test_listar_organismos_devuelve_nombres_ordenados(db_conn, clean_db):
    repo.upsert_organismo(db_conn, "Registro Civil")
    repo.upsert_organismo(db_conn, "Dirección de Rentas")
    db_conn.commit()

    assert tramites_repository.listar_organismos(db_conn) == [
        "Dirección de Rentas",
        "Registro Civil",
    ]


def test_obtener_chunks_por_version_incluye_embedding(db_conn, clean_db):
    organismo_id = repo.upsert_organismo(db_conn, "Registro Civil")
    repo.upsert_tramite(db_conn, "RC-0001", organismo_id, "Actas", "Actas Regulares")
    snapshot = {
        "id": "RC-0001",
        "organismo": "Registro Civil",
        "categoria": "Actas",
        "nombre_oficial": "Actas Regulares",
        "requisitos": ["DNI"],
        "telefono_contacto": "",
        "email_contacto": "",
    }
    chunks = [{"tipo_chunk": "descripcion", "texto": "texto descriptivo", "fuente_url": None}]
    embeddings = [[0.1] * 1536]
    version_id = repo.insert_version_with_chunks(
        db_conn, "RC-0001", 1, "hash-1", snapshot, chunks, embeddings
    )
    db_conn.commit()

    chunks_obtenidos = tramites_repository.obtener_chunks_por_version(db_conn, version_id)

    assert len(chunks_obtenidos) == 1
    assert chunks_obtenidos[0]["tipo_chunk"] == "descripcion"
    assert chunks_obtenidos[0]["texto"] == "texto descriptivo"
    assert list(chunks_obtenidos[0]["embedding"][:3]) == [0.1, 0.1, 0.1]
