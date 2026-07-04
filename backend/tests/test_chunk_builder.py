from ingest.chunk_builder import build_chunks


def test_infers_tipo_chunk_from_source_chunks_and_appends_faq_and_links():
    raw_tramite = {
        "chunks": [
            {
                "chunk_id": "RC-0001-CH-01",
                "texto": "Actas Regulares. Trámite del Registro Civil de Salta.",
                "fuente": "https://registrocivilsalta.gob.ar/oficial/tramites/actas-1",
            },
            {
                "chunk_id": "RC-0001-CH-02",
                "texto": "Requisitos para Actas Regulares: Nombre, apellido, DNI.",
                "fuente": "https://registrocivilsalta.gob.ar/oficial/tramites/actas-1",
            },
            {
                "chunk_id": "RC-0001-CH-03",
                "texto": "Pasos para Actas Regulares: Ingresar al sitio.",
                "fuente": "https://registrocivilsalta.gob.ar/oficial/tramites/actas-1",
            },
            {
                "chunk_id": "RC-0001-CH-04",
                "texto": "Costo, duración y modalidad de Actas Regulares: costo $6000.",
                "fuente": "https://registrocivilsalta.gob.ar/oficial/tramites/actas-1",
            },
            {
                "chunk_id": "RC-0001-CH-05",
                "texto": "Problemas frecuentes de Actas Regulares: datos incompletos.",
                "fuente": "https://registrocivilsalta.gob.ar/oficial/tramites/actas-1",
            },
        ]
    }
    snapshot = {
        "preguntas_frecuentes": [{"pregunta": "¿Cómo hago el trámite?", "respuesta": "Online."}],
        "enlaces_oficiales": [
            "https://registrocivilsalta.gob.ar/",
            "https://registrocivilsalta.gob.ar/oficial/tramites/actas-1",
        ],
    }

    chunks = build_chunks(raw_tramite, snapshot)

    tipos = [c["tipo_chunk"] for c in chunks]
    assert tipos == [
        "descripcion",
        "requisitos",
        "pasos",
        "costo_modalidad",
        "problemas_frecuentes",
        "faq",
        "enlaces_oficiales",
    ]
    assert chunks[-2] == {
        "tipo_chunk": "faq",
        "texto": "¿Cómo hago el trámite? Online.",
        "fuente_url": None,
    }
    assert chunks[-1]["tipo_chunk"] == "enlaces_oficiales"
    assert "https://registrocivilsalta.gob.ar/" in chunks[-1]["texto"]


def test_omits_enlaces_chunk_when_no_links():
    raw_tramite = {"chunks": []}
    snapshot = {"preguntas_frecuentes": [], "enlaces_oficiales": []}

    chunks = build_chunks(raw_tramite, snapshot)

    assert chunks == []
