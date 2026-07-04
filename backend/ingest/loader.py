import json

from ingest import repository as repo
from ingest.chunk_builder import build_chunks
from ingest.hashing import compute_content_hash
from ingest.snapshot_builder import build_snapshot


def ingest_tramite(raw_tramite: dict, conn, embed_fn, faq_fn) -> str:
    snapshot = build_snapshot(raw_tramite, faq_fn)
    content_hash = compute_content_hash(snapshot)

    organismo_id = repo.upsert_organismo(conn, snapshot["organismo"])
    repo.upsert_tramite(
        conn, snapshot["id"], organismo_id, snapshot["categoria"], snapshot["nombre_oficial"]
    )

    vigente = repo.get_vigente_version(conn, snapshot["id"])

    if vigente is not None and vigente["content_hash"] == content_hash:
        return "sin_cambios"

    numero_version = 1 if vigente is None else vigente["numero_version"] + 1
    if vigente is not None:
        repo.close_version(conn, vigente["id"])

    chunks = build_chunks(raw_tramite, snapshot)
    embeddings = embed_fn([c["texto"] for c in chunks])
    repo.insert_version_with_chunks(
        conn, snapshot["id"], numero_version, content_hash, snapshot, chunks, embeddings
    )

    return "nuevo" if vigente is None else "nueva_version"


def ingest_file(path: str, conn, embed_fn, faq_fn) -> dict:
    with open(path, encoding="utf-8") as f:
        raw_tramites = json.load(f)

    resumen = {"nuevos": 0, "sin_cambios": 0, "nueva_version": 0}
    for raw_tramite in raw_tramites:
        estado = ingest_tramite(raw_tramite, conn, embed_fn, faq_fn)
        conn.commit()
        if estado == "nuevo":
            resumen["nuevos"] += 1
        elif estado == "nueva_version":
            resumen["nueva_version"] += 1
        else:
            resumen["sin_cambios"] += 1
    return resumen
