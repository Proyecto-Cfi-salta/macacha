from ingest.snapshot_builder import build_snapshot


def _raw_tramite(**overrides):
    base = {
        "id": "RC-0001",
        "organismo": "Registro Civil",
        "categoria": "Actas",
        "tramite": "Actas Regulares",
        "descripcion": "Descripción de prueba",
        "objetivo": "Objetivo de prueba",
        "sinonimos": ["partida"],
        "keywords": ["actas"],
        "requisitos": ["DNI"],
        "pasos": ["Ingresar a https://registrocivilsalta.gob.ar/"],
        "costo": "$6000",
        "modalidad": "Online",
        "duracion": "10 días hábiles",
        "problemas_frecuentes": ["Datos incompletos"],
        "preguntas_frecuentes": [{"pregunta": "¿Cómo?", "respuesta": "Online"}],
        "chunks": [
            {
                "chunk_id": "RC-0001-CH-01",
                "texto": "Descripción de prueba",
                "fuente": "https://registrocivilsalta.gob.ar/oficial/tramites/actas-1",
            }
        ],
    }
    base.update(overrides)
    return base


def _faq_generator_no_debe_llamarse(**kwargs):
    raise AssertionError("no debería generarse FAQs si el trámite ya trae")


def test_keeps_existing_faqs_and_marks_not_auto_generated():
    snapshot = build_snapshot(_raw_tramite(), _faq_generator_no_debe_llamarse)

    assert snapshot["id"] == "RC-0001"
    assert snapshot["nombre_oficial"] == "Actas Regulares"
    assert snapshot["preguntas_frecuentes"] == [{"pregunta": "¿Cómo?", "respuesta": "Online"}]
    assert snapshot["faq_generadas_automaticamente"] is False
    assert snapshot["enlaces_oficiales"] == [
        "https://registrocivilsalta.gob.ar/",
        "https://registrocivilsalta.gob.ar/oficial/tramites/actas-1",
    ]


def test_generates_faqs_when_missing():
    llamadas = []

    def faq_generator(**kwargs):
        llamadas.append(kwargs)
        return [{"pregunta": "¿Qué es?", "respuesta": "Un trámite"}]

    raw = _raw_tramite(preguntas_frecuentes=[])
    snapshot = build_snapshot(raw, faq_generator)

    assert snapshot["preguntas_frecuentes"] == [{"pregunta": "¿Qué es?", "respuesta": "Un trámite"}]
    assert snapshot["faq_generadas_automaticamente"] is True
    assert llamadas == [
        {
            "nombre_oficial": "Actas Regulares",
            "descripcion": "Descripción de prueba",
            "requisitos": ["DNI"],
            "pasos": ["Ingresar a https://registrocivilsalta.gob.ar/"],
        }
    ]
