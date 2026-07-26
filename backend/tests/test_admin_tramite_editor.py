from ingest import repository as repo
from ingest.hashing import compute_content_hash
from agent.admin import tramite_editor
from agent.admin import tramites_repository


def _fake_embed(texts):
    return [[0.0] * 1536 for _ in texts]


def _snapshot_base(tramite_id="RC-0001", **overrides):
    snapshot = {
        "id": tramite_id,
        "organismo": "Registro Civil",
        "categoria": "Actas",
        "nombre_oficial": "Actas Regulares",
        "sinonimos": [],
        "keywords": [],
        "descripcion": "desc",
        "objetivo": "obj",
        "requisitos": ["DNI"],
        "pasos": ["paso 1"],
        "costo": "Gratuito",
        "modalidad": "Presencial",
        "duracion": "10 min",
        "telefono_contacto": "0387-1111111",
        "email_contacto": "rc@salta.gob.ar",
        "problemas_frecuentes": [],
        "preguntas_frecuentes": [{"pregunta": "p1", "respuesta": "r1"}],
        "enlaces_oficiales": ["https://salta.gob.ar/rc"],
        "faq_generadas_automaticamente": False,
    }
    snapshot.update(overrides)
    return snapshot


def _crear_tramite_base(conn, tramite_id="RC-0001"):
    organismo_id = repo.upsert_organismo(conn, "Registro Civil")
    repo.upsert_tramite(conn, tramite_id, organismo_id, "Actas", "Actas Regulares")
    snapshot = _snapshot_base(tramite_id)
    content_hash = compute_content_hash(snapshot)
    chunks = [
        {
            "tipo_chunk": "requisitos",
            "texto": "Requisitos para Actas Regulares: DNI",
            "fuente_url": "https://fuente.gob.ar",
        },
        {"tipo_chunk": "faq", "texto": "p1 r1", "fuente_url": None},
        {
            "tipo_chunk": "enlaces_oficiales",
            "texto": "Enlaces oficiales: https://salta.gob.ar/rc",
            "fuente_url": "https://salta.gob.ar/rc",
        },
    ]
    embeddings = [[0.1] * 1536, [0.2] * 1536, [0.3] * 1536]
    repo.insert_version_with_chunks(conn, tramite_id, 1, content_hash, snapshot, chunks, embeddings)
    conn.commit()
    return snapshot


def _payload_desde_snapshot(snapshot: dict) -> dict:
    return {k: v for k, v in snapshot.items() if k not in ("id", "faq_generadas_automaticamente")}


def test_editar_tramite_sin_cambios_no_crea_version_nueva(db_conn, clean_db):
    snapshot = _crear_tramite_base(db_conn)
    payload = _payload_desde_snapshot(snapshot)

    resultado = tramite_editor.editar_tramite(db_conn, "RC-0001", payload, _fake_embed)

    assert resultado == {"tramite_id": "RC-0001", "numero_version": 1, "cambios": False}


def test_editar_tramite_con_cambios_crea_version_nueva(db_conn, clean_db):
    snapshot = _crear_tramite_base(db_conn)
    payload = _payload_desde_snapshot(snapshot)
    payload["costo"] = "Con costo"

    resultado = tramite_editor.editar_tramite(db_conn, "RC-0001", payload, _fake_embed)
    db_conn.commit()

    assert resultado == {"tramite_id": "RC-0001", "numero_version": 2, "cambios": True}
    vigente = repo.get_vigente_version(db_conn, "RC-0001")
    assert vigente["numero_version"] == 2


def test_editar_tramite_preserva_chunks_narrativos_con_su_embedding(db_conn, clean_db):
    snapshot = _crear_tramite_base(db_conn)
    payload = _payload_desde_snapshot(snapshot)
    payload["costo"] = "Con costo"

    tramite_editor.editar_tramite(db_conn, "RC-0001", payload, _fake_embed)
    db_conn.commit()

    vigente = repo.get_vigente_version(db_conn, "RC-0001")
    chunks = tramites_repository.obtener_chunks_por_version(db_conn, vigente["id"])
    requisitos_chunk = next(c for c in chunks if c["tipo_chunk"] == "requisitos")
    assert requisitos_chunk["texto"] == "Requisitos para Actas Regulares: DNI"
    assert list(requisitos_chunk["embedding"][:3]) == [0.1, 0.1, 0.1]


def test_editar_tramite_regenera_chunks_de_faq_y_enlaces(db_conn, clean_db):
    snapshot = _crear_tramite_base(db_conn)
    payload = _payload_desde_snapshot(snapshot)
    payload["preguntas_frecuentes"] = [{"pregunta": "nueva", "respuesta": "resp nueva"}]

    tramite_editor.editar_tramite(db_conn, "RC-0001", payload, _fake_embed)
    db_conn.commit()

    vigente = repo.get_vigente_version(db_conn, "RC-0001")
    chunks = tramites_repository.obtener_chunks_por_version(db_conn, vigente["id"])
    faq_chunks = [c for c in chunks if c["tipo_chunk"] == "faq"]
    assert len(faq_chunks) == 1
    assert faq_chunks[0]["texto"] == "nueva resp nueva"


def test_editar_tramite_actualiza_organismo_categoria_y_nombre(db_conn, clean_db):
    snapshot = _crear_tramite_base(db_conn)
    payload = _payload_desde_snapshot(snapshot)
    payload["organismo"] = "Dirección de Rentas"
    payload["categoria"] = "Impuestos"
    payload["nombre_oficial"] = "Nuevo Nombre"

    tramite_editor.editar_tramite(db_conn, "RC-0001", payload, _fake_embed)
    db_conn.commit()

    tramites = tramites_repository.listar_tramites(db_conn)
    assert tramites[0]["organismo"] == "Dirección de Rentas"
    assert tramites[0]["categoria"] == "Impuestos"
    assert tramites[0]["nombre_oficial"] == "Nuevo Nombre"


def _payload_minimo(organismo="Registro Civil", categoria="Actas", nombre="Nuevo Trámite"):
    return {
        "organismo": organismo,
        "categoria": categoria,
        "nombre_oficial": nombre,
        "descripcion": "",
        "objetivo": "",
        "requisitos": [],
        "pasos": [],
        "costo": "",
        "modalidad": "",
        "duracion": "",
        "telefono_contacto": "",
        "email_contacto": "",
        "problemas_frecuentes": [],
        "sinonimos": [],
        "keywords": [],
        "enlaces_oficiales": [],
        "preguntas_frecuentes": [],
    }


def test_generar_id_tramite_reutiliza_prefijo_de_organismo_existente(db_conn, clean_db):
    organismo_id = repo.upsert_organismo(db_conn, "Registro Civil")
    repo.upsert_tramite(db_conn, "RC-0032", organismo_id, "Actas", "Trámite existente")
    db_conn.commit()

    assert tramite_editor.generar_id_tramite(db_conn, "Registro Civil") == "RC-0033"


def test_generar_id_tramite_deriva_prefijo_de_iniciales_para_organismo_nuevo(db_conn, clean_db):
    repo.upsert_organismo(db_conn, "Dirección de Rentas")
    db_conn.commit()

    assert tramite_editor.generar_id_tramite(db_conn, "Dirección de Rentas") == "DR-0001"


def test_generar_id_tramite_resuelve_colision_de_prefijo(db_conn, clean_db):
    organismo_dr_id = repo.upsert_organismo(db_conn, "Departamento de Recursos")
    repo.upsert_tramite(db_conn, "DR-0001", organismo_dr_id, "Cat", "Trámite del primero")
    repo.upsert_organismo(db_conn, "Dirección de Rentas")
    db_conn.commit()

    assert tramite_editor.generar_id_tramite(db_conn, "Dirección de Rentas") == "DR2-0001"


def test_crear_tramite_inserta_version_uno_con_chunk_de_descripcion(db_conn, clean_db):
    payload = _payload_minimo()
    payload["descripcion"] = "Descripción del trámite"

    resultado = tramite_editor.crear_tramite(db_conn, payload, _fake_embed)
    db_conn.commit()

    assert resultado == {"tramite_id": resultado["tramite_id"], "numero_version": 1, "cambios": True}
    assert resultado["tramite_id"].startswith("RC-")

    vigente = repo.get_vigente_version(db_conn, resultado["tramite_id"])
    chunks = tramites_repository.obtener_chunks_por_version(db_conn, vigente["id"])
    assert chunks[0]["tipo_chunk"] == "descripcion"
    assert chunks[0]["texto"] == "Nuevo Trámite. Descripción del trámite"


def test_crear_tramite_sin_descripcion_usa_solo_el_nombre(db_conn, clean_db):
    payload = _payload_minimo()

    resultado = tramite_editor.crear_tramite(db_conn, payload, _fake_embed)
    db_conn.commit()

    vigente = repo.get_vigente_version(db_conn, resultado["tramite_id"])
    chunks = tramites_repository.obtener_chunks_por_version(db_conn, vigente["id"])
    assert chunks[0]["texto"] == "Nuevo Trámite"


def test_crear_tramite_incluye_chunks_de_faq_si_hay(db_conn, clean_db):
    payload = _payload_minimo()
    payload["preguntas_frecuentes"] = [{"pregunta": "p", "respuesta": "r"}]

    resultado = tramite_editor.crear_tramite(db_conn, payload, _fake_embed)
    db_conn.commit()

    vigente = repo.get_vigente_version(db_conn, resultado["tramite_id"])
    chunks = tramites_repository.obtener_chunks_por_version(db_conn, vigente["id"])
    tipos = {c["tipo_chunk"] for c in chunks}
    assert "faq" in tipos
