import json
import uuid


def upsert_organismo(conn, nombre: str) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO organismos (nombre) VALUES (%s)
            ON CONFLICT (nombre) DO UPDATE SET nombre = EXCLUDED.nombre
            RETURNING id
            """,
            (nombre,),
        )
        return cur.fetchone()[0]


def upsert_tramite(
    conn, tramite_id: str, organismo_id: int, categoria: str, nombre_oficial: str
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO tramites (id, organismo_id, categoria, nombre_oficial)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE
                SET organismo_id = EXCLUDED.organismo_id,
                    categoria = EXCLUDED.categoria,
                    nombre_oficial = EXCLUDED.nombre_oficial
            """,
            (tramite_id, organismo_id, categoria, nombre_oficial),
        )


def get_vigente_version(conn, tramite_id: str) -> dict | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, numero_version, content_hash
            FROM tramite_versiones
            WHERE tramite_id = %s AND es_vigente = true
            """,
            (tramite_id,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return {"id": row[0], "numero_version": row[1], "content_hash": row[2]}


def close_version(conn, version_id) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE tramite_versiones
            SET es_vigente = false, vigente_hasta = now()
            WHERE id = %s
            """,
            (version_id,),
        )


def insert_version_with_chunks(
    conn,
    tramite_id: str,
    numero_version: int,
    content_hash: str,
    snapshot: dict,
    chunks: list[dict],
    embeddings: list[list[float]],
) -> str:
    version_id = uuid.uuid4()
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO tramite_versiones
                (id, tramite_id, numero_version, es_vigente, content_hash, snapshot)
            VALUES (%s, %s, %s, true, %s, %s)
            """,
            (
                version_id,
                tramite_id,
                numero_version,
                content_hash,
                json.dumps(snapshot, ensure_ascii=False),
            ),
        )
        for chunk, embedding in zip(chunks, embeddings):
            cur.execute(
                """
                INSERT INTO tramite_chunks (version_id, tipo_chunk, texto, fuente_url, embedding)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (version_id, chunk["tipo_chunk"], chunk["texto"], chunk["fuente_url"], embedding),
            )
    return str(version_id)


def obtener_snapshot_vigente(conn, tramite_id: str) -> dict | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT snapshot
            FROM tramite_versiones
            WHERE tramite_id = %s AND es_vigente = true
            """,
            (tramite_id,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return row[0]
