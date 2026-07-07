import uuid

from ingest import repository as repo


def test_upsert_organismo_returns_same_id_on_conflict(db_conn, clean_db):
    id1 = repo.upsert_organismo(db_conn, "Registro Civil")
    id2 = repo.upsert_organismo(db_conn, "Registro Civil")
    db_conn.commit()

    assert id1 == id2


def test_get_vigente_version_is_none_without_versions(db_conn, clean_db):
    organismo_id = repo.upsert_organismo(db_conn, "Registro Civil")
    repo.upsert_tramite(db_conn, "RC-0001", organismo_id, "Actas", "Actas Regulares")
    db_conn.commit()

    assert repo.get_vigente_version(db_conn, "RC-0001") is None


def test_insert_version_with_chunks_and_read_it_back(db_conn, clean_db):
    organismo_id = repo.upsert_organismo(db_conn, "Registro Civil")
    repo.upsert_tramite(db_conn, "RC-0001", organismo_id, "Actas", "Actas Regulares")

    chunks = [{"tipo_chunk": "descripcion", "texto": "texto de prueba", "fuente_url": None}]
    embeddings = [[0.1] * 1536]

    version_id = repo.insert_version_with_chunks(
        db_conn, "RC-0001", 1, "hash-1", {"id": "RC-0001"}, chunks, embeddings
    )
    db_conn.commit()

    vigente = repo.get_vigente_version(db_conn, "RC-0001")
    assert vigente == {"id": uuid.UUID(version_id), "numero_version": 1, "content_hash": "hash-1"}


def test_close_version_marks_it_as_no_longer_vigente(db_conn, clean_db):
    organismo_id = repo.upsert_organismo(db_conn, "Registro Civil")
    repo.upsert_tramite(db_conn, "RC-0001", organismo_id, "Actas", "Actas Regulares")
    chunks = [{"tipo_chunk": "descripcion", "texto": "texto", "fuente_url": None}]
    embeddings = [[0.1] * 1536]
    version_id = repo.insert_version_with_chunks(
        db_conn, "RC-0001", 1, "hash-1", {"id": "RC-0001"}, chunks, embeddings
    )
    db_conn.commit()

    repo.close_version(db_conn, version_id)
    db_conn.commit()

    assert repo.get_vigente_version(db_conn, "RC-0001") is None


def test_obtener_snapshot_vigente_devuelve_none_si_no_hay_version(db_conn, clean_db):
    organismo_id = repo.upsert_organismo(db_conn, "Registro Civil")
    repo.upsert_tramite(db_conn, "RC-0001", organismo_id, "Actas", "Actas Regulares")
    db_conn.commit()

    assert repo.obtener_snapshot_vigente(db_conn, "RC-0001") is None


def test_obtener_snapshot_vigente_devuelve_el_snapshot(db_conn, clean_db):
    organismo_id = repo.upsert_organismo(db_conn, "Registro Civil")
    repo.upsert_tramite(db_conn, "RC-0001", organismo_id, "Actas", "Actas Regulares")
    snapshot = {"id": "RC-0001", "requisitos": ["DNI"], "costo": "$6000"}
    chunks = [{"tipo_chunk": "descripcion", "texto": "texto", "fuente_url": None}]
    embeddings = [[0.0] * 1536]
    repo.insert_version_with_chunks(db_conn, "RC-0001", 1, "hash-1", snapshot, chunks, embeddings)
    db_conn.commit()

    resultado = repo.obtener_snapshot_vigente(db_conn, "RC-0001")

    assert resultado == snapshot
