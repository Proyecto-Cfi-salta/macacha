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


def generar_id_tramite(conn, organismo: str) -> str:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT t.id
            FROM tramites t
            JOIN organismos o ON o.id = t.organismo_id
            WHERE o.nombre = %s
            ORDER BY t.id
            LIMIT 1
            """,
            (organismo,),
        )
        fila = cur.fetchone()

    if fila is not None:
        prefijo = fila[0].split("-")[0]
    else:
        prefijo = _resolver_colision_prefijo(conn, _iniciales(organismo))

    with conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM tramites WHERE id LIKE %s ORDER BY id DESC LIMIT 1",
            (f"{prefijo}-%",),
        )
        ultimo = cur.fetchone()

    siguiente_numero = 1 if ultimo is None else int(ultimo[0].split("-")[1]) + 1
    return f"{prefijo}-{siguiente_numero:04d}"


def _iniciales(organismo: str) -> str:
    conectores = {"de", "del", "la", "los", "las", "y"}
    palabras = [p for p in organismo.split() if p.lower() not in conectores]
    if not palabras:
        return organismo[:2].upper()
    return "".join(p[0].upper() for p in palabras)


def _resolver_colision_prefijo(conn, prefijo: str) -> str:
    with conn.cursor() as cur:
        for sufijo in [""] + [str(n) for n in range(2, 10)]:
            candidato = f"{prefijo}{sufijo}"
            cur.execute("SELECT 1 FROM tramites WHERE id LIKE %s LIMIT 1", (f"{candidato}-%",))
            if cur.fetchone() is None:
                return candidato
    raise RuntimeError(f"No se pudo generar un prefijo único a partir de '{prefijo}'")


def crear_tramite(conn, payload: dict, embed_fn) -> dict:
    organismo_id = upsert_organismo(conn, payload["organismo"])
    tramite_id = generar_id_tramite(conn, payload["organismo"])
    upsert_tramite(conn, tramite_id, organismo_id, payload.get("categoria", ""), payload["nombre_oficial"])

    snapshot = _construir_snapshot(tramite_id, payload)
    content_hash = compute_content_hash(snapshot)

    descripcion_texto = snapshot["nombre_oficial"]
    if snapshot["descripcion"]:
        descripcion_texto = f"{snapshot['nombre_oficial']}. {snapshot['descripcion']}"

    chunks = [{"tipo_chunk": "descripcion", "texto": descripcion_texto, "fuente_url": None}]
    chunks.extend(_construir_chunks_faq_y_enlaces(snapshot))

    embeddings = embed_fn([c["texto"] for c in chunks])

    insert_version_with_chunks(conn, tramite_id, 1, content_hash, snapshot, chunks, embeddings)

    return {"tramite_id": tramite_id, "numero_version": 1, "cambios": True}
