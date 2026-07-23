from ingest.link_extractor import extract_official_links


def build_snapshot(raw_tramite: dict, faq_generator) -> dict:
    preguntas_frecuentes = raw_tramite.get("preguntas_frecuentes") or []
    faq_generadas_automaticamente = False

    if not preguntas_frecuentes:
        preguntas_frecuentes = faq_generator(
            nombre_oficial=raw_tramite["tramite"],
            descripcion=raw_tramite.get("descripcion", ""),
            requisitos=raw_tramite.get("requisitos", []),
            pasos=raw_tramite.get("pasos", []),
        )
        faq_generadas_automaticamente = True

    enlaces_oficiales = extract_official_links(
        raw_tramite.get("pasos", []), raw_tramite.get("chunks", [])
    )

    return {
        "id": raw_tramite["id"],
        "organismo": raw_tramite["organismo"],
        "categoria": raw_tramite["categoria"],
        "nombre_oficial": raw_tramite["tramite"],
        "sinonimos": raw_tramite.get("sinonimos", []),
        "keywords": raw_tramite.get("keywords", []),
        "descripcion": raw_tramite.get("descripcion", ""),
        "objetivo": raw_tramite.get("objetivo", ""),
        "requisitos": raw_tramite.get("requisitos", []),
        "pasos": raw_tramite.get("pasos", []),
        "costo": raw_tramite.get("costo", ""),
        "modalidad": raw_tramite.get("modalidad", ""),
        "duracion": raw_tramite.get("duracion", ""),
        "telefono_contacto": raw_tramite.get("telefono_contacto", ""),
        "email_contacto": raw_tramite.get("email_contacto", ""),
        "problemas_frecuentes": raw_tramite.get("problemas_frecuentes", []),
        "preguntas_frecuentes": preguntas_frecuentes,
        "enlaces_oficiales": enlaces_oficiales,
        "faq_generadas_automaticamente": faq_generadas_automaticamente,
    }
