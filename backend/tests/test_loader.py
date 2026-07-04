import json

from ingest.loader import ingest_file, ingest_tramite


def _fake_embed_fn(texts):
    return [[0.0] * 1536 for _ in texts]


def _fake_faq_fn(nombre_oficial, descripcion, requisitos, pasos):
    return [{"pregunta": f"¿Qué es {nombre_oficial}?", "respuesta": descripcion}]


def _raw_tramite(**overrides):
    base = {
        "id": "RC-0001",
        "organismo": "Registro Civil",
        "categoria": "Actas",
        "tramite": "Actas Regulares",
        "descripcion": "Descripción de prueba",
        "objetivo": "Objetivo de prueba",
        "sinonimos": [],
        "keywords": [],
        "requisitos": ["DNI"],
        "pasos": ["Paso 1"],
        "costo": "$6000",
        "modalidad": "Online",
        "duracion": "10 días hábiles",
        "problemas_frecuentes": [],
        "preguntas_frecuentes": [{"pregunta": "p", "respuesta": "r"}],
        "chunks": [{"chunk_id": "CH-01", "texto": "Descripción de prueba", "fuente": "https://x"}],
    }
    base.update(overrides)
    return base


def test_ingest_tramite_creates_first_version(db_conn, clean_db):
    estado = ingest_tramite(_raw_tramite(), db_conn, _fake_embed_fn, _fake_faq_fn)
    db_conn.commit()

    assert estado == "nuevo"


def test_ingest_tramite_skips_when_unchanged(db_conn, clean_db):
    raw = _raw_tramite()

    primero = ingest_tramite(raw, db_conn, _fake_embed_fn, _fake_faq_fn)
    db_conn.commit()
    segundo = ingest_tramite(raw, db_conn, _fake_embed_fn, _fake_faq_fn)
    db_conn.commit()

    assert primero == "nuevo"
    assert segundo == "sin_cambios"


def test_ingest_tramite_creates_new_version_when_content_changes(db_conn, clean_db):
    raw = _raw_tramite()
    ingest_tramite(raw, db_conn, _fake_embed_fn, _fake_faq_fn)
    db_conn.commit()

    raw_modificado = _raw_tramite(costo="$7000")
    estado = ingest_tramite(raw_modificado, db_conn, _fake_embed_fn, _fake_faq_fn)
    db_conn.commit()

    assert estado == "nueva_version"


def test_ingest_tramite_generates_faqs_when_missing(db_conn, clean_db):
    llamadas = []

    def faq_fn_espia(**kwargs):
        llamadas.append(kwargs)
        return _fake_faq_fn(**kwargs)

    raw = _raw_tramite(id="RC-0002", preguntas_frecuentes=[])
    ingest_tramite(raw, db_conn, _fake_embed_fn, faq_fn_espia)
    db_conn.commit()

    assert len(llamadas) == 1


def test_ingest_file_returns_summary_counts(tmp_path, db_conn, clean_db):
    raw_tramites = [
        _raw_tramite(),
        _raw_tramite(id="RC-0002", tramite="Actas Exprés", preguntas_frecuentes=[]),
    ]
    archivo = tmp_path / "sample.json"
    archivo.write_text(json.dumps(raw_tramites), encoding="utf-8")

    resumen = ingest_file(str(archivo), db_conn, _fake_embed_fn, _fake_faq_fn)

    assert resumen == {"nuevos": 2, "sin_cambios": 0, "nueva_version": 0}
