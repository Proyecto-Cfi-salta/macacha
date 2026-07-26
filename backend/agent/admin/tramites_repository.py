def listar_tramites(conn) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT t.id, t.nombre_oficial, o.nombre, t.categoria, t.veces_consultado, v.numero_version
            FROM tramites t
            JOIN organismos o ON o.id = t.organismo_id
            LEFT JOIN tramite_versiones v ON v.tramite_id = t.id AND v.es_vigente = true
            ORDER BY t.id
            """
        )
        return [
            {
                "id": tramite_id,
                "nombre_oficial": nombre_oficial,
                "organismo": organismo,
                "categoria": categoria,
                "veces_consultado": veces_consultado,
                "numero_version": numero_version,
            }
            for tramite_id, nombre_oficial, organismo, categoria, veces_consultado, numero_version in cur.fetchall()
        ]


def listar_organismos(conn) -> list[str]:
    with conn.cursor() as cur:
        cur.execute("SELECT nombre FROM organismos ORDER BY nombre")
        return [row[0] for row in cur.fetchall()]


def obtener_chunks_por_version(conn, version_id: str) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT tipo_chunk, texto, fuente_url, embedding FROM tramite_chunks WHERE version_id = %s",
            (version_id,),
        )
        return [
            {"tipo_chunk": tipo_chunk, "texto": texto, "fuente_url": fuente_url, "embedding": embedding}
            for tipo_chunk, texto, fuente_url, embedding in cur.fetchall()
        ]
