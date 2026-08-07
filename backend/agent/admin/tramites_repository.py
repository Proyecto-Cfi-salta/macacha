def listar_tramites(conn, organismo_id: int | None = None) -> list[dict]:
    query = """
        SELECT t.id, t.nombre_oficial, o.nombre, t.categoria, t.veces_consultado, v.numero_version
        FROM tramites t
        JOIN organismos o ON o.id = t.organismo_id
        LEFT JOIN tramite_versiones v ON v.tramite_id = t.id AND v.es_vigente = true
    """
    params: tuple = ()
    if organismo_id is not None:
        query += " WHERE t.organismo_id = %s"
        params = (organismo_id,)
    query += " ORDER BY t.id"

    with conn.cursor() as cur:
        cur.execute(query, params)
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


def listar_organismos(conn) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute("SELECT id, nombre FROM organismos ORDER BY nombre")
        return [{"id": id_, "nombre": nombre} for id_, nombre in cur.fetchall()]


def obtener_organismo_id_de_tramite(conn, tramite_id: str) -> int | None:
    with conn.cursor() as cur:
        cur.execute("SELECT organismo_id FROM tramites WHERE id = %s", (tramite_id,))
        fila = cur.fetchone()
        return fila[0] if fila else None


def obtener_nombre_organismo(conn, organismo_id: int) -> str | None:
    with conn.cursor() as cur:
        cur.execute("SELECT nombre FROM organismos WHERE id = %s", (organismo_id,))
        fila = cur.fetchone()
        return fila[0] if fila else None


def obtener_organismo_id_por_nombre(conn, nombre: str) -> int | None:
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM organismos WHERE nombre = %s", (nombre,))
        fila = cur.fetchone()
        return fila[0] if fila else None


def crear_organismo(conn, nombre: str) -> int:
    with conn.cursor() as cur:
        cur.execute("INSERT INTO organismos (nombre) VALUES (%s) RETURNING id", (nombre,))
        return cur.fetchone()[0]


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
