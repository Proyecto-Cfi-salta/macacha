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

    if not filas:
        return []

    session_ids = [str(sesion_id) for sesion_id, _ in filas]
    conteos = _contar_mensajes_visibles_batch(conn, session_ids)
    ultimos = _obtener_ultimo_mensaje_batch(conn, session_ids)
    citados = _extraer_tramites_citados_batch(conn, session_ids)

    return [
        {
            "id": str(sesion_id),
            "creado_en": creado_en.isoformat(),
            "cantidad_mensajes": conteos.get(str(sesion_id), 0),
            "ultimo_mensaje": ultimos.get(str(sesion_id)),
            "tramites_citados": citados.get(str(sesion_id), []),
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
            SELECT rol, contenido, tool_calls, tool_call_id, proveedor, created_at
            FROM mensajes
            WHERE session_id = %s
            ORDER BY orden ASC
            """,
            (session_id,),
        )
        filas = cur.fetchall()

    mensajes = []
    for rol, contenido, tool_calls, tool_call_id, proveedor, creado_en in filas:
        mensaje: dict = {"rol": rol, "contenido": contenido, "creado_en": creado_en.isoformat()}
        if tool_calls is not None:
            mensaje["tool_calls"] = tool_calls
        if tool_call_id is not None:
            mensaje["tool_call_id"] = tool_call_id
        if proveedor is not None:
            mensaje["proveedor"] = proveedor
        mensajes.append(mensaje)
    return mensajes


def _contar_mensajes_visibles_batch(conn, session_ids: list[str]) -> dict[str, int]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT session_id, COUNT(*)
            FROM mensajes
            WHERE session_id = ANY(%s) AND rol IN ('user', 'assistant') AND contenido IS NOT NULL
            GROUP BY session_id
            """,
            (session_ids,),
        )
        return {str(session_id): total for session_id, total in cur.fetchall()}


def _obtener_ultimo_mensaje_batch(conn, session_ids: list[str]) -> dict[str, str]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT ON (session_id) session_id, contenido
            FROM mensajes
            WHERE session_id = ANY(%s) AND rol IN ('user', 'assistant') AND contenido IS NOT NULL
            ORDER BY session_id, orden DESC
            """,
            (session_ids,),
        )
        return {str(session_id): _truncar(contenido, 140) for session_id, contenido in cur.fetchall()}


def _truncar(texto: str, longitud: int) -> str:
    if len(texto) <= longitud:
        return texto
    return texto[:longitud] + "…"


def _extraer_tramites_citados_batch(conn, session_ids: list[str]) -> dict[str, list[str]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT session_id, tool_calls
            FROM mensajes
            WHERE session_id = ANY(%s) AND rol = 'assistant' AND tool_calls IS NOT NULL
            ORDER BY session_id, orden ASC
            """,
            (session_ids,),
        )
        filas = cur.fetchall()

    citados_por_sesion: dict[str, list[str]] = {}
    for session_id, tool_calls in filas:
        sid = str(session_id)
        citados = citados_por_sesion.setdefault(sid, [])
        for tool_call in tool_calls:
            try:
                argumentos = json.loads(tool_call["function"]["arguments"])
            except (KeyError, TypeError, json.JSONDecodeError):
                continue
            tramite_id = argumentos.get("tramite_id")
            if tramite_id and tramite_id not in citados:
                citados.append(tramite_id)
    return citados_por_sesion


def listar_sesiones_de_organismo(
    conn, organismo_id: int, page: int, page_size: int
) -> tuple[list[dict], int]:
    filas = _listar_todas_las_sesiones(conn)
    if not filas:
        return [], 0

    session_ids = [str(sesion_id) for sesion_id, _ in filas]
    citados = _extraer_tramites_citados_batch(conn, session_ids)
    organismos_de_tramites = _organismos_de_tramites(conn, citados)

    filtradas = [
        (sesion_id, creado_en)
        for sesion_id, creado_en in filas
        if any(
            organismos_de_tramites.get(tramite_id) == organismo_id
            for tramite_id in citados.get(str(sesion_id), [])
        )
    ]

    total = len(filtradas)
    offset = (page - 1) * page_size
    pagina = filtradas[offset : offset + page_size]

    if not pagina:
        return [], total

    ids_pagina = [str(sesion_id) for sesion_id, _ in pagina]
    conteos = _contar_mensajes_visibles_batch(conn, ids_pagina)
    ultimos = _obtener_ultimo_mensaje_batch(conn, ids_pagina)

    resultado = [
        {
            "id": str(sesion_id),
            "creado_en": creado_en.isoformat(),
            "cantidad_mensajes": conteos.get(str(sesion_id), 0),
            "ultimo_mensaje": ultimos.get(str(sesion_id)),
            "tramites_citados": citados.get(str(sesion_id), []),
        }
        for sesion_id, creado_en in pagina
    ]
    return resultado, total


def sesion_pertenece_a_organismo(conn, session_id: str, organismo_id: int) -> bool:
    citados = _extraer_tramites_citados_batch(conn, [session_id])
    tramites_citados = citados.get(session_id, [])
    if not tramites_citados:
        return False
    organismos_de_tramites = _organismos_de_tramites(conn, {session_id: tramites_citados})
    return any(organismos_de_tramites.get(t) == organismo_id for t in tramites_citados)


def _listar_todas_las_sesiones(conn) -> list[tuple]:
    with conn.cursor() as cur:
        cur.execute("SELECT id, created_at FROM sesiones ORDER BY created_at DESC")
        return cur.fetchall()


def _organismos_de_tramites(conn, citados_por_sesion: dict[str, list[str]]) -> dict[str, int]:
    tramite_ids = {tid for citas in citados_por_sesion.values() for tid in citas}
    if not tramite_ids:
        return {}
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, organismo_id FROM tramites WHERE id = ANY(%s)",
            (list(tramite_ids),),
        )
        return {tramite_id: organismo_id for tramite_id, organismo_id in cur.fetchall()}
