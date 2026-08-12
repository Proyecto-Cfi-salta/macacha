def crear_solicitud(
    conn,
    session_id: str,
    tramite_id: str | None,
    organismo_id: int | None,
    nombre: str,
    email: str,
    telefono: str,
    consulta: str,
) -> str:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO solicitudes_contacto
                (session_id, tramite_id, organismo_id, nombre, email, telefono, consulta)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (session_id, tramite_id, organismo_id, nombre, email, telefono, consulta),
        )
        return str(cur.fetchone()[0])


def resolver_destinatarios(conn, organismo_id: int | None) -> list[str]:
    if organismo_id is not None:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT email FROM admins WHERE organismo_id = %s AND activo = true",
                (organismo_id,),
            )
            emails = [row[0] for row in cur.fetchall()]
        if emails:
            return emails

    with conn.cursor() as cur:
        cur.execute("SELECT email FROM admins WHERE rol = 'super_admin' AND activo = true")
        return [row[0] for row in cur.fetchall()]


_SELECT_SOLICITUD = """
    SELECT
        s.id, s.session_id, s.tramite_id, t.nombre_oficial, s.organismo_id, o.nombre,
        s.nombre, s.email, s.telefono, s.consulta, s.estado, s.creado_en
    FROM solicitudes_contacto s
    LEFT JOIN tramites t ON t.id = s.tramite_id
    LEFT JOIN organismos o ON o.id = s.organismo_id
"""


def _fila_a_dict(fila) -> dict:
    (
        id_, session_id, tramite_id, tramite_nombre, organismo_id, organismo,
        nombre, email, telefono, consulta, estado, creado_en,
    ) = fila
    return {
        "id": str(id_),
        "session_id": str(session_id),
        "tramite_id": tramite_id,
        "tramite_nombre": tramite_nombre,
        "organismo_id": organismo_id,
        "organismo": organismo,
        "nombre": nombre,
        "email": email,
        "telefono": telefono,
        "consulta": consulta,
        "estado": estado,
        "creado_en": creado_en.isoformat(),
    }


def listar_solicitudes(conn, organismo_id: int | None) -> list[dict]:
    query = _SELECT_SOLICITUD
    params: tuple = ()
    if organismo_id is not None:
        query += " WHERE s.organismo_id = %s"
        params = (organismo_id,)
    query += " ORDER BY s.creado_en DESC"

    with conn.cursor() as cur:
        cur.execute(query, params)
        return [_fila_a_dict(fila) for fila in cur.fetchall()]


def obtener_solicitud(conn, solicitud_id: str) -> dict | None:
    with conn.cursor() as cur:
        cur.execute(_SELECT_SOLICITUD + " WHERE s.id = %s", (solicitud_id,))
        fila = cur.fetchone()
        return _fila_a_dict(fila) if fila else None


def actualizar_estado(conn, solicitud_id: str, estado: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE solicitudes_contacto SET estado = %s WHERE id = %s", (estado, solicitud_id)
        )
