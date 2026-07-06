import uuid

from retrieval.chunk_result import chunk_desde_fila


def test_mapea_fila_a_dict_con_chunk_id_como_string():
    chunk_uuid = uuid.uuid4()
    fila = (
        chunk_uuid,
        "RC-0001",
        "Actas Regulares",
        "Actas",
        "Registro Civil",
        "descripcion",
        "texto del chunk",
        "https://registrocivilsalta.gob.ar/oficial/tramites/actas-1",
    )

    resultado = chunk_desde_fila(fila)

    assert resultado == {
        "chunk_id": str(chunk_uuid),
        "tramite_id": "RC-0001",
        "nombre_oficial": "Actas Regulares",
        "categoria": "Actas",
        "organismo": "Registro Civil",
        "tipo_chunk": "descripcion",
        "texto": "texto del chunk",
        "fuente_url": "https://registrocivilsalta.gob.ar/oficial/tramites/actas-1",
    }


def test_permite_fuente_url_nula():
    chunk_uuid = uuid.uuid4()
    fila = (chunk_uuid, "RC-0002", "Actas Exprés", "Actas", "Registro Civil", "faq", "pregunta respuesta", None)

    resultado = chunk_desde_fila(fila)

    assert resultado["fuente_url"] is None
