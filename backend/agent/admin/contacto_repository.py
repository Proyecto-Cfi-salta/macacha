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
            cur.execute("SELECT email_contacto FROM organismos WHERE id = %s", (organismo_id,))
            fila = cur.fetchone()
        if fila is not None and fila[0]:
            return [fila[0]]

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
        s.nombre, s.email, s.telefono, s.consulta, s.estado, s.creado_en,
        s.resuelto_por_email, s.resuelto_en
    FROM solicitudes_contacto s
    LEFT JOIN tramites t ON t.id = s.tramite_id
    LEFT JOIN organismos o ON o.id = s.organismo_id
"""


def _fila_a_dict(fila) -> dict:
    (
        id_, session_id, tramite_id, tramite_nombre, organismo_id, organismo,
        nombre, email, telefono, consulta, estado, creado_en, resuelto_por, resuelto_en,
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
        "resuelto_por": resuelto_por,
        "resuelto_en": resuelto_en.isoformat() if resuelto_en else None,
    }


def listar_solicitudes(
    conn, organismo_id: int | None, page: int = 1, page_size: int = 20
) -> tuple[list[dict], int]:
    """Pendientes primero y, dentro de cada grupo, las más nuevas arriba.

    El id desempata para que la paginación sea estable (mismo orden entre páginas).
    """
    donde = ""
    params: tuple = ()
    if organismo_id is not None:
        donde = " WHERE s.organismo_id = %s"
        params = (organismo_id,)

    with conn.cursor() as cur:
        cur.execute(f"SELECT COUNT(*) FROM solicitudes_contacto s{donde}", params)
        total = cur.fetchone()[0]
        cur.execute(
            _SELECT_SOLICITUD
            + donde
            + " ORDER BY (s.estado = 'pendiente') DESC, s.creado_en DESC, s.id"
            + " LIMIT %s OFFSET %s",
            params + (page_size, (page - 1) * page_size),
        )
        return [_fila_a_dict(fila) for fila in cur.fetchall()], total


def obtener_solicitud(conn, solicitud_id: str) -> dict | None:
    with conn.cursor() as cur:
        cur.execute(_SELECT_SOLICITUD + " WHERE s.id = %s", (solicitud_id,))
        fila = cur.fetchone()
        return _fila_a_dict(fila) if fila else None


def actualizar_estado(conn, solicitud_id: str, estado: str, resuelto_por: str | None = None) -> None:
    """Al resolver guarda quién y cuándo; al volver a pendiente lo borra.

    Resolver una solicitud que ya estaba resuelta no cambia a quien la resolvió primero.
    """
    with conn.cursor() as cur:
        if estado == "resuelto":
            cur.execute(
                """
                UPDATE solicitudes_contacto
                SET estado = 'resuelto',
                    resuelto_por_email = CASE WHEN estado = 'resuelto' THEN resuelto_por_email ELSE %s END,
                    resuelto_en = CASE WHEN estado = 'resuelto' THEN resuelto_en ELSE now() END
                WHERE id = %s
                """,
                (resuelto_por, solicitud_id),
            )
        else:
            cur.execute(
                """
                UPDATE solicitudes_contacto
                SET estado = %s, resuelto_por_email = NULL, resuelto_en = NULL
                WHERE id = %s
                """,
                (estado, solicitud_id),
            )


def listar_casillas(conn, organismo_id: int | None) -> list[dict]:
    with conn.cursor() as cur:
        if organismo_id is None:
            cur.execute("SELECT id, nombre, email_contacto FROM organismos ORDER BY nombre")
        else:
            cur.execute(
                "SELECT id, nombre, email_contacto FROM organismos WHERE id = %s", (organismo_id,)
            )
        return [
            {"id": id_, "nombre": nombre, "email_contacto": email}
            for id_, nombre, email in cur.fetchall()
        ]


def guardar_casilla(conn, organismo_id: int, email_contacto: str | None) -> dict | None:
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE organismos SET email_contacto = %s WHERE id = %s RETURNING id, nombre, email_contacto",
            (email_contacto, organismo_id),
        )
        fila = cur.fetchone()
    if fila is None:
        return None
    return {"id": fila[0], "nombre": fila[1], "email_contacto": fila[2]}
