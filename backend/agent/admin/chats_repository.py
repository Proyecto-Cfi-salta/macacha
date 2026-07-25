import json


def contar_sesiones(conn) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM sesiones")
        return cur.fetchone()[0]


def listar_sesiones(conn, page: int, page_size: int) -> list[dict]:
    offset = (page - 1) * page_size
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, created_at
            FROM sesiones
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
            """,
            (page_size, offset),
        )
        filas = cur.fetchall()

    return [
        {
            "id": str(sesion_id),
            "creado_en": creado_en.isoformat(),
            "cantidad_mensajes": _contar_mensajes_visibles(conn, sesion_id),
            "ultimo_mensaje": _obtener_ultimo_mensaje(conn, sesion_id),
            "tramites_citados": _extraer_tramites_citados(conn, sesion_id),
        }
        for sesion_id, creado_en in filas
    ]


def sesion_existe(conn, session_id: str) -> bool:
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM sesiones WHERE id = %s", (session_id,))
        return cur.fetchone() is not None


def obtener_mensajes_completos(conn, session_id: str) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT rol, contenido, tool_calls, tool_call_id, created_at
            FROM mensajes
            WHERE session_id = %s
            ORDER BY orden ASC
            """,
            (session_id,),
        )
        filas = cur.fetchall()

    mensajes = []
    for rol, contenido, tool_calls, tool_call_id, creado_en in filas:
        mensaje: dict = {"rol": rol, "contenido": contenido, "creado_en": creado_en.isoformat()}
        if tool_calls is not None:
            mensaje["tool_calls"] = tool_calls
        if tool_call_id is not None:
            mensaje["tool_call_id"] = tool_call_id
        mensajes.append(mensaje)
    return mensajes


def _contar_mensajes_visibles(conn, session_id) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(*) FROM mensajes
            WHERE session_id = %s AND rol IN ('user', 'assistant') AND contenido IS NOT NULL
            """,
            (session_id,),
        )
        return cur.fetchone()[0]


def _obtener_ultimo_mensaje(conn, session_id) -> str | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT contenido FROM mensajes
            WHERE session_id = %s AND rol IN ('user', 'assistant') AND contenido IS NOT NULL
            ORDER BY orden DESC
            LIMIT 1
            """,
            (session_id,),
        )
        fila = cur.fetchone()
        if fila is None:
            return None
        return _truncar(fila[0], 140)


def _truncar(texto: str, longitud: int) -> str:
    if len(texto) <= longitud:
        return texto
    return texto[:longitud] + "…"


def _extraer_tramites_citados(conn, session_id) -> list[str]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT tool_calls FROM mensajes
            WHERE session_id = %s AND rol = 'assistant' AND tool_calls IS NOT NULL
            ORDER BY orden ASC
            """,
            (session_id,),
        )
        filas = cur.fetchall()

    citados: list[str] = []
    for (tool_calls,) in filas:
        for tool_call in tool_calls:
            argumentos = json.loads(tool_call["function"]["arguments"])
            tramite_id = argumentos.get("tramite_id")
            if tramite_id and tramite_id not in citados:
                citados.append(tramite_id)
    return citados
