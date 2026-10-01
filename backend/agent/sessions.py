import json


def crear_sesion_si_no_existe(conn, session_id: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO sesiones (id) VALUES (%s) ON CONFLICT (id) DO NOTHING",
            (session_id,),
        )


def guardar_mensaje(
    conn,
    session_id: str,
    rol: str,
    contenido: str | None = None,
    tool_calls: list[dict] | None = None,
    tool_call_id: str | None = None,
    proveedor: str | None = None,
) -> str:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO mensajes (session_id, rol, contenido, tool_calls, tool_call_id, proveedor)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                session_id,
                rol,
                contenido,
                json.dumps(tool_calls) if tool_calls is not None else None,
                tool_call_id,
                proveedor,
            ),
        )
        return str(cur.fetchone()[0])


def obtener_historial(conn, session_id: str) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT rol, contenido, tool_calls, tool_call_id
            FROM mensajes
            WHERE session_id = %s
            ORDER BY orden
            """,
            (session_id,),
        )
        historial = []
        for rol, contenido, tool_calls, tool_call_id in cur.fetchall():
            mensaje: dict = {"role": rol, "content": contenido}
            if tool_calls is not None:
                mensaje["tool_calls"] = tool_calls
            if tool_call_id is not None:
                mensaje["tool_call_id"] = tool_call_id
            historial.append(mensaje)
        return historial


def obtener_mensajes_visibles(conn, session_id: str) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT m.id, m.rol, m.contenido, m.created_at,
                   (m.rol = 'assistant' AND m.tool_calls IS NULL) AS votable,
                   f.util, f.motivo, f.comentario
            FROM mensajes m
            LEFT JOIN feedback_respuestas f ON f.mensaje_id = m.id
            WHERE m.session_id = %s AND m.rol IN ('user', 'assistant') AND m.contenido IS NOT NULL
            ORDER BY m.orden
            """,
            (session_id,),
        )
        return [
            {
                "id": str(mensaje_id),
                "rol": rol,
                "contenido": contenido,
                "creado_en": creado_en.isoformat(),
                "votable": votable,
                "feedback": (
                    None if util is None else {"util": util, "motivo": motivo, "comentario": comentario}
                ),
            }
            for mensaje_id, rol, contenido, creado_en, votable, util, motivo, comentario in cur.fetchall()
        ]
