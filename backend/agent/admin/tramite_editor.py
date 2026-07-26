from ingest.hashing import compute_content_hash
from ingest.repository import (
    close_version,
    get_vigente_version,
    insert_version_with_chunks,
    upsert_organismo,
    upsert_tramite,
)
from agent.admin.tramites_repository import obtener_chunks_por_version

CHUNKS_PRESERVADOS = {"requisitos", "pasos", "costo_modalidad", "problemas_frecuentes", "descripcion"}


def _construir_snapshot(tramite_id: str, payload: dict) -> dict:
    return {
        "id": tramite_id,
        "organismo": payload["organismo"],
        "categoria": payload.get("categoria", ""),
        "nombre_oficial": payload["nombre_oficial"],
        "sinonimos": payload.get("sinonimos", []),
        "keywords": payload.get("keywords", []),
        "descripcion": payload.get("descripcion", ""),
        "objetivo": payload.get("objetivo", ""),
        "requisitos": payload.get("requisitos", []),
        "pasos": payload.get("pasos", []),
        "costo": payload.get("costo", ""),
        "modalidad": payload.get("modalidad", ""),
        "duracion": payload.get("duracion", ""),
        "telefono_contacto": payload.get("telefono_contacto", ""),
        "email_contacto": payload.get("email_contacto", ""),
        "problemas_frecuentes": payload.get("problemas_frecuentes", []),
        "preguntas_frecuentes": payload.get("preguntas_frecuentes", []),
        "enlaces_oficiales": payload.get("enlaces_oficiales", []),
        "faq_generadas_automaticamente": False,
    }


def _construir_chunks_faq_y_enlaces(snapshot: dict) -> list[dict]:
    chunks = []
    for faq in snapshot["preguntas_frecuentes"]:
        chunks.append(
            {
                "tipo_chunk": "faq",
                "texto": f"{faq['pregunta']} {faq['respuesta']}",
                "fuente_url": None,
            }
        )
    if snapshot["enlaces_oficiales"]:
        chunks.append(
            {
                "tipo_chunk": "enlaces_oficiales",
                "texto": "Enlaces oficiales: " + ", ".join(snapshot["enlaces_oficiales"]),
                "fuente_url": snapshot["enlaces_oficiales"][0],
            }
        )
    return chunks


def editar_tramite(conn, tramite_id: str, payload: dict, embed_fn) -> dict:
    snapshot = _construir_snapshot(tramite_id, payload)
    content_hash = compute_content_hash(snapshot)

    vigente = get_vigente_version(conn, tramite_id)

    if vigente["content_hash"] == content_hash:
        return {"tramite_id": tramite_id, "numero_version": vigente["numero_version"], "cambios": False}

    chunks_existentes = obtener_chunks_por_version(conn, vigente["id"])
    preservados = [c for c in chunks_existentes if c["tipo_chunk"] in CHUNKS_PRESERVADOS]
    chunks_nuevos = _construir_chunks_faq_y_enlaces(snapshot)

    embeddings_nuevos = embed_fn([c["texto"] for c in chunks_nuevos]) if chunks_nuevos else []

    chunks_finales = preservados + chunks_nuevos
    embeddings_finales = [c["embedding"] for c in preservados] + embeddings_nuevos

    close_version(conn, vigente["id"])
    numero_version = vigente["numero_version"] + 1
    insert_version_with_chunks(
        conn, tramite_id, numero_version, content_hash, snapshot, chunks_finales, embeddings_finales
    )

    organismo_id = upsert_organismo(conn, snapshot["organismo"])
    upsert_tramite(conn, tramite_id, organismo_id, snapshot["categoria"], snapshot["nombre_oficial"])

    return {"tramite_id": tramite_id, "numero_version": numero_version, "cambios": True}
