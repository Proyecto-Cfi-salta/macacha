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
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO mensajes (session_id, rol, contenido, tool_calls, tool_call_id)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                session_id,
                rol,
                contenido,
                json.dumps(tool_calls) if tool_calls is not None else None,
                tool_call_id,
            ),
        )


def obtener_historial(conn, session_id: str) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT rol, contenido, tool_calls, tool_call_id
            FROM mensajes
            WHERE session_id = %s
            ORDER BY created_at
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
            SELECT rol, contenido, created_at
            FROM mensajes
            WHERE session_id = %s AND rol IN ('user', 'assistant') AND contenido IS NOT NULL
            ORDER BY created_at
            """,
            (session_id,),
        )
        return [
            {"rol": rol, "contenido": contenido, "creado_en": creado_en.isoformat()}
            for rol, contenido, creado_en in cur.fetchall()
        ]
